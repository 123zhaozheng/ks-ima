"""PostgreSQL OAuth/MCP repository gate.

These tests exercise the digest-only repository directly against the real
database: one-time authorization-code behavior, refresh rotation/replay family
revocation, finite service-credential expiry, credential rotation/replacement,
rate buckets, and safe audit payloads.  They are mandatory in the Compose gate.
Grants and service principals are user-level; there is no per-knowledge-base
grant boundary anymore.
"""

# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from ima.config import Settings
from ima.domain.oauth import AuthorizationTokenBundle, GrantRecord
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.oauth import McpOauthRepository, McpRepositoryError

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
RESOURCE = "https://ima.test/mcp"
SCOPES_READ = ("mcp:knowledge:read", "mcp:knowledge-bases:read")
CLIENT_OPERATOR_ID = "oauth-client-operator"


def integration_settings() -> Settings:
    assert DATABASE_URL is not None
    return Settings(
        environment="test",
        public_origin="https://ima.test",
        database_url=DATABASE_URL,
        session_pepper="oauth-integration-session",
        token_pepper="oauth-integration-token",
        totp_encryption_key="oauth-integration-key",
        smtp_host=None,
        smtp_from=None,
    )


async def run_migrations_once() -> None:
    """Run alembic upgrade twice; the second run must be idempotent."""
    assert DATABASE_URL is not None
    root = Path(__file__).parents[2]
    env = {
        **os.environ,
        "IMA_DATABASE_URL": DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://"),
    }
    subprocess.run(  # noqa: ASYNC221
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
    )
    subprocess.run(  # noqa: ASYNC221
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
    )


async def create_fixture(engine: object) -> str:
    """Create the platform and client-operator actors for the OAuth fixture."""
    admin_id = "oauth-admin"
    now = datetime.now(UTC)
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id=:id"), {"id": admin_id}
        )
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id=:id"), {"id": CLIENT_OPERATOR_ID}
        )
        await conn.execute(text("DELETE FROM ima.users WHERE id=:id"), {"id": admin_id})
        await conn.execute(
            text(
                "INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"
            ),
            {"id": admin_id, "email": "oauth-admin@example.test", "stamp": admin_id, "now": now},
        )
        await conn.execute(
            text(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (:id,'platform_admin',:now)"
            ),
            {"id": admin_id, "now": now},
        )
        await conn.execute(
            text(
                "INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"
            ),
            {
                "id": CLIENT_OPERATOR_ID,
                "email": "oauth-client-operator@example.test",
                "stamp": CLIENT_OPERATOR_ID,
                "now": now,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (:id,'super_admin',:now)"
            ),
            {"id": CLIENT_OPERATOR_ID, "now": now},
        )
    return admin_id


async def cleanup(engine: object, admin_id: str) -> None:
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text(
                """DELETE FROM ima.mcp_access_tokens WHERE grant_id IN
                (SELECT id FROM ima.mcp_grants WHERE user_id=:uid)
                OR principal_id IN
                (SELECT id FROM ima.mcp_service_principals WHERE owner_user_id=:uid)"""
            ),
            {"uid": admin_id},
        )
        await conn.execute(
            text(
                "DELETE FROM ima.mcp_refresh_tokens WHERE grant_id IN (SELECT id FROM ima.mcp_grants WHERE user_id=:uid)"
            ),
            {"uid": admin_id},
        )
        await conn.execute(
            text(
                "DELETE FROM ima.mcp_refresh_families WHERE grant_id IN (SELECT id FROM ima.mcp_grants WHERE user_id=:uid)"
            ),
            {"uid": admin_id},
        )
        await conn.execute(
            text(
                "DELETE FROM ima.mcp_authorization_codes WHERE grant_id IN (SELECT id FROM ima.mcp_grants WHERE user_id=:uid)"
            ),
            {"uid": admin_id},
        )
        await conn.execute(
            text(
                "DELETE FROM ima.mcp_credentials WHERE principal_id IN (SELECT id FROM ima.mcp_service_principals WHERE owner_user_id=:uid)"
            ),
            {"uid": admin_id},
        )
        await conn.execute(
            text("DELETE FROM ima.mcp_service_principals WHERE owner_user_id=:uid"),
            {"uid": admin_id},
        )
        await conn.execute(text("DELETE FROM ima.mcp_grants WHERE user_id=:uid"), {"uid": admin_id})
        await conn.execute(
            text(
                "DELETE FROM ima.mcp_client_redirects WHERE client_id IN (SELECT id FROM ima.mcp_clients WHERE created_by=:id)"
            ),
            {"id": CLIENT_OPERATOR_ID},
        )
        await conn.execute(
            text("DELETE FROM ima.mcp_clients WHERE created_by=:id"),
            {"id": CLIENT_OPERATOR_ID},
        )
        await conn.execute(
            text(
                "DELETE FROM ima.audit_events WHERE actor_id IN (:admin,:operator) OR target_id IN (:admin,:operator)"
            ),
            {"admin": admin_id, "operator": CLIENT_OPERATOR_ID},
        )
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id=:id"),
            {"id": admin_id},
        )
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id=:id"),
            {"id": CLIENT_OPERATOR_ID},
        )
        await conn.execute(text("DELETE FROM ima.users WHERE id=:id"), {"id": admin_id})
        await conn.execute(text("DELETE FROM ima.users WHERE id=:id"), {"id": CLIENT_OPERATOR_ID})


