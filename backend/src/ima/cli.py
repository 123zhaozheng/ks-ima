"""Explicit operational commands."""

# Bootstrap SQL is deliberately visible in one command for operator review.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from ima.application.identity import new_legacy_id
from ima.application.legacy_identity import compatible_argon2id_phc, compatible_totp_secret
from ima.config import get_settings
from ima.infrastructure.auth.security import encrypt_secret
from ima.infrastructure.tasks.app import create_task_app


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
            "migrate-legacy-identity",
        ),
    )
    parser.add_argument(
        "action", nargs="?", choices=("plan", "apply", "verify", "report"), default="report"
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
    if args.command == "migrate-legacy-identity":
        _legacy_identity_report(args.action)
        return
    asyncio.run(_run_worker())


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
    if task_schema_exists is None:
        with task_app.open():
            task_app.schema_manager.apply_schema()


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


def _legacy_identity_report(action: str = "report") -> None:
    """Run a resumable, per-record legacy identity migration."""
    settings = get_settings()
    conninfo = (
        settings.database_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.user'), to_regclass('public.account'), to_regclass('public.session')"
            )
            tables = cursor.fetchone()
            if not tables or not tables[0]:
                raise SystemExit("legacy identity report returned no public user table")
            cursor.execute(
                """SELECT u.id,u.name,u.email,
                (SELECT a.password FROM "account" a WHERE a.user_id=u.id AND a.provider_id='credential' ORDER BY a.updated_at DESC LIMIT 1),
                (SELECT t.secret FROM "two_factor" t WHERE t.user_id=u.id ORDER BY t.id LIMIT 1)
                FROM "user" u ORDER BY u.id"""
            )
            users = cursor.fetchall()
            cursor.execute('SELECT id,name FROM "workspace" ORDER BY id')
            workspaces = cursor.fetchall()

            if action == "plan":
                compatible_passwords = sum(compatible_argon2id_phc(user[3]) for user in users)
                compatible_totp = sum(compatible_totp_secret(user[4]) for user in users)
                cursor.execute(
                    "SELECT status,count(*) FROM ima.legacy_identity_migration GROUP BY status ORDER BY status"
                )
                checkpoints = {str(status): int(count) for status, count in cursor.fetchall()}
                print(
                    {
                        "action": action,
                        "users": len(users),
                        "workspaces": len(workspaces),
                        "compatiblePasswords": compatible_passwords,
                        "forcedPasswordResets": len(users) - compatible_passwords,
                        "compatibleTotp": compatible_totp,
                        "disabledTotp": len(users) - compatible_totp,
                        "checkpoints": checkpoints,
                        "sessionsRevoked": False,
                        "secretValues": False,
                    }
                )
                return

            if action == "apply":
                for user_id, name, email, phc, totp in users:
                    fingerprint = secrets.token_hex(16)
                    try:
                        with connection.transaction():
                            cursor.execute(
                                """INSERT INTO ima.legacy_identity_migration(source_kind,source_id,status,attempts,source_fingerprint,updated_at) VALUES ('user',%s,'running',1,%s,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='running',attempts=ima.legacy_identity_migration.attempts+1,source_fingerprint=EXCLUDED.source_fingerprint,updated_at=now()""",
                                (user_id, fingerprint),
                            )
                            compatible_password = compatible_argon2id_phc(phc)
                            cursor.execute(
                                """INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (%s,%s,%s,%s,true,%s,%s,now(),now()) ON CONFLICT(id) DO UPDATE SET email=EXCLUDED.email,display_name=EXCLUDED.display_name,password_reset_required=EXCLUDED.password_reset_required,updated_at=now()""",
                                (
                                    user_id,
                                    email,
                                    email.casefold(),
                                    name,
                                    not compatible_password,
                                    secrets.token_hex(24),
                                ),
                            )
                            if compatible_password:
                                cursor.execute(
                                    """INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (%s,%s,'legacy-verified',now()) ON CONFLICT(user_id) DO UPDATE SET phc_hash=EXCLUDED.phc_hash,parameter_version='legacy-verified',changed_at=now()""",
                                    (user_id, phc),
                                )
                            else:
                                cursor.execute(
                                    "DELETE FROM ima.password_credentials WHERE user_id=%s",
                                    (user_id,),
                                )
                            cursor.execute(
                                "DELETE FROM ima.totp_credentials WHERE user_id=%s", (user_id,)
                            )
                            cursor.execute(
                                "DELETE FROM ima.recovery_codes WHERE user_id=%s", (user_id,)
                            )
                            if compatible_totp_secret(totp):
                                cursor.execute(
                                    """INSERT INTO ima.totp_credentials(user_id,encrypted_secret,confirmed_at,created_at) VALUES (%s,%s,now(),now())""",
                                    (
                                        user_id,
                                        encrypt_secret(
                                            totp,
                                            settings.totp_encryption_key.get_secret_value(),
                                            user_id,
                                        ),
                                    ),
                                )
                            cursor.execute(
                                """INSERT INTO public."userData"(id,perfs,data) VALUES (%s,'{}'::jsonb,'{}'::jsonb) ON CONFLICT(id) DO NOTHING""",
                                (user_id,),
                            )
                            cursor.execute(
                                """INSERT INTO ima.legacy_identity_projection(user_id,status,migrated_at,updated_at) VALUES (%s,'complete',now(),now()) ON CONFLICT(user_id) DO UPDATE SET status='complete',migrated_at=now(),updated_at=now()""",
                                (user_id,),
                            )
                            cursor.execute(
                                "UPDATE ima.legacy_identity_migration SET status='complete',processed_at=now(),last_error=NULL,updated_at=now() WHERE source_kind='user' AND source_id=%s",
                                (user_id,),
                            )
                    except Exception as exc:
                        connection.rollback()
                        cursor.execute(
                            """INSERT INTO ima.legacy_identity_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('user',%s,'failed',1,%s,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error=%s,updated_at=now()""",
                            (user_id, type(exc).__name__, type(exc).__name__),
                        )
                        connection.commit()
                with connection.transaction():
                    cursor.execute("DELETE FROM public.session")
                    cursor.execute(
                        """INSERT INTO ima.workspaces(id,name,is_active,created_at,updated_at) SELECT w.id,w.name,true,now(),now() FROM public."workspace" w ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,updated_at=now()"""
                    )
                print(
                    {
                        "action": action,
                        "users": len(users),
                        "workspaces": len(workspaces),
                        "sessionsRevoked": True,
                    }
                )
                return

            cursor.execute(
                "SELECT status,count(*) FROM ima.legacy_identity_migration GROUP BY status ORDER BY status"
            )
            statuses = {str(status): int(count) for status, count in cursor.fetchall()}
            if action == "verify":
                cursor.execute("SELECT count(*) FROM public.session")
                session_row = cursor.fetchone()
                sessions = int(session_row[0]) if session_row else 0
                cursor.execute(
                    "SELECT count(*) FROM ima.legacy_identity_migration WHERE status='failed'"
                )
                failed_row = cursor.fetchone()
                failed = int(failed_row[0]) if failed_row else 0
                verification_errors: list[dict[str, str]] = []
                workspace_ids = {str(workspace_id) for workspace_id, _ in workspaces}
                for user_id, _name, _email, phc, totp in users:
                    cursor.execute(
                        """SELECT u.password_reset_required,
                        (SELECT count(*) FROM ima.password_credentials p WHERE p.user_id=u.id),
                        (SELECT count(*) FROM ima.totp_credentials t WHERE t.user_id=u.id),
                        (SELECT count(*) FROM ima.recovery_codes r WHERE r.user_id=u.id),
                        (SELECT status FROM ima.legacy_identity_projection p WHERE p.user_id=u.id),
                        (SELECT count(*) FROM public."userData" d WHERE d.id=u.id),
                        (SELECT count(*) FROM ima.workspaces w WHERE w.id=u.id)
                        FROM ima.users u WHERE u.id=%s""",
                        (user_id,),
                    )
                    target = cursor.fetchone()
                    expected_password = compatible_argon2id_phc(phc)
                    expected_totp = compatible_totp_secret(totp)
                    expected_workspace = 1 if str(user_id) in workspace_ids else 0
                    if not target:
                        verification_errors.append(
                            {
                                "sourceKind": "user",
                                "sourceId": str(user_id),
                                "reason": "missing_user",
                            }
                        )
                        continue
                    checks = (
                        (bool(target[0]) is (not expected_password), "password_reset_state"),
                        (int(target[1]) == int(expected_password), "password_credential_state"),
                        (int(target[2]) == int(expected_totp), "totp_state"),
                        (int(target[3]) == 0, "recovery_code_side_effect"),
                        (target[4] == "complete", "projection_state"),
                        (int(target[5]) == 1, "legacy_user_data_projection"),
                        (int(target[6]) == expected_workspace, "workspace_side_effect"),
                    )
                    for valid, reason in checks:
                        if not valid:
                            verification_errors.append(
                                {"sourceKind": "user", "sourceId": str(user_id), "reason": reason}
                            )
                for workspace_id, _name in workspaces:
                    cursor.execute(
                        "SELECT count(*) FROM ima.workspaces WHERE id=%s", (workspace_id,)
                    )
                    workspace_row = cursor.fetchone()
                    if not workspace_row or int(workspace_row[0]) != 1:
                        verification_errors.append(
                            {
                                "sourceKind": "workspace",
                                "sourceId": str(workspace_id),
                                "reason": "missing_workspace",
                            }
                        )
                if statuses.get("complete", 0) != len(users):
                    verification_errors.append(
                        {"sourceKind": "migration", "sourceId": "all", "reason": "checkpoint_count"}
                    )
                if sessions or failed or verification_errors:
                    raise SystemExit(
                        "legacy identity verification failed: "
                        f"sessions={sessions}, failed={failed}, records={verification_errors}"
                    )
                print(
                    {
                        "action": action,
                        "statuses": statuses,
                        "sessionsRevoked": True,
                        "secretValues": False,
                    }
                )
                return
            print(
                {
                    "action": "report",
                    "statuses": statuses,
                    "sessionsRevoked": False,
                    "secretValues": False,
                }
            )
