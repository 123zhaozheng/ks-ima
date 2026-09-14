"""Explicit operational commands."""

# Bootstrap SQL is deliberately visible in one command for operator review.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import psycopg

from ima.application.identity import new_legacy_id
from ima.application.maintenance import MaintenanceService
from ima.config import get_settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.tasks.app import (
    configure_procrastinate_function_search_path,
    create_task_app,
)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ima")
    parser.add_argument(
        "command",
        choices=(
            "worker",
            "check-config",
            "check-worker",
            "migrate",
            "bootstrap-admin",
            "rotate-model-secrets",
            "register-mcp-client",
            "maintenance",
        ),
    )
    parser.add_argument(
        "--client-id",
        dest="client_id",
        type=str,
        help="Public client ID (lowercase alphanumeric with hyphens)",
    )
    parser.add_argument(
        "--client-name",
        dest="client_name",
        type=str,
        help="Human-readable client name",
    )
    parser.add_argument(
        "--client-type",
        dest="client_type",
        type=str,
        choices=("public", "confidential"),
        help="OAuth client type",
    )
    parser.add_argument(
        "--app-type",
        dest="app_type",
        type=str,
        choices=("native", "web"),
        help="Application type",
    )
    parser.add_argument(
        "--auth-method",
        dest="auth_method",
        type=str,
        choices=("none",),
        help="Token endpoint auth method (MVP: none only for public clients)",
    )
    parser.add_argument(
        "--redirect-uri",
        dest="redirect_uris",
        type=str,
        action="append",
        metavar="URI",
        help="Exact redirect URI (can be specified multiple times)",
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=("plan", "apply", "verify", "freeze"),
        default=None,
    )
    parser.add_argument(
        "subaction",
        nargs="?",
        choices=("enter", "exit", "status"),
    )
    parser.add_argument(
        "--operator-id",
        dest="operator_id",
        help="Authenticated super-admin user ID recorded for privileged operations",
    )
    parser.add_argument(
        "--reason",
        dest="reason",
        help="Operator reason recorded when entering the maintenance write freeze",
    )
    args = parser.parse_args()
    if args.command == "check-config":
        get_settings()
        print("configuration valid")
        return
    if args.command == "migrate":
        _run_migrations()
        return
    if args.command == "check-worker":
        _check_worker()
        return
    if args.command == "bootstrap-admin":
        _bootstrap_admin()
        return
    if args.command == "rotate-model-secrets":
        _rotate_model_secrets(args.action)
        return
    if args.command == "register-mcp-client":
        _register_mcp_client_sync(
            client_id=args.client_id,
            client_name=args.client_name,
            client_type=args.client_type,
            app_type=args.app_type,
            auth_method=args.auth_method,
            redirect_uris=args.redirect_uris,
            operator_id=args.operator_id,
        )
        return
    if args.command == "maintenance":
        _maintenance_command(args)
        return
    asyncio.run(_run_worker())


def _json_error(code: str, message: str, *, exit_code: int = 2) -> None:
    print(json.dumps({"error": code, "message": message}, sort_keys=True), file=sys.stderr)
    raise SystemExit(exit_code)


def _run_migrations() -> None:
    settings = get_settings()
    backend_root = Path(__file__).resolve().parents[2]
    url = settings.database_url.get_secret_value().replace(
        "postgresql+asyncpg://", "postgresql+psycopg://"
    )
    env = {**os.environ, "IMA_DATABASE_URL": url}
    subprocess.run(
        ["alembic", "-c", str(backend_root / "alembic.ini"), "upgrade", "head"],
        check=True,
        cwd=backend_root,
        env=env,
    )
    task_app = create_task_app(settings)
    task_conninfo = settings.task_url.replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(
        task_conninfo, options=f"-c search_path={settings.task_schema}"
    ) as connection:
        task_schema_row = connection.execute(
            "SELECT to_regclass(%s)", (f"{settings.task_schema}.procrastinate_jobs",)
        ).fetchone()
        task_schema_exists = task_schema_row[0] if task_schema_row else None
    with task_app.open():
        if task_schema_exists is None:
            task_app.schema_manager.apply_schema()
        configure_procrastinate_function_search_path(task_app)


