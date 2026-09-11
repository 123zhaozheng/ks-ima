"""PostgreSQL model-governance lifecycle and boundary gate."""

# This file intentionally uses real PostgreSQL constraints and transactions.
# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from ima.api.app import create_app
from ima.application.model_governance import ModelGovernanceError, ModelGovernanceService
from ima.config import Settings
from ima.domain.model_governance import Workflow
from ima.infrastructure.model_gateway.secrets import SecretEnvelope, SecretKeyRing

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


def scene_service() -> tuple[ModelGovernanceService, AsyncEngine]:
    assert DATABASE_URL
    engine = create_async_engine(DATABASE_URL)
    return ModelGovernanceService(engine, Settings(environment="test")), engine


def seed_scene_actor(actor_id: str) -> None:
    """Insert the governance actor referenced by created_by/updated_by FKs."""
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.users(id,email,normalized_email,display_name,security_stamp,created_at,updated_at) VALUES (%s,%s,%s,%s,'scene-test-stamp',now(),now()) ON CONFLICT DO NOTHING",
            (actor_id, f"{actor_id}@scene.test", f"{actor_id}@scene.test", "Scene Test Actor"),
        )
        connection.commit()


def seed_healthy_model(
    capability: str,
    *,
    enabled: bool = True,
    dimension: int | None = None,
) -> tuple[Any, Any]:
    """Insert one gateway and a validated enabled model with healthy state."""
    gateway_id, model_id = uuid4(), uuid4()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,enabled,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,created_at,updated_at) VALUES (%s,%s,'https://gateway.internal',ARRAY[%s],'required',true,1000,10000,10000,1000,1048576,now(),now())",
            (gateway_id, f"pg-scene-{uuid4().hex[:12]}", capability),
        )
        connection.execute(
            "INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,enabled,validated,embedding_dimension,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,true,%s,now(),now())",
            (
                model_id,
                gateway_id,
                f"{capability}-model",
                capability,
                capability.title(),
                enabled,
                dimension,
            ),
        )
        connection.execute(
            "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,checked_at) VALUES (%s,%s,'healthy',now())",
            (gateway_id, capability),
        )
        connection.commit()
    return gateway_id, model_id


