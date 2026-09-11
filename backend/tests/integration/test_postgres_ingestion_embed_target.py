"""Embedding target resolution for ingestion: the scene default is the only source.

The ingestion ``embed`` stage must resolve its embedding model through the same
governed resolver retrieval uses.  These tests exercise
``ModelGovernanceService.embedding_target`` directly against real PostgreSQL
rows (no mocks, no network).
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ima.application.model_governance import ModelGovernanceService
from ima.config import Settings

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None
ALEMBIC_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") if DATABASE_URL else None
)
EMBEDDING_DIMENSION = 1536


def migrate() -> None:
    assert ALEMBIC_URL
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env={**os.environ, "IMA_DATABASE_URL": ALEMBIC_URL},
        check=True,
    )


def seed_embedding_model() -> tuple[UUID, UUID]:
    """Seed an enabled, validated, healthy embedding model behind a gateway."""
    gateway_id, model_id = uuid4(), uuid4()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,enabled,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,created_at,updated_at) VALUES (%s,%s,'https://gateway.internal',ARRAY['embedding'],'required',true,1000,10000,10000,1000,1048576,now(),now())",
            (gateway_id, f"pg-embed-{uuid4().hex[:12]}"),
        )
        connection.execute(
            "INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,enabled,validated,embedding_dimension,created_at,updated_at) VALUES (%s,%s,%s,'embedding','Embedding',true,true,%s,now(),now())",
            (model_id, gateway_id, f"embedding-{uuid4().hex[:8]}", EMBEDDING_DIMENSION),
        )
        connection.execute(
            "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,checked_at) VALUES (%s,'embedding','healthy',now())",
            (gateway_id,),
        )
        connection.commit()
    return gateway_id, model_id


def seed_scene_default(model_id: UUID) -> UUID:
    """Create a dedicated embedding profile/version and point scene_defaults at it.

    A dedicated alias avoids touching the singleton ``场景默认`` profile an
    operator may have configured in the shared dev database.
    """
    profile_id = uuid4()
    config = {
        "workflow": "embedding",
        "embeddingModelId": str(model_id),
        "dimension": EMBEDDING_DIMENSION,
    }
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_at,updated_at) VALUES (%s,'embedding',%s,'test scene default',1,now(),now())",
            (profile_id, f"pg-embed-scene-{profile_id.hex[:8]}"),
        )
        connection.execute(
            "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,published_at,created_at,updated_at) VALUES (%s,1,'published',%s::jsonb,'digest',now(),now(),now())",
            (profile_id, json.dumps(config)),
        )
        connection.execute(
            "INSERT INTO ima.scene_defaults(workflow,profile_id,updated_at) VALUES ('embedding',%s,now()) ON CONFLICT(workflow) DO UPDATE SET profile_id=EXCLUDED.profile_id,updated_at=EXCLUDED.updated_at",
            (profile_id,),
        )
        connection.commit()
    return profile_id


def snapshot_scene_default(workflow: str) -> tuple[Any, Any, Any] | None:
    """Capture the shared row so a test can restore an operator's configuration."""
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        row = connection.execute(
            "SELECT profile_id,updated_at,updated_by FROM ima.scene_defaults WHERE workflow=%s",
            (workflow,),
        ).fetchone()
    return row


def restore_scene_default(
    workflow: str, snapshot: tuple[Any, Any, Any] | None, owned_profile: UUID | None
) -> None:
    """Remove the test's pointer and put the operator's pointer back, if any."""
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        if owned_profile is not None:
            connection.execute(
                "DELETE FROM ima.scene_defaults WHERE workflow=%s AND profile_id=%s",
                (workflow, owned_profile),
            )
        else:
            connection.execute("DELETE FROM ima.scene_defaults WHERE workflow=%s", (workflow,))
        if snapshot:
            connection.execute(
                "INSERT INTO ima.scene_defaults(workflow,profile_id,updated_at,updated_by) VALUES (%s,%s,%s,%s) ON CONFLICT(workflow) DO UPDATE SET profile_id=EXCLUDED.profile_id,updated_at=EXCLUDED.updated_at,updated_by=EXCLUDED.updated_by",
                (workflow, snapshot[0], snapshot[1], snapshot[2]),
            )
        connection.commit()


def cleanup(
    *,
    kb_ids: tuple[str, ...] = (),
    profile_ids: tuple[UUID, ...] = (),
    gateway_ids: tuple[UUID, ...] = (),
) -> None:
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        for profile_id in profile_ids:
            connection.execute(
                "DELETE FROM ima.capability_profile_versions WHERE profile_id=%s", (profile_id,)
            )
            connection.execute("DELETE FROM ima.capability_profiles WHERE id=%s", (profile_id,))
        for kb_id in kb_ids:
            connection.execute("DELETE FROM ima.knowledge_bases WHERE id=%s", (kb_id,))
        for gateway_id in gateway_ids:
            connection.execute("DELETE FROM ima.governed_models WHERE gateway_id=%s", (gateway_id,))
            connection.execute("DELETE FROM ima.model_gateways WHERE id=%s", (gateway_id,))
        connection.commit()


def service() -> tuple[ModelGovernanceService, AsyncEngine]:
    assert DATABASE_URL
    engine = create_async_engine(DATABASE_URL)
    return ModelGovernanceService(engine, Settings(environment="test")), engine


pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")


@pytest.mark.postgres
async def test_embedding_target_resolves_scene_default_with_version_and_dimension() -> None:
    migrate()
    kb_id = f"pg-embed-{uuid4().hex[:16]}"
    gateway_id, model_id = seed_embedding_model()
    snapshot = snapshot_scene_default("embedding")
    profile_id = seed_scene_default(model_id)
    models, engine = service()
    try:
        target = await models.embedding_target(kb_id)
        assert target is not None
        assert target["model_id"] == model_id
        assert target["model_version"] == 1
        assert target["embedding_dimension"] == EMBEDDING_DIMENSION
        assert target["source"] == "scene_default"
        assert target["reason"] is None
    finally:
        await engine.dispose()
        restore_scene_default("embedding", snapshot, profile_id)
        cleanup(profile_ids=(profile_id,), gateway_ids=(gateway_id,))


@pytest.mark.postgres
async def test_embedding_target_is_none_without_scene_default() -> None:
    migrate()
    kb_id = f"pg-embed-{uuid4().hex[:16]}"
    snapshot = snapshot_scene_default("embedding")
    # Take the shared pointer out of the way for the duration of the assertion.
    restore_scene_default("embedding", None, None)
    models, engine = service()
    try:
        assert await models.embedding_target(kb_id) is None
    finally:
        await engine.dispose()
        restore_scene_default("embedding", snapshot, None)


@pytest.mark.postgres
async def test_embedding_target_reports_unavailable_when_scene_default_model_is_disabled() -> None:
    migrate()
    kb_id = f"pg-embed-{uuid4().hex[:16]}"
    gateway_id, model_id = seed_embedding_model()
    snapshot = snapshot_scene_default("embedding")
    profile_id = seed_scene_default(model_id)
    models, engine = service()
    try:
        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "UPDATE ima.governed_models SET enabled=false,updated_at=now() WHERE id=%s",
                (model_id,),
            )
            connection.commit()
        target = await models.embedding_target(kb_id)
        assert target is not None
        assert target["reason"] == "UNAVAILABLE"
        assert target["model_id"] == model_id
    finally:
        await engine.dispose()
        restore_scene_default("embedding", snapshot, profile_id)
        cleanup(profile_ids=(profile_id,), gateway_ids=(gateway_id,))