async def _run_worker() -> None:
    from ima.workers.main import run

    await run()


def _check_worker() -> None:
    """Fail a container healthcheck when the configured worker is stale."""
    settings = get_settings()
    task_conninfo = settings.task_url.replace("postgresql+asyncpg://", "postgresql://")
    with psycopg.connect(
        task_conninfo, options=f"-c search_path={settings.task_schema}"
    ) as connection:
        row = connection.execute(
            "SELECT heartbeat_at FROM worker_heartbeat WHERE worker_name = %s",
            (settings.worker_name,),
        ).fetchone()
    heartbeat = row[0] if row else None
    if not isinstance(heartbeat, datetime):
        raise SystemExit("worker heartbeat is unavailable")
    if (datetime.now(UTC) - heartbeat).total_seconds() > settings.worker_lag_warning_seconds:
        raise SystemExit("worker heartbeat is stale")


def _rotate_model_secrets(action: str | None) -> None:
    """Plan/apply/verify key-ring rotation without printing credentials."""

    settings = get_settings()
    ring = __import__(
        "ima.infrastructure.model_gateway.secrets", fromlist=["SecretKeyRing"]
    ).SecretKeyRing(
        settings.model_key_ring.get_secret_value(),
        settings.model_current_key_version,
        settings.model_fingerprint_key.get_secret_value(),
    )
    conninfo = (
        settings.database_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with psycopg.connect(conninfo) as connection:
        rows = connection.execute(
            "SELECT id,key_version FROM ima.model_gateway_secrets ORDER BY id"
        ).fetchall()
        summary: dict[str, Any] = {
            "action": action,
            "records": len(rows),
            "currentVersion": settings.model_current_key_version,
            "secretValues": False,
        }
        if action == "plan":
            print(summary)
            return
        failures: list[dict[str, str]] = []
        if action == "apply":
            for secret_id, _key_version in rows:
                try:
                    with connection.transaction():
                        row = connection.execute(
                            "SELECT s.*,g.id gateway_id FROM ima.model_gateway_secrets s JOIN ima.model_gateways g ON g.secret_id=s.id WHERE s.id=%s FOR UPDATE",
                            (secret_id,),
                        ).fetchone()
                        if not row:
                            continue
                        envelope = __import__(
                            "ima.infrastructure.model_gateway.secrets", fromlist=["SecretEnvelope"]
                        ).SecretEnvelope(
                            key_version=row[1], nonce=row[2], ciphertext=row[3], fingerprint=row[4]
                        )
                        secret = ring.decrypt(
                            envelope, gateway_id=str(row[8]), secret_id=str(row[0])
                        )
                        rotated = ring.encrypt(
                            secret, gateway_id=str(row[8]), secret_id=str(row[0])
                        )
                        connection.execute(
                            "UPDATE ima.model_gateway_secrets SET key_version=%s,nonce=%s,ciphertext=%s,fingerprint=%s,rotated_at=now() WHERE id=%s",
                            (
                                rotated.key_version,
                                rotated.nonce,
                                rotated.ciphertext,
                                rotated.fingerprint,
                                secret_id,
                            ),
                        )
                except Exception as exc:
                    failures.append({"id": str(secret_id), "reason": type(exc).__name__})
        elif action == "verify":
            for secret_id, _version in rows:
                row = connection.execute(
                    "SELECT s.*,g.id gateway_id FROM ima.model_gateway_secrets s JOIN ima.model_gateways g ON g.secret_id=s.id WHERE s.id=%s",
                    (secret_id,),
                ).fetchone()
                if not row:
                    failures.append({"id": str(secret_id), "reason": "missing_gateway"})
                    continue
                try:
                    envelope = __import__(
                        "ima.infrastructure.model_gateway.secrets", fromlist=["SecretEnvelope"]
                    ).SecretEnvelope(
                        key_version=row[1], nonce=row[2], ciphertext=row[3], fingerprint=row[4]
                    )
                    ring.decrypt(envelope, gateway_id=str(row[8]), secret_id=str(row[0]))
                except Exception as exc:
                    failures.append({"id": str(secret_id), "reason": type(exc).__name__})
        summary["failures"] = failures
        summary["verified"] = not failures
        print(summary)
        if failures and action == "verify":
            raise SystemExit(1)


def _maintenance_command(args: Any) -> None:
    """Enter/exit/report the typed maintenance write freeze."""
    if args.action != "freeze":
        _json_error("invalid_action", "maintenance supports freeze")
    mode = args.subaction or "status"
    operator_id = str(args.operator_id or "")
    if mode in {"enter", "exit"} and not operator_id:
        _json_error("operator_required", "freeze enter/exit requires --operator-id")
    settings = get_settings()
    engine = create_engine(settings)
    service = MaintenanceService(engine)

    async def run() -> dict[str, Any]:
        try:
            if mode == "enter":
                return await service.enter_freeze(operator_id, args.reason or "maintenance window")
            if mode == "exit":
                return await service.exit_freeze(operator_id)
            return await service.freeze_status()
        finally:
            await engine.dispose()

    try:
        report = asyncio.run(run())
    except PermissionError as exc:
        _json_error("operator_forbidden", str(exc), exit_code=3)
    print(json.dumps(report, sort_keys=True))


def _bootstrap_admin() -> None:
    """Create the first super administrator through a local operator command."""
    settings = get_settings()
    email = os.environ.get("IMA_BOOTSTRAP_EMAIL")
    password = os.environ.get("IMA_BOOTSTRAP_PASSWORD")
    if not email or not password:
        if settings.environment == "production":
            raise SystemExit(
                "IMA_BOOTSTRAP_EMAIL and IMA_BOOTSTRAP_PASSWORD are required in production"
            )
        email = input("Administrator email: ").strip()
        password = input("Administrator password: ")
    if len(password) < 12:
        raise SystemExit("bootstrap password must be at least 12 characters")
    from datetime import UTC, datetime
    from secrets import token_urlsafe

    from argon2 import PasswordHasher

    phc = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash(password)
    conninfo = (
        settings.database_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM ima.platform_role_assignments WHERE role='super_admin'"
            )
            existing = cursor.fetchone()
            if existing and existing[0]:
                raise SystemExit("an active super administrator already exists")
            now = datetime.now(UTC)
            user_id = new_legacy_id()
            cursor.execute(
                """INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (%s,%s,%s,%s,true,false,%s,%s,%s) ON CONFLICT(normalized_email) DO UPDATE SET is_active=true""",
                (
                    user_id,
                    email,
                    email.casefold(),
                    email.split("@", 1)[0],
                    token_urlsafe(32),
                    now,
                    now,
                ),
            )
            cursor.execute(
                "SELECT id FROM ima.users WHERE normalized_email=%s", (email.casefold(),)
            )
            found = cursor.fetchone()
            if not found:
                raise SystemExit("bootstrap account could not be created")
            user_id = found[0]
            cursor.execute(
                """INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (%s,%s,'argon2id-v1-m65536-t3-p2',%s) ON CONFLICT(user_id) DO UPDATE SET phc_hash=EXCLUDED.phc_hash,changed_at=EXCLUDED.changed_at""",
                (user_id, phc, now),
            )
            cursor.execute(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (%s,'super_admin',%s) ON CONFLICT DO NOTHING",
                (user_id, now),
            )
        connection.commit()
    print(f"bootstrapped super administrator {email}")


def _register_mcp_client_sync(
    *,
    client_id: str | None,
    client_name: str | None,
    client_type: str | None,
    app_type: str | None,
    auth_method: str | None,
    redirect_uris: list[str] | None,
    operator_id: str | None = None,
) -> None:
    """Register a pre-registered OAuth MCP client."""
    from sqlalchemy.exc import IntegrityError

    from ima.infrastructure.db.engine import create_engine
    from ima.infrastructure.oauth import McpOauthRepository

    settings = get_settings()
    errors: list[str] = []

    # Validate client_id format (lowercase alphanumeric with hyphens)
    if not client_id:
        errors.append("--client-id is required")
    elif len(client_id) > 128 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", client_id):
        errors.append("--client-id must be lowercase alphanumeric with hyphens only")

    # Validate client_name
    if not client_name:
        errors.append("--client-name is required")
    elif not client_name.strip():
        errors.append("--client-name must not be blank")
    elif len(client_name) > 200:
        errors.append("--client-name must be <= 200 characters")

    # Validate client_type
    if not client_type:
        errors.append("--client-type is required (public or confidential)")
    elif client_type not in ("public", "confidential"):
        errors.append("--client-type must be 'public' or 'confidential'")

    # Validate app_type
    if not app_type:
        errors.append("--app-type is required (native or web)")
    elif app_type not in ("native", "web"):
        errors.append("--app-type must be 'native' or 'web'")

    # Validate auth_method - MVP only supports "none" for public clients
    if not auth_method:
        errors.append("--auth-method is required; MVP supports only 'none'")
    elif auth_method != "none":
        errors.append("--auth-method must be 'none' (MVP limitation)")

    # Validate that public clients use none auth method
    if client_type == "confidential" and auth_method == "none":
        errors.append(
            "confidential clients must have token_endpoint_auth_method='client_secret_basic' (not supported in MVP)"
        )
    if not operator_id:
        errors.append("--operator-id is required and must identify an active super-admin")

    # Initialize seen_uris before validation loop
    seen_uris: set[str] = set()

    # Validate redirect URIs
    if not redirect_uris:
        errors.append("at least one --redirect-uri is required")
    else:
        for uri in redirect_uris:
            try:
                parsed = urlsplit(uri)
                _ = parsed.port
            except ValueError:
                parsed = None
            safe = bool(
                parsed
                and parsed.hostname
                and not parsed.fragment
                and not parsed.username
                and not parsed.password
                and (
                    parsed.scheme == "https"
                    or (
                        parsed.scheme == "http"
                        and parsed.hostname.casefold() in {"localhost", "127.0.0.1", "::1"}
                    )
                )
                and len(uri) <= 512
            )
            if not safe:
                errors.append(
                    f"--redirect-uri must be HTTPS or loopback HTTP without credentials or fragment: {uri}"
                )
            # No duplicates
            if uri in seen_uris:
                errors.append(f"duplicate --redirect-uri: {uri}")
            else:
                seen_uris.add(uri)

    if errors:
        _json_error("invalid_request", "; ".join(errors), exit_code=1)

    # Canonical resource MUST come from settings - never operator input
    canonical_resource = settings.mcp_resource_url

    # For MVP public clients, no secret needed (auth_method="none")
    client_secret = None

    async def register() -> object:
        engine = create_engine(settings)
        try:
            return await McpOauthRepository(engine, settings).register_client(
                client_id=str(client_id),
                client_name=str(client_name).strip(),
                client_type=str(client_type),
                token_endpoint_auth_method=str(auth_method),
                application_type=str(app_type),
                canonical_resource=canonical_resource,
                redirect_uris=tuple(sorted(seen_uris)),
                created_by=operator_id,
                client_secret=client_secret,
            )
        finally:
            await engine.dispose()

    try:
        client_uuid = asyncio.run(register())

        result = {
            "success": True,
            "clientId": client_id,
            "clientName": client_name,
            "clientType": client_type,
            "applicationType": app_type,
            "redirectUris": tuple(sorted(seen_uris)),
            "resource": canonical_resource,
            "uuid": str(client_uuid),
        }

        print(json.dumps(result, sort_keys=True))

    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            _json_error(
                "duplicate_client_id", f"client_id '{client_id}' already registered", exit_code=5
            )
        _json_error("registration_failed", "database constraint rejected registration", exit_code=2)
    except PermissionError:
        _json_error("operator_forbidden", "operator is not an active super-admin", exit_code=3)
    except Exception as exc:
        _json_error("registration_failed", type(exc).__name__, exit_code=2)
