"""Grounded-Ask profile resolution and automatic retrieval-index maintenance.

Scene-only resolution: every workflow's model comes from the platform scene
defaults, and ingestion/reconciliation keeps exact-model vector indexes current.
"""

# This file intentionally uses real PostgreSQL rows for the ask-profile path.
# ruff: noqa: E501

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
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
from ima.workers.main import reconcile_once

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
async def test_ask_profile_composes_scene_defaults() -> None:
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
async def test_ask_profile_denies_without_scene_default() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    seed_scene_actor("scene-ask-actor-2")
    # Shared dev database: ensure no grounded_ask scene default pre-exists.
    cleanup(workflows=("grounded_ask",))
    models, search, engine = scene_services()
    try:
        async with engine.connect() as conn:
            with pytest.raises(SearchError) as denied:
                await search._profile(conn, kb_id)
            assert (denied.value.status_code, denied.value.code) == (409, "NO_ASSIGNMENT")
    finally:
        await engine.dispose()
        cleanup(workflows=("grounded_ask",), actor_ids=("scene-ask-actor-2",))


class _IndexDeferSpy:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def defer_async(self, *, kb_id: str) -> None:
        self.calls.append(kb_id)


def seed_ready_chunk(kb_id: str, document_id: Any, model_id: Any, dimension: int) -> None:
    """Seed one isolated file document with a single ready exact-model chunk."""
    checksum, digest = "a" * 64, "b" * 64
    vector = "[" + ",".join(["0.1"] * dimension) + "]"
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Index KB',true,now(),now())",
            (kb_id,),
        )
        connection.execute(
            "INSERT INTO ima.folders(id,kb_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,created_at,updated_at) VALUES (%s,%s,NULL,'Root','root',0,'active',1,true,now(),now())",
            (kb_id, kb_id),
        )
        connection.execute(
            "INSERT INTO ima.documents(id,kb_id,folder_id,kind,title,normalized_title,current_version,file_state,created_at,updated_at) VALUES (%s,%s,%s,'file','Doc','Doc',1,'ready',now(),now())",
            (document_id, kb_id, kb_id),
        )
        connection.execute(
            "INSERT INTO ima.document_file_versions(document_id,version,kb_id,object_state,object_key,checksum,size_bytes,mime_type,original_filename,created_at) VALUES (%s,1,%s,'verified',%s,%s,11,'text/plain','doc.txt',now())",
            (document_id, kb_id, f"it/{kb_id}/{document_id}", checksum),
        )
        connection.execute(
            "INSERT INTO ima.document_derived_text(document_id,version,generation,parser_name,parser_version,source_checksum,text_digest,text_content,status,created_at) VALUES (%s,1,1,'test','1',%s,%s,'hello world','ready',now())",
            (document_id, checksum, digest),
        )
        connection.execute(
            "INSERT INTO ima.document_chunks(kb_id,document_id,version,generation,ordinal,text_content,content_digest,embedding_status,model_id,model_version,embedding_dimension,embedding,created_at,updated_at) VALUES (%s,%s,1,1,0,'hello world',%s,'ready',%s,1,%s,CAST(%s AS vector),now(),now())",
            (kb_id, document_id, digest, model_id, dimension, vector),
        )
        connection.commit()


def cleanup_index_fixtures(
    kb_id: str, *, workflows: tuple[str, ...] = (), gateway_ids: tuple[Any, ...] = ()
) -> None:
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute("DELETE FROM ima.chunk_search_indexes WHERE kb_id=%s", (kb_id,))
        connection.execute("DELETE FROM ima.document_chunks WHERE kb_id=%s", (kb_id,))
        connection.execute(
            "DELETE FROM ima.document_derived_text WHERE document_id IN (SELECT id FROM ima.documents WHERE kb_id=%s)",
            (kb_id,),
        )
        connection.execute("DELETE FROM ima.document_file_versions WHERE kb_id=%s", (kb_id,))
        connection.execute("DELETE FROM ima.documents WHERE kb_id=%s", (kb_id,))
        connection.execute("DELETE FROM ima.folders WHERE kb_id=%s", (kb_id,))
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
        connection.execute("DELETE FROM ima.knowledge_bases WHERE id=%s", (kb_id,))
        for gateway_id in gateway_ids:
            connection.execute("DELETE FROM ima.governed_models WHERE gateway_id=%s", (gateway_id,))
            connection.execute("DELETE FROM ima.model_gateways WHERE id=%s", (gateway_id,))
        connection.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_maintain_vector_index_builds_exact_scene_default_index() -> None:
    migrate()
    kb_id, document_id = f"pg-kb-{uuid4().hex[:20]}", uuid4()
    chat_gateway, chat_model = seed_healthy_model("chat")
    embed_gateway, embed_model = seed_healthy_model("embedding")
    seed_scene_actor("scene-index-actor-1")
    models, search, engine = scene_services()
    try:
        await models.set_scene_default("scene-index-actor-1", Workflow.GROUNDED_ASK, chat_model)
        await models.set_scene_default("scene-index-actor-1", Workflow.EMBEDDING, embed_model)
        seed_ready_chunk(kb_id, document_id, embed_model, 1536)
        async with engine.connect() as conn:
            config = await search._profile(conn, kb_id)
            with pytest.raises(SearchError) as missing:
                await search._vector_target(conn, kb_id, config)
            assert missing.value.code == "REINDEX_REQUIRED"
        assert kb_id in await search.kbs_missing_vector_index()

        built = await search.maintain_vector_index(kb_id)
        assert built is not None and built["status"] == "active"
        assert built["modelId"] == embed_model
        async with engine.connect() as conn:
            config = await search._profile(conn, kb_id)
            target = await search._vector_target(conn, kb_id, config)
            assert target["model_id"] == embed_model
        assert kb_id not in await search.kbs_missing_vector_index()
    finally:
        await engine.dispose()
        cleanup_index_fixtures(
            kb_id,
            workflows=("grounded_ask", "embedding"),
            gateway_ids=(chat_gateway, embed_gateway),
        )
        cleanup(actor_ids=("scene-index-actor-1",))


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_reconcile_heals_ready_chunks_without_an_active_index() -> None:
    migrate()
    kb_id, document_id = f"pg-kb-{uuid4().hex[:20]}", uuid4()
    gateway_id, model_id = seed_healthy_model("embedding")
    seed_scene_actor("scene-index-actor-2")
    models, search, engine = scene_services()
    try:
        await models.set_scene_default("scene-index-actor-2", Workflow.EMBEDDING, model_id)
        seed_ready_chunk(kb_id, document_id, model_id, 1536)
        spies = {"index": _IndexDeferSpy()}
        await reconcile_once(engine, spies, datetime.now(UTC), search)
        assert spies["index"].calls == [kb_id]

        # Once the index exists, reconciliation stops re-deferring the build.
        await search.maintain_vector_index(kb_id)
        second = {"index": _IndexDeferSpy()}
        await reconcile_once(engine, second, datetime.now(UTC), search)
        assert second["index"].calls == []
    finally:
        await engine.dispose()
        cleanup_index_fixtures(kb_id, workflows=("embedding",), gateway_ids=(gateway_id,))
        cleanup(actor_ids=("scene-index-actor-2",))
