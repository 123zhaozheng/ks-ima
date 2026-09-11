"""Grounded-Ask profile resolution: scene-default fallback and assignment priority."""

# This file intentionally uses real PostgreSQL rows for the ask-profile path.
# ruff: noqa: E501

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ima.application.model_governance import ModelGovernanceService
from ima.application.search import SearchError, SearchService
from ima.config import Settings
from ima.domain.model_governance import Workflow

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None
ALEMBIC_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") if DATABASE_URL else None
)


def migrate() -> None:
    assert ALEMBIC_URL
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env={**os.environ, "IMA_DATABASE_URL": ALEMBIC_URL},
        check=True,
    )


def scene_services() -> tuple[ModelGovernanceService, SearchService, AsyncEngine]:
    assert DATABASE_URL
    engine = create_async_engine(DATABASE_URL)
    models = ModelGovernanceService(engine, Settings(environment="test"))
    return models, SearchService(engine, models), engine


def seed_scene_actor(actor_id: str) -> None:
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.users(id,email,normalized_email,display_name,security_stamp,created_at,updated_at) VALUES (%s,%s,%s,%s,'scene-ask-stamp',now(),now()) ON CONFLICT DO NOTHING",
            (actor_id, f"{actor_id}@scene.test", f"{actor_id}@scene.test", "Scene Ask Actor"),
        )
        connection.commit()


def seed_healthy_model(capability: str) -> tuple[Any, Any]:
    gateway_id, model_id = uuid4(), uuid4()
    dimension = 1536 if capability == "embedding" else None
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,enabled,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,created_at,updated_at) VALUES (%s,%s,'https://gateway.internal',ARRAY[%s],'required',true,1000,10000,10000,1000,1048576,now(),now())",
            (gateway_id, f"pg-ask-{uuid4().hex[:12]}", capability),
        )
        connection.execute(
            "INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,enabled,validated,embedding_dimension,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,true,true,%s,now(),now())",
            (
                model_id,
                gateway_id,
                f"{capability}-model",
                capability,
                capability.title(),
                dimension,
            ),
        )
        connection.execute(
            "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,checked_at) VALUES (%s,%s,'healthy',now())",
            (gateway_id, capability),
        )
        connection.commit()
    return gateway_id, model_id