async def build_human_grant(
    repository: McpOauthRepository, user_id: str
) -> tuple[UUID, GrantRecord]:
    """Register a public desktop client and approve a user-level human grant."""
    client_uuid = await repository.register_client(
        client_id="desktop-1",
        client_name="Test Desktop",
        client_type="public",
        token_endpoint_auth_method="none",
        application_type="native",
        canonical_resource=RESOURCE,
        redirect_uris=("http://localhost:8765/callback",),
        created_by=CLIENT_OPERATOR_ID,
    )
    grant = await repository.upsert_grant(
        user_id=user_id,
        client_id=client_uuid,
        canonical_resource=RESOURCE,
        scopes=SCOPES_READ,
        expires_at=datetime.now(UTC) + timedelta(days=31),
        consent_granted_by=user_id,
    )
    return client_uuid, grant


async def issue_human_token_bundle(
    repository: McpOauthRepository, grant: GrantRecord, client_uuid: UUID, user_id: str
) -> AuthorizationTokenBundle:
    raw_code, _ = await repository.create_authorization_code(
        grant_id=grant.id,
        user_id=user_id,
        client_id=client_uuid,
        redirect_uri="http://localhost:8765/callback",
        canonical_resource=RESOURCE,
        scopes=grant.scopes,
        code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        security_stamp=user_id,
        state=f"refresh-fixture-{uuid4()}",
        expires_at=datetime.now(UTC) + timedelta(seconds=60),
    )
    return await repository.exchange_authorization_code_bundle(
        raw_code,
        expected_client_id=client_uuid,
        expected_redirect_uri="http://localhost:8765/callback",
        expected_resource=RESOURCE,
        expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
    )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_mcp_client_registration_requires_active_super_admin_and_attributes_audit() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)

    async def register(created_by: str | None) -> UUID:
        return await repository.register_client(
            client_id=f"operator-check-{uuid4()}",
            client_name="Operator Check",
            client_type="public",
            token_endpoint_auth_method="none",
            application_type="native",
            canonical_resource=RESOURCE,
            redirect_uris=("http://localhost:8765/operator-callback",),
            created_by=created_by,
        )

    try:
        with pytest.raises(PermissionError):
            await register(None)
        with pytest.raises(PermissionError):
            await register(admin_id)

        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.users SET is_active=false,disabled_at=now() WHERE id=:id"),
                {"id": CLIENT_OPERATOR_ID},
            )
        with pytest.raises(PermissionError):
            await register(CLIENT_OPERATOR_ID)

        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.users SET is_active=true,disabled_at=NULL WHERE id=:id"),
                {"id": CLIENT_OPERATOR_ID},
            )
        client_uuid = await register(CLIENT_OPERATOR_ID)
        async with engine.connect() as conn:
            client_actor = await conn.scalar(
                text("SELECT created_by FROM ima.mcp_clients WHERE id=:id"),
                {"id": client_uuid},
            )
            audit_actor = await conn.scalar(
                text(
                    "SELECT actor_id FROM ima.audit_events WHERE action='oauth.client.registered' AND target_id=:id"
                ),
                {"id": str(client_uuid)},
            )
        assert client_actor == CLIENT_OPERATOR_ID
        assert audit_actor == CLIENT_OPERATOR_ID
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_schema_digest_only_and_one_time_code() -> None:
    """Fresh/repeat migration, ima catalog, digest-only storage, one-time code."""
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        async with engine.connect() as conn:
            # New tables exist in ima.
            for table in (
                "mcp_clients",
                "mcp_client_redirects",
                "mcp_grants",
                "mcp_authorization_codes",
                "mcp_access_tokens",
                "mcp_refresh_families",
                "mcp_refresh_tokens",
                "mcp_service_principals",
                "mcp_credentials",
                "mcp_rate_buckets",
                "mcp_concurrency_leases",
            ):
                assert await conn.scalar(
                    text("SELECT to_regclass(:name)"),
                    {"name": f"ima.{table}"},
                ), f"missing ima.{table}"
            assert await conn.scalar(
                text("SELECT to_regclass('ima.ix_mcp_concurrency_source_expiry')")
            )

        client_uuid, grant = await build_human_grant(repository, admin_id)
        # User-level grants never carry a knowledge base binding.
        assert grant.kb_id is None
        raw_code, code = await repository.create_authorization_code(
            grant_id=grant.id,
            user_id=admin_id,
            client_id=client_uuid,
            redirect_uri="http://localhost:8765/callback",
            canonical_resource=RESOURCE,
            scopes=SCOPES_READ,
            code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            security_stamp=admin_id,
            state="state-abc",
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )
        async with engine.connect() as conn:
            stored_digest = await conn.scalar(
                text("SELECT code_digest FROM ima.mcp_authorization_codes WHERE id=:id"),
                {"id": code.id},
            )
            assert stored_digest == repository._token_digest(raw_code)
            assert stored_digest != raw_code
            assert raw_code not in str(stored_digest)

        # A verifier mismatch is audited but must not consume the code.
        with pytest.raises(McpRepositoryError) as mismatch:
            await repository.consume_authorization_code(
                raw_code,
                expected_client_id=client_uuid,
                expected_redirect_uri="http://localhost:8765/callback",
                expected_resource=RESOURCE,
                expected_code_challenge="wrong-challenge",
            )
        assert mismatch.value.reason == "verifier_mismatch"

        # A current-user security-state mismatch is rejected without consuming the code.
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.users SET security_stamp='changed-stamp' WHERE id=:id"),
                {"id": admin_id},
            )
        with pytest.raises(McpRepositoryError) as stale_stamp:
            await repository.consume_authorization_code(
                raw_code,
                expected_client_id=client_uuid,
                expected_redirect_uri="http://localhost:8765/callback",
                expected_resource=RESOURCE,
                expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            )
        assert stale_stamp.value.reason == "invalid_grant"
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.users SET security_stamp=:stamp WHERE id=:id"),
                {"id": admin_id, "stamp": admin_id},
            )

        # First exchange succeeds and consumes the code atomically.
        consumed = await repository.consume_authorization_code(
            raw_code,
            expected_client_id=client_uuid,
            expected_redirect_uri="http://localhost:8765/callback",
            expected_resource=RESOURCE,
            expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        )
        assert consumed.user_id == admin_id

        # Second exchange of the same code is rejected and revokes the grant.
        with pytest.raises(McpRepositoryError) as exc:
            await repository.consume_authorization_code(
                raw_code,
                expected_client_id=client_uuid,
                expected_redirect_uri="http://localhost:8765/callback",
                expected_resource=RESOURCE,
                expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            )
        assert exc.value.reason in ("used_code", "invalid_code")
        async with engine.connect() as conn:
            grant_state = await conn.scalar(
                text("SELECT state FROM ima.mcp_grants WHERE id=:id"), {"id": grant.id}
            )
            assert grant_state == "revoked"
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_refresh_rotation_replay_family_revoke_and_narrowing() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        issued = await issue_human_token_bundle(repository, grant, client_uuid, admin_id)
        raw_refresh, refresh = issued.refresh_token, issued.refresh
        async with engine.connect() as conn:
            family_absolute = await conn.scalar(
                text("SELECT absolute_expires_at FROM ima.mcp_refresh_families WHERE id=:id"),
                {"id": refresh.family_id},
            )
        assert isinstance(family_absolute, datetime)
        async with engine.connect() as conn:
            stored_digest = await conn.scalar(
                text("SELECT token_digest FROM ima.mcp_refresh_tokens WHERE id=:id"),
                {"id": refresh.id},
            )
            assert stored_digest == repository._token_digest(raw_refresh)
            assert stored_digest != raw_refresh

        # Narrowing is allowed; widening is rejected before any write.
        bundle = await repository.exchange_refresh_token_bundle(
            raw_refresh,
            expected_client_id=client_uuid,
            expected_resource=RESOURCE,
            requested_scopes=("mcp:knowledge:read",),
        )
        new_raw, grant_after = bundle.refresh_token, bundle.grant
        assert set(grant_after.scopes) == set(SCOPES_READ)
        assert bundle.access.scopes == ("mcp:knowledge:read",)
        assert bundle.refresh.scopes == ("mcp:knowledge:read",)
        assert bundle.access.expires_at <= grant.expires_at
        assert bundle.refresh.expires_at <= family_absolute
        assert bundle.access.expires_at <= datetime.now(UTC) + timedelta(
            seconds=settings.oauth_access_token_seconds
        )
        assert bundle.refresh.expires_at <= datetime.now(UTC) + timedelta(
            seconds=settings.oauth_refresh_rolling_seconds
        )
        assert new_raw not in repr(bundle) and bundle.access_token not in repr(bundle)
        async with engine.connect() as conn:
            persisted = (
                (
                    await conn.execute(
                        text(
                            "SELECT token_digest FROM ima.mcp_refresh_tokens WHERE id=:refresh UNION ALL SELECT token_digest FROM ima.mcp_access_tokens WHERE id=:access"
                        ),
                        {"refresh": bundle.refresh.id, "access": bundle.access.id},
                    )
                )
                .scalars()
                .all()
            )
            assert new_raw not in persisted and bundle.access_token not in persisted
            replaced = await conn.scalar(
                text("SELECT replaced_at FROM ima.mcp_refresh_tokens WHERE id=:id"),
                {"id": refresh.id},
            )
            assert replaced is not None

        # A narrowed token cannot broaden back to the original grant on a later rotation.
        with pytest.raises(McpRepositoryError) as narrowed_widening:
            await repository.exchange_refresh_token_bundle(
                new_raw,
                expected_client_id=client_uuid,
                expected_resource=RESOURCE,
                requested_scopes=SCOPES_READ,
            )
        assert narrowed_widening.value.reason == "invalid_scope"
        async with engine.connect() as conn:
            assert await conn.scalar(
                text(
                    "SELECT count(*) FROM ima.audit_events WHERE action='oauth.refresh_token.rotated' AND reason_code='scope_widening'"
                )
            )

        # Replay remains a compromise signal after current client lifecycle changes.
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.mcp_clients SET is_enabled=false WHERE id=:id"),
                {"id": client_uuid},
            )

        with pytest.raises(McpRepositoryError) as exc:
            await repository.exchange_refresh_token_bundle(
                raw_refresh,
                expected_client_id=client_uuid,
                expected_resource=RESOURCE,
                requested_scopes=("mcp:knowledge:read", "mcp:knowledge:write"),
            )
        assert exc.value.reason == "refresh_reuse"
        # Reuse revokes the family and the grant.
        async with engine.connect() as conn:
            family_state = await conn.scalar(
                text("SELECT revoked_at FROM ima.mcp_refresh_families WHERE id=:id"),
                {"id": refresh.family_id},
            )
            grant_state = await conn.scalar(
                text("SELECT state FROM ima.mcp_grants WHERE id=:id"), {"id": grant.id}
            )
            assert family_state is not None
            assert grant_state == "revoked"
        # The freshly rotated token now also fails because the family is revoked.
        with pytest.raises(McpRepositoryError):
            await repository.exchange_refresh_token_bundle(
                new_raw,
                expected_client_id=client_uuid,
                expected_resource=RESOURCE,
                requested_scopes=None,
            )
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_refresh_bundle_failure_and_cancellation_roll_back_all_writes() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        issued = await issue_human_token_bundle(repository, grant, client_uuid, admin_id)
        raw_refresh, refresh = issued.refresh_token, issued.refresh
        async with engine.connect() as conn:
            baseline_access = await conn.scalar(
                text("SELECT count(*) FROM ima.mcp_access_tokens WHERE grant_id=:id"),
                {"id": grant.id},
            )
            baseline_last_used = await conn.scalar(
                text("SELECT last_used_at FROM ima.mcp_grants WHERE id=:id"),
                {"id": grant.id},
            )
            baseline_audits = await conn.scalar(
                text(
                    "SELECT count(*) FROM ima.audit_events WHERE target_id=:id AND action IN ('oauth.refresh_token.rotated','oauth.access_token.issued') AND result='success'"
                ),
                {"id": str(grant.id)},
            )

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE OR REPLACE FUNCTION ima.fail_refresh_access_bundle() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced refresh access failure'; END $$"
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER fail_refresh_access_bundle BEFORE INSERT ON ima.mcp_access_tokens FOR EACH ROW EXECUTE FUNCTION ima.fail_refresh_access_bundle()"
                )
            )
        with pytest.raises(Exception, match="forced refresh access failure"):
            await repository.exchange_refresh_token_bundle(
                raw_refresh,
                expected_client_id=client_uuid,
                expected_resource=RESOURCE,
                requested_scopes=("mcp:knowledge:read",),
            )

        async def assert_unchanged() -> None:
            async with engine.connect() as conn:
                state = (
                    (
                        await conn.execute(
                            text(
                                "SELECT replaced_at,replaced_by FROM ima.mcp_refresh_tokens WHERE id=:id"
                            ),
                            {"id": refresh.id},
                        )
                    )
                    .mappings()
                    .one()
                )
                assert state["replaced_at"] is None and state["replaced_by"] is None
                assert (
                    await conn.scalar(
                        text(
                            "SELECT rotated_generation FROM ima.mcp_refresh_families WHERE id=:id"
                        ),
                        {"id": refresh.family_id},
                    )
                    == 0
                )
                assert (
                    await conn.scalar(
                        text("SELECT count(*) FROM ima.mcp_refresh_tokens WHERE family_id=:id"),
                        {"id": refresh.family_id},
                    )
                    == 1
                )
                assert (
                    await conn.scalar(
                        text("SELECT count(*) FROM ima.mcp_access_tokens WHERE grant_id=:id"),
                        {"id": grant.id},
                    )
                    == baseline_access
                )
                assert (
                    await conn.scalar(
                        text("SELECT last_used_at FROM ima.mcp_grants WHERE id=:id"),
                        {"id": grant.id},
                    )
                    == baseline_last_used
                )
                assert (
                    await conn.scalar(
                        text(
                            "SELECT count(*) FROM ima.audit_events WHERE target_id=:id AND action IN ('oauth.refresh_token.rotated','oauth.access_token.issued') AND result='success'"
                        ),
                        {"id": str(grant.id)},
                    )
                    == baseline_audits
                )

        await assert_unchanged()
        async with engine.begin() as conn:
            await conn.execute(
                text("DROP TRIGGER fail_refresh_access_bundle ON ima.mcp_access_tokens")
            )
            await conn.execute(
                text(
                    "CREATE OR REPLACE FUNCTION ima.fail_refresh_access_bundle() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(10); RETURN NEW; END $$"
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER fail_refresh_access_bundle BEFORE INSERT ON ima.mcp_access_tokens FOR EACH ROW EXECUTE FUNCTION ima.fail_refresh_access_bundle()"
                )
            )
        exchange = asyncio.create_task(
            repository.exchange_refresh_token_bundle(
                raw_refresh,
                expected_client_id=client_uuid,
                expected_resource=RESOURCE,
                requested_scopes=("mcp:knowledge:read",),
            )
        )
        await asyncio.sleep(0.5)
        exchange.cancel()
        with pytest.raises(asyncio.CancelledError):
            await exchange
        await assert_unchanged()
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DROP TRIGGER IF EXISTS fail_refresh_access_bundle ON ima.mcp_access_tokens")
            )
            await conn.execute(text("DROP FUNCTION IF EXISTS ima.fail_refresh_access_bundle()"))
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_concurrent_refresh_has_one_winner_then_revokes_family_on_replay() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        issued = await issue_human_token_bundle(repository, grant, client_uuid, admin_id)
        raw_refresh = issued.refresh_token
        family_id = issued.refresh.family_id

        async def attempt() -> object:
            try:
                return await repository.exchange_refresh_token_bundle(
                    raw_refresh,
                    expected_client_id=client_uuid,
                    expected_resource=RESOURCE,
                    requested_scopes=None,
                )
            except McpRepositoryError as exc:
                return exc

        outcomes = await asyncio.gather(attempt(), attempt())
        winners = [value for value in outcomes if not isinstance(value, McpRepositoryError)]
        failures = [value for value in outcomes if isinstance(value, McpRepositoryError)]
        assert len(winners) == 1
        assert len(failures) == 1 and failures[0].reason == "refresh_reuse"
        winner = winners[0]
        assert winner.access_token not in repr(winner)
        assert winner.refresh_token not in repr(winner)

        async with engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT revoked_at IS NOT NULL FROM ima.mcp_refresh_families WHERE id=:id"),
                {"id": family_id},
            )
            assert (
                await conn.scalar(
                    text("SELECT state FROM ima.mcp_grants WHERE id=:id"), {"id": grant.id}
                )
                == "revoked"
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.mcp_refresh_tokens WHERE family_id=:id"),
                    {"id": family_id},
                )
                == 2
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.mcp_access_tokens WHERE grant_id=:id"),
                    {"id": grant.id},
                )
                == 2
            )
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.audit_events WHERE target_id=:id AND action='oauth.refresh_token.replay' AND reason_code='refresh_reuse'"
                    ),
                    {"id": str(grant.id)},
                )
                == 1
            )
        assert (
            await repository.load_access_token(winner.access_token, expected_resource=RESOURCE)
            is None
        )
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_access_token_resource_binding_and_revoke() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        raw_at, at = await repository.create_access_token(
            grant_id=grant.id,
            principal_id=None,
            client_id=client_uuid,
            canonical_resource=RESOURCE,
            scopes=SCOPES_READ,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
            security_stamp=admin_id,
        )
        # Correct resource resolves.
        loaded = await repository.load_access_token(raw_at, expected_resource=RESOURCE)
        assert loaded is not None
        assert loaded.grant_id == grant.id
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.mcp_clients SET is_enabled=false WHERE id=:id"),
                {"id": client_uuid},
            )
        assert await repository.load_access_token(raw_at, expected_resource=RESOURCE) is None
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.mcp_clients SET is_enabled=true WHERE id=:id"),
                {"id": client_uuid},
            )
        # Wrong resource is rejected (audience binding).
        assert (
            await repository.load_access_token(raw_at, expected_resource="https://other.test/api")
            is None
        )
        # Digest-only persistence for access tokens too.
        async with engine.connect() as conn:
            stored = await conn.scalar(
                text("SELECT token_digest FROM ima.mcp_access_tokens WHERE id=:id"),
                {"id": at.id},
            )
            assert stored == repository._token_digest(raw_at)
        await repository.revoke_access_token(raw_at, reason="test_revoke")
        assert await repository.load_access_token(raw_at, expected_resource=RESOURCE) is None
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_service_principal_credential_finite_expiry_rotation_and_revoke() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        principal = await repository.create_service_principal(
            display_name="CI Deploy",
            purpose="Automated ingestion",
            owner_user_id=admin_id,
            scopes=("mcp:knowledge:read",),
            expires_at=datetime.now(UTC) + timedelta(days=30),
            rate_limit=5,
            concurrency_limit=2,
            cidr_allowlist=("10.0.0.0/8",),
            created_by=admin_id,
        )
        # Finite expiry is enforced.
        with pytest.raises(McpRepositoryError) as exc:
            await repository.create_service_principal(
                display_name="Too Long",
                purpose="Should be rejected",
                owner_user_id=admin_id,
                scopes=("mcp:knowledge:read",),
                expires_at=datetime.now(UTC) + timedelta(days=400),
                rate_limit=5,
                concurrency_limit=2,
                created_by=admin_id,
            )
        assert exc.value.reason == "expiry_too_long"

        raw_secret, credential = await repository.create_credential(
            principal_id=principal.id,
            created_by=admin_id,
            expires_at=principal.expires_at,
        )
        async with engine.connect() as conn:
            stored = await conn.scalar(
                text("SELECT digest FROM ima.mcp_credentials WHERE id=:id"),
                {"id": credential.id},
            )
            assert stored == repository._token_digest(raw_secret)
            assert stored != raw_secret

        found = await repository.find_credential_by_id(credential.credential_id)
        assert found is not None
        assert await repository.exchange_credential(credential.credential_id, "wrong") is None
        exchanged = await repository.exchange_credential(credential.credential_id, raw_secret)
        assert exchanged is not None
        exchanged_credential, exchanged_principal = exchanged
        assert exchanged_credential.principal_id == principal.id
        assert exchanged_principal.id == principal.id
        assert exchanged_credential.last_used_at is not None

        # Rotate: old credential is revoked by default, replacement issued.
        raw2, new_cred, old_cred = await repository.rotate_credential(
            credential.credential_id,
            created_by=admin_id,
            expires_at=principal.expires_at,
        )
        assert old_cred.revoked_at is not None
        assert new_cred.revoked_at is None
        assert raw2 != raw_secret
        # Old credential id no longer resolves.
        assert await repository.find_credential_by_id(credential.credential_id) is None

        # Revoke the replacement by credential id.
        await repository.revoke_credential(new_cred.credential_id, actor_id=admin_id, reason="test")
        assert await repository.find_credential_by_id(new_cred.credential_id) is None

        # Principal disable/revoke takes effect on next lookup.
        await repository.set_principal_state(
            principal.id, "revoked", actor_id=admin_id, reason="test"
        )
        assert await repository.load_service_principal(principal.id, include_inactive=False) is None
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_credential_bearer_direct_auth_lease_and_revocation() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        principal_row = await repository.create_service_principal(
            display_name="Direct Bearer",
            purpose="Connector one-click config",
            owner_user_id=admin_id,
            scopes=("mcp:knowledge:read",),
            expires_at=datetime.now(UTC) + timedelta(days=90),
            rate_limit=5,
            concurrency_limit=2,
            created_by=admin_id,
        )
        raw_secret, credential = await repository.create_credential(
            principal_id=principal_row.id,
            created_by=admin_id,
            expires_at=principal_row.expires_at,
        )

        resolved = await repository.resolve_credential_bearer(raw_secret)
        assert resolved is not None
        direct_credential, direct_principal = resolved
        assert direct_credential.id == credential.id
        assert direct_principal.id == principal_row.id
        assert direct_credential.last_used_at is not None
        assert await repository.resolve_credential_bearer("wrong-secret") is None

        # Leases anchor on one durable access-token row per credential whose
        # digest can never be presented as a bearer secret.
        lease = await repository.acquire_concurrency_lease(
            token_id=credential.id,
            principal_id=principal_row.id,
            source="127.0.0.1",
            request_id="direct-1",
            limit=principal_row.concurrency_limit,
        )
        assert lease is not None
        async with engine.connect() as conn:
            anchor = (
                (
                    await conn.execute(
                        text(
                            "SELECT token_digest,canonical_resource,principal_id FROM ima.mcp_access_tokens WHERE id=:id"
                        ),
                        {"id": credential.id},
                    )
                )
                .mappings()
                .first()
            )
            assert anchor is not None
            assert UUID(str(anchor["principal_id"])) == principal_row.id
            assert anchor["token_digest"] != repository._token_digest(raw_secret)
            assert anchor["canonical_resource"] != settings.mcp_resource_url
            count = await conn.scalar(
                text("SELECT count(*) FROM ima.mcp_access_tokens WHERE id=:id"),
                {"id": credential.id},
            )
            assert int(count) == 1
        # The anchor backs leases only: even the guessable synthetic preimage
        # never resolves as a bearer because the resource cannot match.
        assert (
            await repository.load_access_token(
                f"mcp-credential-lease:{credential.id}",
                expected_resource=settings.mcp_resource_url,
            )
            is None
        )
        await repository.release_concurrency_lease(lease)

        # A revocation that lands on the anchor row (e.g. someone presents the
        # synthetic string to /oauth/revoke) is repaired while the credential
        # itself stays live.
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.mcp_access_tokens SET revoked_at=now() WHERE id=:id"),
                {"id": credential.id},
            )
        healed = await repository.acquire_concurrency_lease(
            token_id=credential.id,
            principal_id=principal_row.id,
            source="127.0.0.1",
            request_id="direct-2",
            limit=principal_row.concurrency_limit,
        )
        assert healed is not None
        await repository.release_concurrency_lease(healed)

        # Audit rows carry identifiers only, never the secret.
        async with engine.connect() as conn:
            audits = (
                await conn.execute(
                    text(
                        "SELECT result,metadata FROM ima.audit_events WHERE action='mcp.credential.direct_auth' AND target_id=:pid"
                    ),
                    {"pid": str(principal_row.id)},
                )
            ).all()
            assert [row[0] for row in audits] == ["success"]
            assert "credential_id" in str(audits[0][1])
            assert raw_secret not in str(audits)

        # Revocation denies the secret immediately.
        await repository.revoke_credential(
            credential.credential_id, actor_id=admin_id, reason="test"
        )
        assert await repository.resolve_credential_bearer(raw_secret) is None
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_rate_buckets_and_safe_audit() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        # Exhaust a limit of 3 attempts; the 4th is blocked.
        bucket_run = str(uuid4())
        allowed = [
            await repository.rate_allowed("token", "exchange", f"bucket-a:{bucket_run}", limit=3)
            for _ in range(4)
        ]
        assert allowed[:3] == [True, True, True]
        assert allowed[3] is False
        # A different principal is not affected.
        assert (
            await repository.rate_allowed("token", "exchange", f"bucket-b:{bucket_run}", limit=3)
            is True
        )
        concurrent = await asyncio.gather(
            *(
                repository.rate_allowed("tool", "ask", f"bucket-concurrent:{bucket_run}", limit=5)
                for _ in range(10)
            )
        )
        assert sum(concurrent) == 5

        # Audit rows are written with safe metadata and no raw secrets.
        await repository.append_audit(
            admin_id,
            "mcp.tool.denied",
            "failure",
            target_type="tool",
            target_id="kb_ask",
            reason="insufficient_scope",
            metadata={"scopes": ["mcp:knowledge:read"]},
            correlation_id="corr-1",
        )
        await repository.append_audit(
            admin_id,
            "oauth.redaction.test",
            "failure",
            metadata={
                "access_token": "must-not-persist",
                "nested": {"code_verifier": "must-not-persist", "kb_id": "kb-1"},
            },
        )
        async with engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT action,result,reason_code,metadata,correlation_id FROM ima.audit_events WHERE actor_id=:id AND action='mcp.tool.denied'"
                        ),
                        {"id": admin_id},
                    )
                )
                .mappings()
                .first()
            )
            assert row is not None
            assert row["result"] == "failure"
            assert row["reason_code"] == "insufficient_scope"
            assert row["correlation_id"] == "corr-1"
            metadata = dict(row["metadata"])
            assert "access_token" not in metadata and "secret" not in metadata
            redacted = await conn.scalar(
                text(
                    "SELECT metadata FROM ima.audit_events WHERE actor_id=:id AND action='oauth.redaction.test'"
                ),
                {"id": admin_id},
            )
            assert redacted["access_token"] in {"[REDACTED]", "<redacted>"}
            assert redacted["nested"]["code_verifier"] in {"[REDACTED]", "<redacted>"}
            assert "must-not-persist" not in str(redacted)
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_concurrent_code_exchange_allows_exactly_one_winner() -> None:
    """Two concurrent exchanges of the same code must produce exactly one winner."""
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        raw_code, _ = await repository.create_authorization_code(
            grant_id=grant.id,
            user_id=admin_id,
            client_id=client_uuid,
            redirect_uri="http://localhost:8765/callback",
            canonical_resource=RESOURCE,
            scopes=SCOPES_READ,
            code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            security_stamp=admin_id,
            state="state-xyz",
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )

        async def attempt() -> bool:
            try:
                await repository.exchange_authorization_code_bundle(
                    raw_code,
                    expected_client_id=client_uuid,
                    expected_redirect_uri="http://localhost:8765/callback",
                    expected_resource=RESOURCE,
                    expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
                )
                return True
            except McpRepositoryError:
                return False

        results = await asyncio.gather(attempt(), attempt())
        assert sum(results) == 1
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_token_bundle_failure_rolls_back_code_and_all_tokens() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        raw_code, code = await repository.create_authorization_code(
            grant_id=grant.id,
            user_id=admin_id,
            client_id=client_uuid,
            redirect_uri="http://localhost:8765/callback",
            canonical_resource=RESOURCE,
            scopes=SCOPES_READ,
            code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            security_stamp=admin_id,
            state="atomic",
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "CREATE OR REPLACE FUNCTION ima.fail_refresh_bundle() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced bundle failure'; END $$"
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER fail_refresh_bundle BEFORE INSERT ON ima.mcp_refresh_tokens FOR EACH ROW EXECUTE FUNCTION ima.fail_refresh_bundle()"
                )
            )
        with pytest.raises(Exception, match="forced bundle failure"):
            await repository.exchange_authorization_code_bundle(
                raw_code,
                expected_client_id=client_uuid,
                expected_redirect_uri="http://localhost:8765/callback",
                expected_resource=RESOURCE,
                expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            )
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT used_at FROM ima.mcp_authorization_codes WHERE id=:id"),
                    {"id": code.id},
                )
                is None
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.mcp_access_tokens WHERE grant_id=:id"),
                    {"id": grant.id},
                )
                == 0
            )
        async with engine.begin() as conn:
            await conn.execute(text("DROP TRIGGER fail_refresh_bundle ON ima.mcp_refresh_tokens"))
            await conn.execute(
                text(
                    "CREATE OR REPLACE FUNCTION ima.fail_refresh_bundle() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM pg_sleep(10); RETURN NEW; END $$"
                )
            )
            await conn.execute(
                text(
                    "CREATE TRIGGER fail_refresh_bundle BEFORE INSERT ON ima.mcp_refresh_tokens FOR EACH ROW EXECUTE FUNCTION ima.fail_refresh_bundle()"
                )
            )
        exchange = asyncio.create_task(
            repository.exchange_authorization_code_bundle(
                raw_code,
                expected_client_id=client_uuid,
                expected_redirect_uri="http://localhost:8765/callback",
                expected_resource=RESOURCE,
                expected_code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
            )
        )
        await asyncio.sleep(0.5)
        exchange.cancel()
        with pytest.raises(asyncio.CancelledError):
            await exchange
        async with engine.connect() as conn:
            assert await conn.scalar(
                text("SELECT used_at IS NULL FROM ima.mcp_authorization_codes WHERE id=:id"),
                {"id": code.id},
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.mcp_access_tokens WHERE grant_id=:id"),
                    {"id": grant.id},
                )
                == 0
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.mcp_refresh_families WHERE grant_id=:id"),
                    {"id": grant.id},
                )
                == 0
            )
    finally:
        async with engine.begin() as conn:
            await conn.execute(
                text("DROP TRIGGER IF EXISTS fail_refresh_bundle ON ima.mcp_refresh_tokens")
            )
            await conn.execute(text("DROP FUNCTION IF EXISTS ima.fail_refresh_bundle()"))
        await cleanup(engine, admin_id)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_oauth_concurrency_leases_limit_release_and_expiry_recovery() -> None:
    assert DATABASE_URL is not None
    await run_migrations_once()
    settings = integration_settings()
    engine = create_engine(settings)
    repository = McpOauthRepository(engine, settings)
    admin_id = await create_fixture(engine)
    try:
        client_uuid, grant = await build_human_grant(repository, admin_id)
        raw, token = await repository.create_access_token(
            grant_id=grant.id,
            principal_id=None,
            client_id=client_uuid,
            canonical_resource=RESOURCE,
            scopes=SCOPES_READ,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            security_stamp=admin_id,
        )
        assert raw
        leases = await asyncio.gather(
            *(
                repository.acquire_concurrency_lease(
                    token_id=token.id,
                    principal_id=None,
                    source="10.0.0.1",
                    request_id=f"request-{index}",
                    limit=2,
                    ttl_seconds=30,
                )
                for index in range(3)
            )
        )
        assert sum(value is not None for value in leases) == 2
        async with engine.connect() as conn:
            denial = (
                (
                    await conn.execute(
                        text(
                            "SELECT reason_code,metadata FROM ima.audit_events WHERE action='mcp.concurrency.denied' ORDER BY created_at DESC LIMIT 1"
                        )
                    )
                )
                .mappings()
                .one()
            )
            assert denial["reason_code"] == "concurrency_limited"
            assert dict(denial["metadata"]) == {"limit": 2}
        first = next(value for value in leases if value is not None)
        await repository.release_concurrency_lease(first)
        assert (
            await repository.acquire_concurrency_lease(
                token_id=token.id,
                principal_id=None,
                source="10.0.0.1",
                request_id="replacement",
                limit=2,
            )
            is not None
        )
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.mcp_concurrency_leases SET created_at=:created,expires_at=:past WHERE token_id=:id"
                ),
                {
                    "created": datetime.now(UTC) - timedelta(seconds=2),
                    "past": datetime.now(UTC) - timedelta(seconds=1),
                    "id": token.id,
                },
            )
        recovered = await repository.acquire_concurrency_lease(
            token_id=token.id,
            principal_id=None,
            source="10.0.0.1",
            request_id="after-expiry",
            limit=1,
        )
        assert recovered is not None
        raw_other, other_token = await repository.create_access_token(
            grant_id=grant.id,
            principal_id=None,
            client_id=client_uuid,
            canonical_resource=RESOURCE,
            scopes=SCOPES_READ,
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            security_stamp=admin_id,
        )
        assert raw_other
        # The same opaque request ID is isolated by actor token and source boundary.
        first_actor = await repository.acquire_concurrency_lease(
            token_id=token.id,
            principal_id=None,
            source="10.0.0.2",
            request_id="same-request",
            limit=2,
        )
        second_actor = await repository.acquire_concurrency_lease(
            token_id=other_token.id,
            principal_id=None,
            source="10.0.0.2",
            request_id="same-request",
            limit=2,
        )
        assert first_actor is not None and second_actor is not None and first_actor != second_actor
        assert (
            await repository.acquire_concurrency_lease(
                token_id=other_token.id,
                principal_id=None,
                source="10.0.0.2",
                request_id="same-request",
                limit=2,
            )
            == second_actor
        )

        principal = await repository.create_service_principal(
            display_name="Lease principal",
            purpose="Concurrency boundary",
            owner_user_id=admin_id,
            scopes=("mcp:knowledge:read",),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            rate_limit=10,
            concurrency_limit=1,
            created_by=admin_id,
        )
        _, principal_token_1 = await repository.create_access_token(
            grant_id=None,
            principal_id=principal.id,
            client_id=None,
            canonical_resource=RESOURCE,
            scopes=("mcp:knowledge:read",),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        _, principal_token_2 = await repository.create_access_token(
            grant_id=None,
            principal_id=principal.id,
            client_id=None,
            canonical_resource=RESOURCE,
            scopes=("mcp:knowledge:read",),
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
        )
        principal_leases = await asyncio.gather(
            repository.acquire_concurrency_lease(
                token_id=principal_token_1.id,
                principal_id=principal.id,
                source="10.0.0.3",
                request_id="principal-one",
                limit=99,
            ),
            repository.acquire_concurrency_lease(
                token_id=principal_token_2.id,
                principal_id=principal.id,
                source="10.0.0.4",
                request_id="principal-two",
                limit=99,
            ),
        )
        assert sum(value is not None for value in principal_leases) == 1
        # Omitting the token's principal cannot create a token-scoped bypass.
        assert (
            await repository.acquire_concurrency_lease(
                token_id=principal_token_2.id,
                principal_id=None,
                source="10.0.0.5",
                request_id="spoofed-human",
                limit=99,
            )
            is None
        )
    finally:
        await cleanup(engine, admin_id)
        await engine.dispose()