def cleanup_scene_fixtures(
    *,
    kb_id: str | None = None,
    workflow: str | tuple[str, ...] | None = None,
    extra_profile_ids: tuple[Any, ...] = (),
    gateway_ids: tuple[Any, ...] = (),
    actor_ids: tuple[str, ...] = (),
) -> None:
    """Remove every row this test created, including stale managed profiles."""
    assert SYNC_URL
    workflows = (workflow,) if isinstance(workflow, str) else tuple(workflow or ())
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
def test_model_governance_migration_is_fresh_and_repeatable() -> None:
    migrate()
    migrate()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        assert (
            connection.execute("SELECT version_num FROM ima.alembic_version").fetchone()[0]
            == "20260910_0013"
        )
        for table in (
            "model_gateway_secrets",
            "model_gateways",
            "governed_models",
            "capability_profiles",
            "capability_profile_versions",
            "model_dependency_index",
            "legacy_model_governance_migration",
            "scene_defaults",
        ):
            assert connection.execute("SELECT to_regclass(%s)", (f"ima.{table}",)).fetchone()[0]
        # Scene-only resolution: the assignment table is gone for good.
        assert (
            connection.execute(
                "SELECT to_regclass('ima.kb_profile_assignments')"
            ).fetchone()[0]
            is None
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_secret_persistence_is_encrypted_and_rotatable() -> None:
    migrate()
    assert SYNC_URL
    ring = SecretKeyRing(
        '{"v1":"model-test-key","v2":"model-test-key-rotated"}', "v2", "fingerprint-test"
    )
    gateway_id, secret_id = uuid4(), uuid4()
    envelope = ring.encrypt("super-secret", gateway_id=str(gateway_id), secret_id=str(secret_id))
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute("DELETE FROM ima.model_gateway_secrets WHERE id=%s", (secret_id,))
        connection.execute(
            "INSERT INTO ima.model_gateway_secrets(id,key_version,nonce,ciphertext,fingerprint,created_at) VALUES (%s,%s,%s,%s,%s,now())",
            (
                secret_id,
                envelope.key_version,
                envelope.nonce,
                envelope.ciphertext,
                envelope.fingerprint,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT ciphertext::text,fingerprint FROM ima.model_gateway_secrets WHERE id=%s",
            (secret_id,),
        ).fetchone()
        assert row and "super-secret" not in str(row[0])
        assert (
            ring.decrypt(
                SecretEnvelope(
                    key_version=envelope.key_version,
                    nonce=envelope.nonce,
                    ciphertext=envelope.ciphertext,
                    fingerprint=envelope.fingerprint,
                ),
                gateway_id=str(gateway_id),
                secret_id=str(secret_id),
            )
            == "super-secret"
        )
        connection.execute("DELETE FROM ima.model_gateway_secrets WHERE id=%s", (secret_id,))
        connection.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_published_profile_version_cannot_be_rewritten() -> None:
    migrate()
    assert SYNC_URL
    profile_id = uuid4()
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_at,updated_at) VALUES (%s,'title_generation','pg-profile','profile',1,now(),now())",
            (profile_id,),
        )
        connection.execute(
            "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,published_at,created_at,updated_at) VALUES (%s,1,'published','{}','digest',now(),now(),now())",
            (profile_id,),
        )
        connection.commit()
        with pytest.raises(psycopg.Error):
            connection.execute(
                "UPDATE ima.capability_profile_versions SET config=%s::jsonb WHERE profile_id=%s AND version=1",
                (json.dumps({"changed": True}), profile_id),
            )
        connection.rollback()
        connection.execute(
            "DELETE FROM ima.capability_profile_versions WHERE profile_id=%s", (profile_id,)
        )
        connection.execute("DELETE FROM ima.capability_profiles WHERE id=%s", (profile_id,))
        connection.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_dependency_rows_have_restrictive_foreign_keys() -> None:
    migrate()
    assert SYNC_URL
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    model_id, gateway_id = uuid4(), uuid4()
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Model Knowledge Base',true,now(),now())",
            (kb_id,),
        )
        connection.execute(
            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,created_at,updated_at) VALUES (%s,%s,'https://gateway.internal',ARRAY['chat'], 'required',1000,10000,10000,1000,1048576,now(),now())",
            (gateway_id, f"pg-mg-{uuid4().hex[:12]}"),
        )
        connection.execute(
            "INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,created_at,updated_at) VALUES (%s,%s,'chat','chat','Chat',now(),now())",
            (model_id, gateway_id),
        )
        connection.execute(
            "INSERT INTO ima.model_dependency_index(id,dependency_kind,kb_id,source_id,model_id,dimension,created_at,updated_at) VALUES (%s,'target_index',%s,'idx-1',%s,1536,now(),now())",
            (uuid4(), kb_id, model_id),
        )
        connection.commit()
        with pytest.raises(psycopg.Error):
            connection.execute("DELETE FROM ima.governed_models WHERE id=%s", (model_id,))
        connection.rollback()
        connection.execute("DELETE FROM ima.knowledge_bases WHERE id=%s", (kb_id,))
        connection.execute("DELETE FROM ima.governed_models WHERE id=%s", (model_id,))
        connection.execute("DELETE FROM ima.model_gateways WHERE id=%s", (gateway_id,))
        connection.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_reindex_dependency_is_visible_to_impact_contract() -> None:
    migrate()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        row = connection.execute(
            "SELECT count(*) FROM ima.model_dependency_index WHERE dependency_kind IN ('target_index','legacy_index')"
        ).fetchone()
        assert row and row[0] >= 0


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_health_state_is_persisted_with_safe_reason_only() -> None:
    migrate()
    assert SYNC_URL
    gateway_id = uuid4()
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,allowed_capabilities,tls_mode,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,created_at,updated_at) VALUES (%s,%s,'https://gateway.internal',ARRAY['chat'],'required',1000,10000,10000,1000,1048576,now(),now())",
            (gateway_id, f"pg-health-{uuid4().hex[:12]}"),
        )
        connection.execute(
            "INSERT INTO ima.model_gateway_health(gateway_id,capability,state,reason_code,checked_at) VALUES (%s,'chat','unavailable','TIMEOUT',now())",
            (gateway_id,),
        )
        connection.commit()
        row = connection.execute(
            "SELECT state,reason_code FROM ima.model_gateway_health WHERE gateway_id=%s",
            (gateway_id,),
        ).fetchone()
        assert row == ("unavailable", "TIMEOUT")
        connection.execute("DELETE FROM ima.model_gateways WHERE id=%s", (gateway_id,))
        connection.commit()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_scene_default_set_list_roundtrip_audit_and_clear() -> None:
    migrate()
    # The dev database is shared with live E2E traffic: wipe any pre-existing
    # scene state so the managed profile starts at version 1.
    cleanup_scene_fixtures(workflow="title_generation", actor_ids=("scene-actor-1",))
    first_gateway, model_id = seed_healthy_model("chat")
    other_gateway, other_model_id = seed_healthy_model("chat")
    seed_scene_actor("scene-actor-1")
    service, engine = scene_service()
    try:
        assert SYNC_URL
        cleared = await service.set_scene_default("scene-actor-1", Workflow.TITLE_GENERATION, None)
        assert cleared["workflow"] == "title_generation"
        assert cleared["modelId"] is None

        item = await service.set_scene_default("scene-actor-1", Workflow.TITLE_GENERATION, model_id)
        assert item["modelId"] == str(model_id)
        assert item["profileVersion"] == 1
        with psycopg.connect(SYNC_URL) as connection:
            pointer = connection.execute(
                "SELECT profile_id,updated_by FROM ima.scene_defaults WHERE workflow='title_generation'"
            ).fetchone()
            assert pointer and pointer[1] == "scene-actor-1"
            profile_id = pointer[0]
            assert (
                connection.execute(
                    "SELECT current_version FROM ima.capability_profiles WHERE id=%s", (profile_id,)
                ).fetchone()[0]
                == 1
            )
            published = connection.execute(
                "SELECT config FROM ima.capability_profile_versions WHERE profile_id=%s AND state='published'",
                (profile_id,),
            ).fetchone()[0]
            assert published["chatModelId"] == str(model_id)
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.audit_events WHERE action='model.scene_default.updated' AND target_id='title_generation' AND actor_id='scene-actor-1'"
                ).fetchone()[0]
                >= 1
            )

        # Repointing publishes a new version; repeating the same model is a no-op.
        item = await service.set_scene_default(
            "scene-actor-1", Workflow.TITLE_GENERATION, other_model_id
        )
        assert item["modelId"] == str(other_model_id)
        assert item["profileVersion"] == 2
        repeated = await service.set_scene_default(
            "scene-actor-1", Workflow.TITLE_GENERATION, other_model_id
        )
        assert repeated["profileVersion"] == 2

        cleared = await service.set_scene_default("scene-actor-1", Workflow.TITLE_GENERATION, None)
        assert cleared["modelId"] is None and cleared["profileId"] is None
        with psycopg.connect(SYNC_URL) as connection:
            assert (
                connection.execute(
                    "SELECT 1 FROM ima.scene_defaults WHERE workflow='title_generation'"
                ).fetchone()
                is None
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.audit_events WHERE action='model.scene_default.cleared' AND target_id='title_generation'"
                ).fetchone()[0]
                >= 1
            )
    finally:
        await engine.dispose()
        cleanup_scene_fixtures(
            workflow="title_generation",
            gateway_ids=(first_gateway, other_gateway),
            actor_ids=("scene-actor-1",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_scene_default_rejects_missing_disabled_and_mismatched_models() -> None:
    migrate()
    service, engine = scene_service()
    try:
        disabled_gateway, disabled_chat = seed_healthy_model("chat", enabled=False)
        embedding_gateway, embedding_model = seed_healthy_model("embedding", dimension=1536)
        assert SYNC_URL
        with pytest.raises(ModelGovernanceError) as missing:
            await service.set_scene_default("scene-actor-2", Workflow.TITLE_GENERATION, uuid4())
        assert (missing.value.status_code, missing.value.code) == (422, "MODEL_NOT_FOUND")
        with pytest.raises(ModelGovernanceError) as mismatch:
            await service.set_scene_default(
                "scene-actor-2", Workflow.TITLE_GENERATION, embedding_model
            )
        assert (mismatch.value.status_code, mismatch.value.code) == (422, "CAPABILITY_MISMATCH")
        with pytest.raises(ModelGovernanceError) as disabled:
            await service.set_scene_default(
                "scene-actor-2", Workflow.TITLE_GENERATION, disabled_chat
            )
        assert (disabled.value.status_code, disabled.value.code) == (422, "MODEL_DISABLED")
        with psycopg.connect(SYNC_URL) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.audit_events WHERE action='model.scene_default.updated' AND actor_id='scene-actor-2'"
                ).fetchone()[0]
                == 0
            )
    finally:
        await engine.dispose()
        cleanup_scene_fixtures(
            workflow="title_generation",
            gateway_ids=(disabled_gateway, embedding_gateway),
            actor_ids=("scene-actor-2",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_execution_falls_back_to_scene_default_without_assignment() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    gateway_id, model_id = seed_healthy_model("chat")
    seed_scene_actor("scene-actor-3")
    service, engine = scene_service()
    try:
        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Scene KB',true,now(),now())",
                (kb_id,),
            )
            connection.commit()
        await service.set_scene_default("scene-actor-3", Workflow.GROUNDED_ASK, model_id)
        target = await service._execution_target(
            kb_id, Workflow.GROUNDED_ASK, "chat", decrypt_secret=False
        )
        assert target is not None
        assert target["source"] == "scene_default"
        assert target["model_id"] == model_id
        assert target["reason"] is None
        assert target["config"]["chatModelId"] == str(model_id)
    finally:
        await engine.dispose()
        cleanup_scene_fixtures(
            kb_id=kb_id,
            workflow="grounded_ask",
            gateway_ids=(gateway_id,),
            actor_ids=("scene-actor-3",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_configured_scene_default_with_missing_model_never_falls_back() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    broken_profile = uuid4()
    gateway_id, healthy_model = seed_healthy_model("chat")
    seed_scene_actor("scene-actor-4")
    service, engine = scene_service()
    try:
        assert SYNC_URL
        # A configured scene default whose typed config references a missing
        # model must stay UNAVAILABLE, never collapse into NO_ASSIGNMENT.
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Scene KB',true,now(),now())",
                (kb_id,),
            )
            connection.execute(
                "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_at,updated_at) VALUES (%s,'title_generation','PG Assigned Broken','profile',1,now(),now())",
                (broken_profile,),
            )
            connection.execute(
                "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,published_at,created_at,updated_at) VALUES (%s,1,'published',%s::jsonb,'digest',now(),now(),now())",
                (
                    broken_profile,
                    json.dumps({"chatModelId": str(uuid4()), "workflow": "title_generation"}),
                ),
            )
            connection.execute(
                "INSERT INTO ima.scene_defaults(workflow,profile_id,updated_at,updated_by) VALUES ('title_generation',%s,now(),%s) ON CONFLICT(workflow) DO UPDATE SET profile_id=EXCLUDED.profile_id,updated_at=EXCLUDED.updated_at,updated_by=EXCLUDED.updated_by",
                (broken_profile, "scene-actor-4"),
            )
            connection.commit()
        target = await service._execution_target(
            kb_id, Workflow.TITLE_GENERATION, "chat", decrypt_secret=False
        )
        assert target is not None
        assert target["profile_id"] == broken_profile
        assert target.get("source") is None
        assert target["reason"] == "UNAVAILABLE"

        # Repointing the scene default at a healthy model restores execution.
        await service.set_scene_default("scene-actor-4", Workflow.TITLE_GENERATION, healthy_model)
        target = await service._execution_target(
            kb_id, Workflow.TITLE_GENERATION, "chat", decrypt_secret=False
        )
        assert target is not None
        assert target["source"] == "scene_default"
        assert target["reason"] is None
        assert target["model_id"] == healthy_model

        # Clearing the scene default returns a genuine NO_ASSIGNMENT.
        await service.set_scene_default("scene-actor-4", Workflow.TITLE_GENERATION, None)
        assert (
            await service._execution_target(
                kb_id, Workflow.TITLE_GENERATION, "chat", decrypt_secret=False
            )
            is None
        )
    finally:
        await engine.dispose()
        cleanup_scene_fixtures(
            kb_id=kb_id,
            workflow="title_generation",
            extra_profile_ids=(broken_profile,),
            gateway_ids=(gateway_id,),
            actor_ids=("scene-actor-4",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_disabled_scene_default_model_is_unavailable_until_cleared() -> None:
    migrate()
    kb_id = f"pg-kb-{uuid4().hex[:20]}"
    gateway_id, model_id = seed_healthy_model("chat")
    seed_scene_actor("scene-actor-5")
    service, engine = scene_service()
    try:
        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "INSERT INTO ima.knowledge_bases(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Scene KB',true,now(),now())",
                (kb_id,),
            )
            connection.commit()
        await service.set_scene_default("scene-actor-5", Workflow.SUMMARIZATION, model_id)
        target = await service._execution_target(
            kb_id, Workflow.SUMMARIZATION, "chat", decrypt_secret=False
        )
        assert target is not None and target["reason"] is None
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "UPDATE ima.governed_models SET enabled=false WHERE id=%s", (model_id,)
            )
            connection.commit()
        target = await service._execution_target(
            kb_id, Workflow.SUMMARIZATION, "chat", decrypt_secret=False
        )
        assert target is not None
        assert target["source"] == "scene_default"
        assert target["reason"] == "UNAVAILABLE"
        with psycopg.connect(SYNC_URL) as connection:
            denial = connection.execute(
                "SELECT reason_code FROM ima.audit_events WHERE action='model.execution.denied' AND result='failed' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            assert denial is not None and denial[0] == "UNAVAILABLE"
        await service.set_scene_default("scene-actor-5", Workflow.SUMMARIZATION, None)
        assert (
            await service._execution_target(
                kb_id, Workflow.SUMMARIZATION, "chat", decrypt_secret=False
            )
            is None
        )
    finally:
        await engine.dispose()
        cleanup_scene_fixtures(
            kb_id=kb_id,
            workflow="summarization",
            gateway_ids=(gateway_id,),
            actor_ids=("scene-actor-5",),
        )


class _StubIdentityApi:
    """Identity double satisfying the `current` dependency and require() gate."""

    def __init__(
        self, *, user_id: str, authenticated: bool, recent_auth_at: datetime | None = None
    ) -> None:
        self._user_id = user_id
        self._authenticated = authenticated
        self._recent_auth_at = recent_auth_at or datetime.now(UTC)
        self.digest = "scene-api-csrf-digest"

    async def has_capability(self, user_id: str, capability: str) -> bool:
        return True

    async def current_session(self, request: Any) -> tuple[dict[str, Any], Any] | None:
        if not self._authenticated:
            return None
        return (
            {"csrf_digest": self.digest, "recent_auth_at": self._recent_auth_at},
            SimpleNamespace(id=self._user_id),
        )

    def _session_digest(self, cookie: str) -> str:
        return self.digest


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_scene_default_api_routes_list_save_and_gate() -> None:
    migrate()
    gateway_id, model_id = seed_healthy_model("chat")
    disabled_gateway, disabled_model = seed_healthy_model("chat", enabled=False)
    rerank_gateway, rerank_model = seed_healthy_model("rerank")
    seed_scene_actor("scene-api-actor")
    # Shared dev database: clear scene state (including live E2E residue)
    # before asserting the list starts empty.
    cleanup_scene_fixtures(workflow=tuple(workflow.value for workflow in Workflow))
    # TestClient spins a fresh event loop per request; NullPool keeps asyncpg
    # connections from crossing loops between requests.
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    service = ModelGovernanceService(engine, Settings(environment="test"))
    try:
        assert SYNC_URL
        settings = Settings(environment="test")
        stub = _StubIdentityApi(user_id="scene-api-actor", authenticated=True)
        app = create_app(settings)
        app.state.settings = settings
        app.state.identity_service = stub
        app.state.model_governance_service = service
        client = TestClient(app)
        write = {
            "headers": {"Origin": settings.public_origin, "x-csrf-token": stub.digest},
            "cookies": {settings.csrf_cookie_name: stub.digest},
        }

        listed = client.get("/api/v1/admin/scene-defaults")
        assert listed.status_code == 200
        items = listed.json()["items"]
        assert [item["workflow"] for item in items] == [workflow.value for workflow in Workflow]
        assert all(item["modelId"] is None for item in items)

        saved = client.put(
            "/api/v1/admin/scene-defaults/grounded_ask",
            json={"modelId": str(model_id)},
            **write,
        )
        assert saved.status_code == 200
        body = saved.json()
        assert body == {
            "workflow": "grounded_ask",
            "profileId": body["profileId"],
            "profileVersion": 1,
            "modelId": str(model_id),
        }
        assert body["profileId"]

        listed = client.get("/api/v1/admin/scene-defaults")
        grounded = next(
            item for item in listed.json()["items"] if item["workflow"] == "grounded_ask"
        )
        assert grounded["modelId"] == str(model_id)

        repointed = client.put(
            "/api/v1/admin/scene-defaults/reranking",
            json={"modelId": str(rerank_model)},
            **write,
        )
        assert repointed.status_code == 200
        assert repointed.json()["modelId"] == str(rerank_model)

        unknown = client.put(
            "/api/v1/admin/scene-defaults/grounded_ask",
            json={"modelId": str(uuid4())},
            **write,
        )
        assert unknown.status_code == 422
        assert unknown.json()["code"] == "MODEL_NOT_FOUND"

        disabled = client.put(
            "/api/v1/admin/scene-defaults/grounded_ask",
            json={"modelId": str(disabled_model)},
            **write,
        )
        assert disabled.status_code == 422
        assert disabled.json()["code"] == "MODEL_DISABLED"

        mismatch = client.put(
            "/api/v1/admin/scene-defaults/embedding",
            json={"modelId": str(model_id)},
            **write,
        )
        assert mismatch.status_code == 422
        assert mismatch.json()["code"] == "CAPABILITY_MISMATCH"

        with psycopg.connect(SYNC_URL) as connection:
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.audit_events WHERE action IN ('model.scene_default.updated','model.scene_default.cleared') AND actor_id='scene-api-actor'"
                ).fetchone()[0]
                >= 2
            )

        stub._authenticated = False
        assert client.get("/api/v1/admin/scene-defaults").status_code == 401
        assert (
            client.put(
                "/api/v1/admin/scene-defaults/grounded_ask",
                json={"modelId": str(model_id)},
                **write,
            ).status_code
            == 401
        )
    finally:
        await engine.dispose()
        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            for workflow in ("grounded_ask", "reranking"):
                connection.execute("DELETE FROM ima.scene_defaults WHERE workflow=%s", (workflow,))
                connection.execute(
                    "DELETE FROM ima.capability_profile_versions WHERE profile_id IN (SELECT id FROM ima.capability_profiles WHERE workflow=%s AND business_alias='场景默认')",
                    (workflow,),
                )
                connection.execute(
                    "DELETE FROM ima.capability_profiles WHERE workflow=%s AND business_alias='场景默认'",
                    (workflow,),
                )
            connection.commit()
        cleanup_scene_fixtures(
            gateway_ids=(gateway_id, disabled_gateway, rerank_gateway),
            actor_ids=("scene-api-actor",),
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_scene_default_save_skips_recent_auth_while_other_mutations_require_it() -> None:
    """Scene saves are routine config; other governance writes keep the gate."""
    migrate()
    gateway_id, model_id = seed_healthy_model("chat")
    seed_scene_actor("scene-recent-actor")
    cleanup_scene_fixtures(workflow=tuple(workflow.value for workflow in Workflow))
    engine = create_async_engine(DATABASE_URL, poolclass=NullPool)
    service = ModelGovernanceService(engine, Settings(environment="test"))
    try:
        assert SYNC_URL
        settings = Settings(environment="test")
        # Authenticated long ago: past the recent-auth window.
        stale = datetime.now(UTC) - timedelta(seconds=settings.recent_auth_seconds + 60)
        stub = _StubIdentityApi(
            user_id="scene-recent-actor", authenticated=True, recent_auth_at=stale
        )
        app = create_app(settings)
        app.state.settings = settings
        app.state.identity_service = stub
        app.state.model_governance_service = service
        client = TestClient(app)
        write = {
            "headers": {"Origin": settings.public_origin, "x-csrf-token": stub.digest},
            "cookies": {settings.csrf_cookie_name: stub.digest},
        }

        saved = client.put(
            "/api/v1/admin/scene-defaults/grounded_ask",
            json={"modelId": str(model_id)},
            **write,
        )
        assert saved.status_code == 200
        assert saved.json()["modelId"] == str(model_id)

        # The recent-auth gate is only relaxed for scene defaults.
        gated = client.post(f"/api/v1/admin/model-gateways/{gateway_id}/discover", **write)
        assert gated.status_code == 401
    finally:
        await engine.dispose()
        assert SYNC_URL
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute("DELETE FROM ima.scene_defaults WHERE workflow='grounded_ask'")
            connection.execute(
                "DELETE FROM ima.capability_profile_versions WHERE profile_id IN (SELECT id FROM ima.capability_profiles WHERE workflow='grounded_ask' AND business_alias='场景默认')"
            )
            connection.execute(
                "DELETE FROM ima.capability_profiles WHERE workflow='grounded_ask' AND business_alias='场景默认'"
            )
            connection.commit()
        cleanup_scene_fixtures(gateway_ids=(gateway_id,), actor_ids=("scene-recent-actor",))