def cleanup(
    *,
    kb_id: str | None = None,
    workflows: tuple[str, ...] = (),
    extra_profile_ids: tuple[Any, ...] = (),
    gateway_ids: tuple[Any, ...] = (),
    actor_ids: tuple[str, ...] = (),
) -> None:
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        if kb_id:
            connection.execute("DELETE FROM ima.kb_profile_assignments WHERE kb_id=%s", (kb_id,))
            connection.execute("DELETE FROM ima.knowledge_bases WHERE id=%s", (kb_id,))
        for workflow in workflows:
            connection.execute("DELETE FROM ima.scene_defaults WHERE workflow=%s", (workflow,))
            connection.execute(
                "DELETE FROM ima.capability_profile_versions WHERE profile_id IN (SELECT id FROM ima.capability_profiles WHERE workflow=%s AND business_alias='场景默认')",
                (workflow,),
            )
            connection.execute(
                "DELETE FROM ima.capability_profiles WHERE workflow=%s AND business_alias='场景默认'",
                (workflow,),
            )
        for profile_id in extra_profile_ids:
            connection.execute(
                "DELETE FROM ima.capability_profile_versions WHERE profile_id=%s", (profile_id,)
            )
            connection.execute("DELETE FROM ima.capability_profiles WHERE id=%s", (profile_id,))
        for gateway_id in gateway_ids:
            connection.execute("DELETE FROM ima.governed_models WHERE gateway_id=%s", (gateway_id,))
            connection.execute("DELETE FROM ima.model_gateways WHERE id=%s", (gateway_id,))
        for actor_id in actor_ids:
            connection.execute("DELETE FROM ima.audit_events WHERE actor_id=%s", (actor_id,))
            connection.execute("DELETE FROM ima.users WHERE id=%s", (actor_id,))
        connection.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_ask_profile_composes_scene_defaults_when_unassigned() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    chat_gateway, chat_model = seed_healthy_model("chat")
    embedding_gateway, embedding_model = seed_healthy_model("embedding")
    rerank_gateway, rerank_model = seed_healthy_model("rerank")
    seed_scene_actor("scene-ask-actor-1")
    models, search, engine = scene_services()
    try:
        await models.set_scene_default("scene-ask-actor-1", Workflow.GROUNDED_ASK, chat_model)
        await models.set_scene_default("scene-ask-actor-1", Workflow.EMBEDDING, embedding_model)
        await models.set_scene_default("scene-ask-actor-1", Workflow.RERANKING, rerank_model)
        async with engine.connect() as conn:
            config = await search._profile(conn, kb_id)
            assert config.chat_model_id == str(chat_model)
            assert config.system_prompt == "You are a helpful assistant."
            assert config.embedding_model_id == str(embedding_model)
            assert config.rerank_model_id == str(rerank_model)
            # The composed embedding slot reaches real consumers: the vector
            # target lookup proceeds past the slot check and demands an index.
            with pytest.raises(SearchError) as vector:
                await search._vector_target(conn, kb_id, config)
            assert vector.value.detail == "An exact active vector index is required"

        # Clearing the embedding and reranking defaults leaves those slots
        # empty; the ask profile reports the missing embedding assignment.
        await models.set_scene_default("scene-ask-actor-1", Workflow.EMBEDDING, None)
        await models.set_scene_default("scene-ask-actor-1", Workflow.RERANKING, None)
        async with engine.connect() as conn:
            config = await search._profile(conn, kb_id)
            assert config.chat_model_id == str(chat_model)
            assert config.embedding_model_id is None
            assert config.rerank_model_id is None
            with pytest.raises(SearchError) as vector:
                await search._vector_target(conn, kb_id, config)
            assert vector.value.detail == "The grounded profile has no embedding assignment"
    finally:
        await engine.dispose()
        cleanup(
            workflows=("grounded_ask", "embedding", "reranking"),
            gateway_ids=(chat_gateway, embedding_gateway, rerank_gateway),
            actor_ids=("scene-ask-actor-1",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_ask_profile_denies_without_scene_default_or_broken_assignment() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    broken_profile = uuid4()
    scene_gateway, scene_model = seed_healthy_model("chat")
    seed_scene_actor("scene-ask-actor-2")
    # Shared dev database: ensure no grounded_ask scene default pre-exists.
    cleanup(workflows=("grounded_ask",))
    models, search, engine = scene_services()
    try:
        async with engine.connect() as conn:
            with pytest.raises(SearchError) as denied:
                await search._profile(conn, kb_id)
            assert (denied.value.status_code, denied.value.code) == (409, "NO_ASSIGNMENT")

        # A grounded_ask scene default alone does not override an existing
        # assignment row whose profile join misses: the denial is preserved.
        await models.set_scene_default("scene-ask-actor-2", Workflow.GROUNDED_ASK, scene_model)
        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Ask KB',true,now(),now())",
                (kb_id,),
            )
            # The assignment's only version is a draft, so the published join
            # misses while the assignment row itself still exists.
            connection.execute(
                "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_at,updated_at) VALUES (%s,'grounded_ask','PG Ask Broken','profile',1,now(),now())",
                (broken_profile,),
            )
            connection.execute(
                "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,created_at,updated_at) VALUES (%s,1,'draft',%s::jsonb,'digest',now(),now())",
                (broken_profile, json.dumps({"workflow": "grounded_ask"})),
            )
            connection.execute(
                "INSERT INTO ima.kb_profile_assignments(kb_id,workflow,profile_id,profile_version,assigned_at) VALUES (%s,'grounded_ask',%s,1,now())",
                (kb_id, broken_profile),
            )
            connection.commit()
        async with engine.connect() as conn:
            with pytest.raises(SearchError) as denied:
                await search._profile(conn, kb_id)
            assert (denied.value.status_code, denied.value.code) == (409, "NO_ASSIGNMENT")
    finally:
        await engine.dispose()
        cleanup(
            kb_id=kb_id,
            workflows=("grounded_ask",),
            extra_profile_ids=(broken_profile,),
            gateway_ids=(scene_gateway,),
            actor_ids=("scene-ask-actor-2",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_ask_profile_assignment_beats_scene_defaults() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    assigned_profile = uuid4()
    scene_gateway, scene_model = seed_healthy_model("chat")
    assigned_gateway, assigned_model = seed_healthy_model("chat")
    seed_scene_actor("scene-ask-actor-3")
    models, search, engine = scene_services()
    try:
        await models.set_scene_default("scene-ask-actor-3", Workflow.GROUNDED_ASK, scene_model)
        assert SYNC_URL
        assigned_config = json.dumps(
            {
                "chatModelId": str(assigned_model),
                "systemPrompt": "Assigned ground",
                "contextLimit": 1000,
                "outputLimit": 100,
                "workflow": "grounded_ask",
            }
        )
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Ask KB',true,now(),now())",
                (kb_id,),
            )
            connection.execute(
                "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_at,updated_at) VALUES (%s,'grounded_ask','PG Ask Assigned','profile',1,now(),now())",
                (assigned_profile,),
            )
            connection.execute(
                "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,published_at,created_at,updated_at) VALUES (%s,1,'published',%s::jsonb,'digest',now(),now(),now())",
                (assigned_profile, assigned_config),
            )
            connection.execute(
                "INSERT INTO ima.kb_profile_assignments(kb_id,workflow,profile_id,profile_version,assigned_at) VALUES (%s,'grounded_ask',%s,1,now())",
                (kb_id, assigned_profile),
            )
            connection.commit()
        async with engine.connect() as conn:
            config = await search._profile(conn, kb_id)
            assert config.chat_model_id == str(assigned_model)
            assert config.system_prompt == "Assigned ground"
    finally:
        await engine.dispose()
        cleanup(
            kb_id=kb_id,
            workflows=("grounded_ask",),
            extra_profile_ids=(assigned_profile,),
            gateway_ids=(scene_gateway, assigned_gateway),
            actor_ids=("scene-ask-actor-3",),
        )
