"""PostgreSQL identity gate; this test is mandatory in the Compose gate."""

# Full SQL fixture statements stay visible for migration review.
# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from argon2 import PasswordHasher
from sqlalchemy import text

from ima.application.identity import IdentityError, IdentityService
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.tasks.app import create_task_app

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")


class FakeRequest:
    def __init__(self, cookies: dict[str, str] | None = None) -> None:
        self.headers = {"user-agent": "identity-integration"}
        self.cookies = cookies or {}
        self.client = SimpleNamespace(host="127.0.0.1")


class FakeResponse:
    def __init__(self) -> None:
        self.cookies: dict[str, str] = {}

    def set_cookie(self, key: str, value: str, **_: object) -> None:
        self.cookies[key] = value


def integration_settings() -> Settings:
    assert DATABASE_URL is not None
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="session-integration-pepper",
        token_pepper="token-integration-pepper",
        totp_encryption_key="totp-integration-key",
        bridge_token="bridge-integration-token",
    )


async def ensure_legacy_tables(engine: object) -> None:
    async with engine.begin() as connection:  # type: ignore[attr-defined]
        for statement in (
            'CREATE TABLE IF NOT EXISTS public."user" (id text PRIMARY KEY,name text NOT NULL,email text NOT NULL UNIQUE,image text,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now())',
            'CREATE TABLE IF NOT EXISTS public."userData" (id text PRIMARY KEY,perfs jsonb NOT NULL,data jsonb NOT NULL)',
            'CREATE TABLE IF NOT EXISTS public."account" (id text PRIMARY KEY,account_id text NOT NULL,provider_id text NOT NULL,user_id text NOT NULL,password text,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now())',
            'CREATE TABLE IF NOT EXISTS public."two_factor" (id text PRIMARY KEY,secret text NOT NULL,backup_codes text NOT NULL,user_id text NOT NULL)',
            'CREATE TABLE IF NOT EXISTS public."session" (id text PRIMARY KEY,token text NOT NULL,user_id text NOT NULL,expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now())',
            'CREATE TABLE IF NOT EXISTS public."workspace" (id varchar(16) PRIMARY KEY,name text NOT NULL)',
        ):
            await connection.execute(text(statement))


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_identity_schema_repeat_lifecycle_and_security_invariants() -> None:
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
    settings = integration_settings()
    settings = Settings(**{**settings.model_dump(), "recent_auth_seconds": 900})
    engine = create_engine(settings)
    service = IdentityService(engine, settings)
    task_app = create_task_app(settings)
    async with engine.connect() as connection:
        task_schema_ready = await connection.scalar(
            text("SELECT to_regtype('ima_jobs.procrastinate_job_status')")
        )
    if task_schema_ready is None:
        with task_app.open():
            task_app.schema_manager.apply_schema()
    try:
        await ensure_legacy_tables(engine)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    'DELETE FROM public."userData" WHERE id IN (SELECT id FROM public."user" WHERE email=\'identity@example.test\')'
                )
            )
            await connection.execute(
                text("DELETE FROM public.\"user\" WHERE email='identity@example.test'")
            )
            await connection.execute(text("DELETE FROM ima.audit_events"))
            await connection.execute(text("DELETE FROM ima.users"))
        user, _ = await service.create_user(
            "identity@example.test", "Identity Fixture", "password-123456", invite=False
        )
        response = FakeResponse()
        status, _, challenge = await service.authenticate_password(
            "identity@example.test", "password-123456", FakeRequest(), response
        )
        assert status == "authenticated"
        assert challenge is None
        assert settings.session_cookie_name in response.cookies
        session_request = FakeRequest(
            {settings.session_cookie_name: response.cookies[settings.session_cookie_name]}
        )
        current = await service.current_session(session_request)
        assert current is not None and current[1].id == user.id
        uri = await service.start_totp(user.id)
        assert uri.startswith("otpauth://")
        import pyotp

        secret = uri.split("secret=", 1)[1].split("&", 1)[0]
        codes = await service.confirm_totp(user.id, pyotp.TOTP(secret).now())
        assert len(codes) == 10
        response = FakeResponse()
        status, _, challenge = await service.authenticate_password(
            "identity@example.test", "password-123456", FakeRequest(), response
        )
        assert status == "totp_required" and challenge
        verified = await service.verify_challenge(
            challenge, codes[0], FakeRequest(), response, recovery=True
        )
        assert verified.id == user.id
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM ima.recovery_codes "
                        "WHERE user_id=:id AND used_at IS NOT NULL"
                    ),
                    {"id": user.id},
                )
                == 1
            )
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM ima.audit_events WHERE actor_id=:id"),
                    {"id": user.id},
                )
                >= 3
            )
        legacy_phc = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(
            "legacy-password"
        )
        legacy_totp = pyotp.random_base32()
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO public.\"user\"(id,name,email) VALUES ('legacy-user-01','Legacy Fixture','legacy@example.test') ON CONFLICT DO NOTHING"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"account\"(id,account_id,provider_id,user_id,password) VALUES ('legacy-account-01','legacy-user-01','credential','legacy-user-01',:phc) ON CONFLICT DO NOTHING"
                ),
                {"phc": legacy_phc},
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"two_factor\"(id,secret,backup_codes,user_id) VALUES ('legacy-totp-01',:secret,'[]','legacy-user-01') ON CONFLICT DO NOTHING"
                ),
                {"secret": legacy_totp},
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"session\"(id,token,user_id,expires_at) VALUES ('legacy-session-01','legacy-session-token','legacy-user-01',now()+interval '1 day') ON CONFLICT DO NOTHING"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"workspace\"(id,name) VALUES ('legacy-ws-01','Legacy Workspace') ON CONFLICT DO NOTHING"
                )
            )
        migration_env = {**os.environ, "IMA_DATABASE_URL": env["IMA_DATABASE_URL"]}
        subprocess.run(
            ["uv", "run", "ima", "migrate-legacy-identity", "apply"],
            cwd=root,
            env=migration_env,
            check=True,
        )  # noqa: ASYNC221
        subprocess.run(
            ["uv", "run", "ima", "migrate-legacy-identity", "apply"],
            cwd=root,
            env=migration_env,
            check=True,
        )  # noqa: ASYNC221
        subprocess.run(
            ["uv", "run", "ima", "migrate-legacy-identity", "verify"],
            cwd=root,
            env=migration_env,
            check=True,
        )  # noqa: ASYNC221
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT password_reset_required FROM ima.users WHERE id='legacy-user-01'")
                )
                is False
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM ima.password_credentials WHERE user_id='legacy-user-01'"
                    )
                )
                == 1
            )
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM ima.totp_credentials WHERE user_id='legacy-user-01'")
                )
                == 1
            )
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM ima.sessions WHERE user_id='legacy-user-01'")
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text("SELECT count(*) FROM ima.workspaces WHERE id='legacy-ws-01'")
                )
                == 1
            )
        concurrent_ids = ("concurrent-super-a", "concurrent-super-b")
        async with engine.begin() as connection:
            for user_id in concurrent_ids:
                await connection.execute(
                    text(
                        "INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,security_stamp,created_at,updated_at) VALUES (:id,:email,:email,:name,true,:stamp,now(),now()) ON CONFLICT(id) DO UPDATE SET is_active=true"
                    ),
                    {
                        "id": user_id,
                        "email": f"{user_id}@example.test",
                        "name": user_id,
                        "stamp": user_id,
                    },
                )
                await connection.execute(
                    text(
                        "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (:id,'super_admin',now()) ON CONFLICT DO NOTHING"
                    ),
                    {"id": user_id},
                )
        outcomes = await asyncio.gather(
            service.mutate_platform_role(
                concurrent_ids[0], concurrent_ids[1], "super_admin", grant=False
            ),
            service.mutate_platform_role(
                concurrent_ids[1], concurrent_ids[0], "super_admin", grant=False
            ),
            return_exceptions=True,
        )
        assert sum(isinstance(outcome, IdentityError) for outcome in outcomes) == 1
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM ima.platform_role_assignments r JOIN ima.users u ON u.id=r.user_id WHERE r.role='super_admin' AND u.is_active"
                    )
                )
                >= 1
            )
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_identity_rate_limit_and_password_reset_token_is_single_use() -> None:
    settings = integration_settings()
    settings = Settings(**{**settings.model_dump(), "login_max_attempts": 2})
    engine = create_engine(settings)
    service = IdentityService(engine, settings)
    try:
        await ensure_legacy_tables(engine)
        email = "reset-single-use@example.test"
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ima.users WHERE normalized_email=:email"), {"email": email}
            )
            await connection.execute(
                text(
                    'DELETE FROM public."userData" WHERE id IN (SELECT id FROM public."user" WHERE email=:email)'
                ),
                {"email": email},
            )
            await connection.execute(
                text('DELETE FROM public."user" WHERE email=:email'), {"email": email}
            )
        await service.create_user(email, "Reset Fixture", "password-123456", invite=False)
        token = await service.create_password_token(email, "password_reset")
        assert token
        await service.reset_password(token, "password-654321")
        with pytest.raises(IdentityError):
            await service.reset_password(token, "password-987654")
        assert await service.rate_allowed("sign_in", "bucket")
        assert await service.rate_allowed("sign_in", "bucket")
        assert await service.rate_allowed("sign_in", "bucket") is False
        token = await service.create_password_token(email, "password_reset")
        assert token
        outcomes = await asyncio.gather(
            service.reset_password(token, "password-111111"),
            service.reset_password(token, "password-222222"),
            return_exceptions=True,
        )
        assert sum(isinstance(outcome, IdentityError) for outcome in outcomes) == 1
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_identity_projection_has_no_legacy_account_session_or_workspace_side_effect() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = IdentityService(engine, settings)
    try:
        await ensure_legacy_tables(engine)
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ima.users WHERE normalized_email='projection@example.test'")
            )
            await connection.execute(
                text(
                    'DELETE FROM public."userData" WHERE id IN (SELECT id FROM public."user" WHERE email=\'projection@example.test\')'
                )
            )
            await connection.execute(
                text("DELETE FROM public.\"user\" WHERE email='projection@example.test'")
            )
        user, _ = await service.create_user(
            "projection@example.test", "Projection Fixture", "password-123456", invite=False
        )
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text('SELECT count(*) FROM public."account" WHERE user_id=:id'), {"id": user.id}
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text('SELECT count(*) FROM public."session" WHERE user_id=:id'), {"id": user.id}
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text('SELECT count(*) FROM public."two_factor" WHERE user_id=:id'),
                    {"id": user.id},
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text('SELECT count(*) FROM public."workspace" WHERE id=:id'), {"id": user.id}
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text('SELECT count(*) FROM public."user" WHERE id=:id'), {"id": user.id}
                )
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_invite_is_explicitly_unavailable_without_smtp() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = IdentityService(engine, settings)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "DELETE FROM ima.audit_events WHERE action='auth.invite_accepted' AND reason_code='invalid_or_expired'"
                )
            )
        with pytest.raises(IdentityError) as error:
            await service.create_user("invite-disabled@example.test", "Invite Fixture", invite=True)
        assert error.value.status_code == 503
        with pytest.raises(IdentityError) as invalid:
            await service.accept_invite("invalid-invitation-token-00000001", "password-123456")
        assert invalid.value.status_code == 400
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM ima.audit_events WHERE action='auth.invite_accepted' AND result='failed' AND reason_code='invalid_or_expired'"
                    )
                )
                == 1
            )
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_incompatible_legacy_credentials_force_reset_and_disable_totp() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    try:
        await ensure_legacy_tables(engine)
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ima.users WHERE id='legacy-incompatible-01'")
            )
            await connection.execute(
                text("DELETE FROM public.\"user\" WHERE id='legacy-incompatible-01'")
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"user\"(id,name,email) VALUES ('legacy-incompatible-01','Bad Legacy','legacy-incompatible@example.test') ON CONFLICT DO NOTHING"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"account\"(id,account_id,provider_id,user_id,password) VALUES ('legacy-incompatible-account','legacy-incompatible-01','credential','legacy-incompatible-01','not-a-phc') ON CONFLICT DO NOTHING"
                )
            )
            await connection.execute(
                text(
                    "INSERT INTO public.\"two_factor\"(id,secret,backup_codes,user_id) VALUES ('legacy-incompatible-totp','invalid','[]','legacy-incompatible-01') ON CONFLICT DO NOTHING"
                )
            )
        root = Path(__file__).parents[2]
        migration_env = {
            **os.environ,
            "IMA_DATABASE_URL": DATABASE_URL.replace(
                "postgresql+asyncpg://", "postgresql+psycopg://"
            ),
        }
        subprocess.run(
            ["uv", "run", "ima", "migrate-legacy-identity", "apply"],
            cwd=root,
            env=migration_env,
            check=True,
        )  # noqa: ASYNC221
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text(
                        "SELECT password_reset_required FROM ima.users WHERE id='legacy-incompatible-01'"
                    )
                )
                is True
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM ima.password_credentials WHERE user_id='legacy-incompatible-01'"
                    )
                )
                == 0
            )
            assert (
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM ima.totp_credentials WHERE user_id='legacy-incompatible-01'"
                    )
                )
                == 0
            )
    finally:
        await engine.dispose()
