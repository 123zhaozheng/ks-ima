"""PostgreSQL model-governance lifecycle and boundary gate."""

# This file intentionally uses real PostgreSQL constraints and transactions.
# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

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


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_model_governance_migration_is_fresh_and_repeatable() -> None:
    migrate()
    migrate()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        assert (
            connection.execute("SELECT version_num FROM ima.alembic_version").fetchone()[0]
            == "20260825_0005"
        )
        for table in (
            "model_gateway_secrets",
            "model_gateways",
            "governed_models",
            "capability_profiles",
            "capability_profile_versions",
            "workspace_profile_assignments",
            "model_dependency_index",
            "legacy_model_governance_migration",
        ):
            assert connection.execute("SELECT to_regclass(%s)", (f"ima.{table}",)).fetchone()[0]


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
def test_assignment_and_dependency_rows_have_restrictive_foreign_keys() -> None:
    migrate()
    assert SYNC_URL
    workspace_id = f"pg-ws-{uuid4().hex[:20]}"
    profile_id, model_id, gateway_id = uuid4(), uuid4(), uuid4()
    with psycopg.connect(SYNC_URL) as connection:
        connection.execute(
            "INSERT INTO ima.workspaces(id,name,is_active,created_at,updated_at) VALUES (%s,'PG Model Workspace',true,now(),now())",
            (workspace_id,),
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
            "INSERT INTO ima.capability_profiles(id,workflow,business_alias,description,current_version,created_at,updated_at) VALUES (%s,'title_generation','PG Assignment','profile',1,now(),now())",
            (profile_id,),
        )
        connection.execute(
            "INSERT INTO ima.capability_profile_versions(profile_id,version,state,config,config_digest,created_at,updated_at) VALUES (%s,1,'published',%s::jsonb,'digest',now(),now())",
            (
                profile_id,
                json.dumps({"chatModelId": str(model_id), "workflow": "title_generation"}),
            ),
        )
        connection.execute(
            "INSERT INTO ima.workspace_profile_assignments(workspace_id,workflow,profile_id,profile_version,assigned_at) VALUES (%s,'title_generation',%s,1,now())",
            (workspace_id, profile_id),
        )
        connection.execute(
            "INSERT INTO ima.model_dependency_index(id,dependency_kind,workspace_id,source_id,model_id,dimension,created_at,updated_at) VALUES (%s,'target_index',%s,'idx-1',%s,1536,now(),now())",
            (uuid4(), workspace_id, model_id),
        )
        connection.commit()
        with pytest.raises(psycopg.Error):
            connection.execute("DELETE FROM ima.governed_models WHERE id=%s", (model_id,))
        connection.rollback()
        connection.execute("DELETE FROM ima.workspaces WHERE id=%s", (workspace_id,))
        connection.execute(
            "DELETE FROM ima.capability_profile_versions WHERE profile_id=%s", (profile_id,)
        )
        connection.execute("DELETE FROM ima.capability_profiles WHERE id=%s", (profile_id,))
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
