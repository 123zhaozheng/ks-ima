"""Explicit operational commands."""

# Bootstrap SQL is deliberately visible in one command for operator review.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg

from ima.application.identity import new_legacy_id
from ima.application.legacy_identity import compatible_argon2id_phc, compatible_totp_secret
from ima.config import get_settings
from ima.domain.authorization import DEFAULT_ROLE_GRANTS, legacy_role
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
            "migrate-legacy-authorization",
            "rotate-model-secrets",
            "migrate-legacy-model-governance",
        ),
    )
    parser.add_argument(
        "action", nargs="?", choices=("plan", "apply", "verify", "report"), default="report"
    )
    parser.add_argument(
        "--mapping-file",
        dest="mapping_file",
        type=Path,
        help="Explicit JSON source-to-target capability mapping for legacy model governance",
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
    if args.command == "migrate-legacy-authorization":
        _legacy_authorization_report(args.action)
        return
    if args.command == "rotate-model-secrets":
        _rotate_model_secrets(args.action)
        return
    if args.command == "migrate-legacy-model-governance":
        _legacy_model_governance_report(args.action, args.mapping_file)
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


def _rotate_model_secrets(action: str) -> None:
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
        summary = {
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


def _legacy_model_governance_report(action: str, mapping_file: Path | None = None) -> None:
    """Inventory and conservatively import legacy providers/models.

    Legacy settings are treated as migration input only.  Ambiguous providers,
    malformed URLs, and all profile/RAG translations remain review checkpoints;
    no plaintext value is included in reports or audit metadata.
    """

    settings = get_settings()
    conninfo = (
        settings.database_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with psycopg.connect(conninfo) as connection:
        tables = connection.execute(
            "SELECT to_regclass('public.provider'),to_regclass('public.model'),to_regclass('public.globalSettings'),to_regclass('public.entity'),to_regclass('public.chunk')"
        ).fetchone()
        table_flags: tuple[Any, ...] = tuple(tables) if tables else ()
        source_available = bool(table_flags and table_flags[0] and table_flags[1])
        providers = (
            connection.execute(
                'SELECT id,"rootId",type,settings FROM "provider" ORDER BY id'
            ).fetchall()
            if source_available
            else []
        )
        models = (
            connection.execute(
                'SELECT id,"rootId","entityId",name,label,settings FROM "model" ORDER BY id'
            ).fetchall()
            if source_available
            else []
        )
        global_row = (
            connection.execute('SELECT count(*) FROM "globalSettings"').fetchone()
            if table_flags and table_flags[2]
            else None
        )
        tuning_row = (
            connection.execute(
                "SELECT count(*) FROM \"entity\" WHERE \"conf\" ?| ARRAY['chatModelId','embeddingModelId','rerankModelId','chunkSize','topK']"
            ).fetchone()
            if table_flags and table_flags[3]
            else None
        )
        chunk_row = (
            connection.execute(
                'SELECT count(*) FROM "chunk" WHERE embedding IS NOT NULL'
            ).fetchone()
            if table_flags and table_flags[4]
            else None
        )
        global_settings_count = int(global_row[0]) if global_row else 0
        workspace_tuning_count = int(tuning_row[0]) if tuning_row else 0
        indexed_chunk_count = int(chunk_row[0]) if chunk_row else 0
        mapping: dict[str, Any] = {}
        mapping_file = mapping_file or (
            Path(os.environ["IMA_MODEL_GOVERNANCE_MAPPING"])
            if os.environ.get("IMA_MODEL_GOVERNANCE_MAPPING")
            else None
        )
        if mapping_file:
            try:
                loaded = json.loads(Path(mapping_file).read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    mapping = loaded
            except (OSError, json.JSONDecodeError):
                mapping = {}
        summary: dict[str, Any] = {
            "action": action,
            "sourceAvailable": source_available,
            "providers": len(providers),
            "models": len(models),
            "globalSettings": global_settings_count,
            "workspaceTuningRows": workspace_tuning_count,
            "indexedChunks": indexed_chunk_count,
            "mappingFile": bool(mapping_file),
            "secretValues": False,
            "review": 0,
        }
        if action == "plan":
            print(summary)
            return
        key_ring = __import__(
            "ima.infrastructure.model_gateway.secrets", fromlist=["SecretKeyRing"]
        ).SecretKeyRing(
            settings.model_key_ring.get_secret_value(),
            settings.model_current_key_version,
            settings.model_fingerprint_key.get_secret_value(),
        )
        if action == "apply" and source_available:
            for provider_id, _root_id, _provider_type, raw_settings in providers:
                source_id = str(provider_id)
                fingerprint = hashlib.sha256(
                    json.dumps(raw_settings or {}, sort_keys=True, default=str).encode()
                ).hexdigest()
                checkpoint = connection.execute(
                    "SELECT status,source_fingerprint FROM ima.legacy_model_governance_migration WHERE source_kind='provider' AND source_id=%s",
                    (source_id,),
                ).fetchone()
                if checkpoint and checkpoint[0] == "complete" and checkpoint[1] == fingerprint:
                    continue
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO ima.legacy_model_governance_migration(source_kind,source_id,source_fingerprint,status,attempts,updated_at) VALUES ('provider',%s,%s,'running',1,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET attempts=ima.legacy_model_governance_migration.attempts+1,updated_at=now()",
                        (source_id, fingerprint),
                    )
                    settings_json = raw_settings if isinstance(raw_settings, dict) else {}
                    base_url = (
                        settings_json.get("baseURL")
                        or settings_json.get("baseUrl")
                        or settings_json.get("url")
                    )
                    secret = settings_json.get("apiKey")
                    # A target gateway can only be imported when the source is
                    # structurally explicit; it always remains disabled.
                    if (
                        not isinstance(base_url, str)
                        or not base_url
                        or not isinstance(secret, str)
                        or not secret
                    ):
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='review',last_error='ambiguous_provider',updated_at=now() WHERE source_kind='provider' AND source_id=%s",
                            (source_id,),
                        )
                        summary["review"] += 1
                        continue
                    try:
                        from ima.domain.model_governance import ModelCapability, ModelGatewayInput

                        checked = ModelGatewayInput(
                            name=f"legacy-{source_id[:80]}",
                            baseUrl=base_url,
                            allowedCapabilities=frozenset(ModelCapability),
                            insecurePrivate=base_url.startswith("http://"),
                            allowedHosts=(),
                        )
                        gateway_id = uuid4()
                        secret_id = uuid4()
                        envelope = key_ring.encrypt(
                            secret, gateway_id=str(gateway_id), secret_id=str(secret_id)
                        )
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
                        scheme = (
                            "private_http" if checked.base_url.startswith("http://") else "required"
                        )
                        connection.execute(
                            "INSERT INTO ima.model_gateways(id,name,normalized_base_url,enabled,allowed_capabilities,tls_mode,insecure_private,connect_timeout_ms,read_timeout_ms,write_timeout_ms,pool_timeout_ms,max_response_bytes,allowed_hosts,allowed_cidrs,secret_id,created_at,updated_at) VALUES (%s,%s,%s,false,%s,%s,%s,5000,30000,30000,5000,8388608,%s,%s,%s,now(),now())",
                            (
                                gateway_id,
                                checked.name,
                                checked.base_url.rstrip("/"),
                                list(item.value for item in checked.allowed_capabilities),
                                scheme,
                                checked.insecure_private,
                                list(checked.allowed_hosts),
                                list(checked.allowed_cidrs),
                                secret_id,
                            ),
                        )
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='complete',mapped_target_id=%s,processed_at=now(),updated_at=now() WHERE source_kind='provider' AND source_id=%s",
                            (gateway_id, source_id),
                        )
                    except Exception as exc:
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='review',last_error=%s,updated_at=now() WHERE source_kind='provider' AND source_id=%s",
                            (type(exc).__name__, source_id),
                        )
                        summary["review"] += 1
            for model_id, _root_id, provider_id, remote_name, label, raw_model_settings in models:
                source_id = str(model_id)
                fingerprint = hashlib.sha256(
                    json.dumps(raw_model_settings or {}, sort_keys=True, default=str).encode()
                ).hexdigest()
                checkpoint = connection.execute(
                    "SELECT status,source_fingerprint FROM ima.legacy_model_governance_migration WHERE source_kind='model' AND source_id=%s",
                    (source_id,),
                ).fetchone()
                if checkpoint and checkpoint[0] == "complete" and checkpoint[1] == fingerprint:
                    continue
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO ima.legacy_model_governance_migration(source_kind,source_id,source_fingerprint,status,attempts,updated_at) VALUES ('model',%s,%s,'running',1,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET attempts=ima.legacy_model_governance_migration.attempts+1,updated_at=now()",
                        (source_id, fingerprint),
                    )
                    explicit = mapping.get(source_id)
                    capability = explicit.get("capability") if isinstance(explicit, dict) else None
                    if capability not in {"chat", "embedding", "rerank"}:
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='review',last_error='ambiguous_capability',updated_at=now() WHERE source_kind='model' AND source_id=%s",
                            (source_id,),
                        )
                        summary["review"] += 1
                        continue
                    gateway = connection.execute(
                        "SELECT mapped_target_id FROM ima.legacy_model_governance_migration WHERE source_kind='provider' AND source_id=%s AND status='complete'",
                        (str(provider_id),),
                    ).fetchone()
                    dimension = explicit.get("dimension") if isinstance(explicit, dict) else None
                    if capability == "embedding" and (
                        not isinstance(dimension, int) or dimension < 1
                    ):
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='review',last_error='embedding_dimension_required',updated_at=now() WHERE source_kind='model' AND source_id=%s",
                            (source_id,),
                        )
                        summary["review"] += 1
                        continue
                    if not gateway or not gateway[0]:
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='review',last_error='missing_provider_mapping',updated_at=now() WHERE source_kind='model' AND source_id=%s",
                            (source_id,),
                        )
                        summary["review"] += 1
                        continue
                    try:
                        target_id = uuid4()
                        connection.execute(
                            "INSERT INTO ima.governed_models(id,gateway_id,remote_name,capability,business_label,enabled,validated,embedding_dimension,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,false,false,%s,now(),now())",
                            (
                                target_id,
                                gateway[0],
                                str(remote_name),
                                capability,
                                str(label or remote_name),
                                dimension if capability == "embedding" else None,
                            ),
                        )
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='complete',mapped_target_id=%s,processed_at=now(),updated_at=now() WHERE source_kind='model' AND source_id=%s",
                            (target_id, source_id),
                        )
                    except Exception as exc:
                        connection.execute(
                            "UPDATE ima.legacy_model_governance_migration SET status='review',last_error=%s,updated_at=now() WHERE source_kind='model' AND source_id=%s",
                            (type(exc).__name__, source_id),
                        )
                        summary["review"] += 1
        if action in {"verify", "report"}:
            statuses = connection.execute(
                "SELECT status,count(*) FROM ima.legacy_model_governance_migration GROUP BY status ORDER BY status"
            ).fetchall()
            summary["statuses"] = {str(status): int(count) for status, count in statuses}
        print(summary)


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


def _legacy_authorization_report(action: str = "report") -> None:
    """Import the legacy membership/folder slice with record checkpoints.

    This command is intentionally conservative: malformed ACLs and hierarchy
    records are checkpointed as failures instead of being guessed into target
    state. Every successful source record is committed independently so a later
    run can resume without replaying completed rows.
    """
    settings = get_settings()
    conninfo = (
        settings.database_url.get_secret_value()
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )
    with psycopg.connect(conninfo) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.member'),to_regclass('public.entity'),to_regclass('public.workspace')"
            )
            tables = cursor.fetchone()
            if not tables or not tables[0] or not tables[1] or not tables[2]:
                raise SystemExit(
                    "legacy authorization migration requires member, entity, and workspace tables"
                )
            cursor.execute('SELECT id,name,"ownerId" FROM "workspace" ORDER BY id')
            workspaces = cursor.fetchall()
            cursor.execute(
                'SELECT "workspaceId","userId",role FROM "member" ORDER BY "workspaceId","userId"'
            )
            members = cursor.fetchall()
            cursor.execute(
                'SELECT id,"rootId","parentId",type,name,conf FROM "entity" WHERE type=\'dir\' ORDER BY "rootId",id'
            )
            folders = cursor.fetchall()
            cursor.execute(
                "SELECT status,count(*) FROM ima.workspace_authorization_migration GROUP BY status ORDER BY status"
            )
            statuses = {str(row[0]): int(row[1]) for row in cursor.fetchall()}
            summary = {
                "action": action,
                "workspaces": len(workspaces),
                "members": len(members),
                "folders": len(folders),
                "statuses": statuses,
                "secretValues": False,
            }
            if action == "plan":
                print(summary)
                return
            if action in {"apply", "verify"}:
                failures: list[dict[str, str]] = []
                if action == "apply":
                    for workspace_id, name, owner_id in workspaces:
                        try:
                            with connection.transaction():
                                cursor.execute(
                                    "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,updated_at) VALUES ('workspace',%s,'running',1,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='running',attempts=ima.workspace_authorization_migration.attempts+1,updated_at=now()",
                                    (workspace_id,),
                                )
                                cursor.execute(
                                    "INSERT INTO ima.workspaces(id,name,is_active,created_at,updated_at) VALUES (%s,%s,true,now(),now()) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,updated_at=now()",
                                    (workspace_id, name or workspace_id),
                                )
                                cursor.execute(
                                    "INSERT INTO ima.folders(id,workspace_id,parent_id,name,normalized_name,is_root,acl_anchor_id,created_at,updated_at) VALUES (%s,%s,NULL,%s,%s,true,%s,now(),now()) ON CONFLICT(id) DO NOTHING",
                                    (
                                        workspace_id,
                                        workspace_id,
                                        name or workspace_id,
                                        str(name or workspace_id).casefold(),
                                        workspace_id,
                                    ),
                                )
                                cursor.execute(
                                    "INSERT INTO ima.folder_closure(workspace_id,ancestor_id,descendant_id,depth) VALUES (%s,%s,%s,0) ON CONFLICT DO NOTHING",
                                    (workspace_id, workspace_id, workspace_id),
                                )
                                cursor.execute(
                                    "INSERT INTO ima.folder_acls(id,folder_id,created_at,updated_at) VALUES (%s,%s,now(),now()) ON CONFLICT(folder_id) DO NOTHING",
                                    (str(uuid4()), workspace_id),
                                )
                                for role, grants in DEFAULT_ROLE_GRANTS.items():
                                    for grant in grants:
                                        cursor.execute(
                                            "INSERT INTO ima.folder_acl_entries(acl_id,subject_type,subject_id,action) SELECT id,'role',%s,%s FROM ima.folder_acls WHERE folder_id=%s ON CONFLICT DO NOTHING",
                                            (role.value, grant.value, workspace_id),
                                        )
                                if owner_id:
                                    cursor.execute(
                                        "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,joined_at,updated_at) SELECT %s,id,'workspace_admin','active',now(),now() FROM ima.users WHERE id=%s ON CONFLICT DO NOTHING",
                                        (workspace_id, owner_id),
                                    )
                                cursor.execute(
                                    "UPDATE ima.workspace_authorization_migration SET status='complete',processed_at=now(),last_error=NULL,updated_at=now() WHERE source_kind='workspace' AND source_id=%s",
                                    (workspace_id,),
                                )
                        except Exception as exc:
                            connection.rollback()
                            failures.append(
                                {
                                    "sourceKind": "workspace",
                                    "sourceId": str(workspace_id),
                                    "reason": type(exc).__name__,
                                }
                            )
                            cursor.execute(
                                "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('workspace',%s,'failed',1,%s,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error=EXCLUDED.last_error,updated_at=now()",
                                (workspace_id, type(exc).__name__),
                            )
                            connection.commit()
                    for member_id, user_id, source_role in members:
                        try:
                            mapped = legacy_role(str(source_role)).value
                        except KeyError:
                            failures.append(
                                {
                                    "sourceKind": "member",
                                    "sourceId": str(member_id),
                                    "reason": "invalid_role",
                                }
                            )
                            cursor.execute(
                                "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('member',%s,'failed',1,'invalid_role',now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error='invalid_role',updated_at=now()",
                                (member_id,),
                            )
                            connection.commit()
                            continue
                        try:
                            with connection.transaction():
                                cursor.execute(
                                    "SELECT 1 FROM public.member WHERE id=%s", (member_id,)
                                )
                                cursor.execute(
                                    'SELECT "workspaceId" FROM public.member WHERE id=%s',
                                    (member_id,),
                                )
                                row = cursor.fetchone()
                                if not row:
                                    raise ValueError("missing_workspace")
                                cursor.execute(
                                    "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,joined_at,updated_at) SELECT %s,%s,%s,'active',now(),now() FROM ima.users WHERE id=%s ON CONFLICT(workspace_id,user_id) DO UPDATE SET role=EXCLUDED.role,state='active',updated_at=now()",
                                    (row[0], user_id, mapped, user_id),
                                )
                                if cursor.rowcount != 1:
                                    raise ValueError("missing_user")
                                cursor.execute(
                                    "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,updated_at) VALUES ('member',%s,'complete',1,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='complete',updated_at=now()",
                                    (member_id,),
                                )
                        except Exception as exc:
                            connection.rollback()
                            failures.append(
                                {
                                    "sourceKind": "member",
                                    "sourceId": str(member_id),
                                    "reason": type(exc).__name__,
                                }
                            )
                            cursor.execute(
                                "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('member',%s,'failed',1,%s,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error=EXCLUDED.last_error,updated_at=now()",
                                (member_id, type(exc).__name__),
                            )
                            connection.commit()
                    # Folder import is topological and bounded. A source cycle
                    # remains failed rather than becoming an arbitrary tree.
                    pending = list(folders)
                    source_roots = {
                        str(source_id): str(source_root) for source_id, source_root, *_ in folders
                    }
                    while pending:
                        progressed = False
                        for row in pending[:]:
                            folder_id, root_id, parent_id, _kind, name, _conf = row
                            if str(folder_id) == str(root_id):
                                try:
                                    root_entries, root_error = _parse_legacy_acl(_conf)
                                    if root_error:
                                        raise ValueError(root_error)
                                    if root_entries is not None:
                                        with connection.transaction():
                                            cursor.execute(
                                                "SELECT id FROM ima.folder_acls WHERE folder_id=%s",
                                                (root_id,),
                                            )
                                            acl_row = cursor.fetchone()
                                            if not acl_row:
                                                raise ValueError("missing_root_acl")
                                            cursor.execute(
                                                "DELETE FROM ima.folder_acl_entries WHERE acl_id=%s",
                                                (acl_row[0],),
                                            )
                                            for (
                                                subject_type,
                                                subject_id,
                                                legacy_grant,
                                            ) in root_entries:
                                                if subject_type == "user":
                                                    cursor.execute(
                                                        "SELECT 1 FROM ima.workspace_members WHERE workspace_id=%s AND user_id=%s AND state='active'",
                                                        (root_id, subject_id),
                                                    )
                                                    if not cursor.fetchone():
                                                        raise ValueError("missing_acl_user")
                                                cursor.execute(
                                                    "INSERT INTO ima.folder_acl_entries(acl_id,subject_type,subject_id,action) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                                    (
                                                        acl_row[0],
                                                        subject_type,
                                                        subject_id,
                                                        legacy_grant,
                                                    ),
                                                )
                                    progressed = True
                                except Exception as exc:
                                    connection.rollback()
                                    failures.append(
                                        {
                                            "sourceKind": "folder",
                                            "sourceId": str(folder_id),
                                            "reason": type(exc).__name__,
                                        }
                                    )
                                    cursor.execute(
                                        "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('folder',%s,'failed',1,%s,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error=EXCLUDED.last_error,updated_at=now()",
                                        (folder_id, type(exc).__name__),
                                    )
                                    connection.commit()
                                pending.remove(row)
                                continue
                            if (
                                parent_id is not None
                                and str(parent_id) in source_roots
                                and source_roots[str(parent_id)] != str(root_id)
                            ):
                                failures.append(
                                    {
                                        "sourceKind": "folder",
                                        "sourceId": str(folder_id),
                                        "reason": "cross_workspace_parent",
                                    }
                                )
                                cursor.execute(
                                    "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('folder',%s,'failed',1,'cross_workspace_parent',now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error='cross_workspace_parent',updated_at=now()",
                                    (folder_id,),
                                )
                                connection.commit()
                                pending.remove(row)
                                progressed = True
                                continue
                            cursor.execute(
                                "SELECT 1 FROM ima.folders WHERE id=%s AND workspace_id=%s",
                                (parent_id, root_id),
                            )
                            if not cursor.fetchone():
                                continue
                            try:
                                with connection.transaction():
                                    cursor.execute(
                                        "INSERT INTO ima.folders(id,workspace_id,parent_id,name,normalized_name,is_root,acl_anchor_id,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,false,(SELECT acl_anchor_id FROM ima.folders WHERE id=%s),now(),now()) ON CONFLICT(id) DO NOTHING",
                                        (
                                            folder_id,
                                            root_id,
                                            parent_id,
                                            name or folder_id,
                                            str(name or folder_id).casefold(),
                                            parent_id,
                                        ),
                                    )
                                    cursor.execute(
                                        "INSERT INTO ima.folder_closure(workspace_id,ancestor_id,descendant_id,depth) SELECT %s,ancestor_id,%s,depth+1 FROM ima.folder_closure WHERE workspace_id=%s AND descendant_id=%s UNION ALL SELECT %s,%s,%s,0 ON CONFLICT DO NOTHING",
                                        (
                                            root_id,
                                            folder_id,
                                            root_id,
                                            parent_id,
                                            root_id,
                                            folder_id,
                                            folder_id,
                                        ),
                                    )
                                    acl_entries, acl_error = _parse_legacy_acl(_conf)
                                    if acl_error:
                                        raise ValueError(acl_error)
                                    if acl_entries is not None:
                                        acl_id = str(uuid4())
                                        cursor.execute(
                                            "INSERT INTO ima.folder_acls(id,folder_id,created_at,updated_at) VALUES (%s,%s,now(),now()) ON CONFLICT(folder_id) DO UPDATE SET version=ima.folder_acls.version+1,updated_at=now() RETURNING id",
                                            (acl_id, folder_id),
                                        )
                                        acl_row = cursor.fetchone()
                                        if acl_row:
                                            acl_id = str(acl_row[0])
                                        for subject_type, subject_id, legacy_grant in acl_entries:
                                            if subject_type == "user":
                                                cursor.execute(
                                                    "SELECT 1 FROM ima.workspace_members WHERE workspace_id=%s AND user_id=%s AND state='active'",
                                                    (root_id, subject_id),
                                                )
                                                if not cursor.fetchone():
                                                    raise ValueError("missing_acl_user")
                                            cursor.execute(
                                                "INSERT INTO ima.folder_acl_entries(acl_id,subject_type,subject_id,action) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                                                (acl_id, subject_type, subject_id, legacy_grant),
                                            )
                                        cursor.execute(
                                            "UPDATE ima.folders SET acl_anchor_id=%s WHERE id=%s",
                                            (folder_id, folder_id),
                                        )
                                    cursor.execute(
                                        "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,updated_at) VALUES ('folder',%s,'complete',1,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='complete',updated_at=now()",
                                        (folder_id,),
                                    )
                                    pending.remove(row)
                                    progressed = True
                            except Exception as exc:
                                connection.rollback()
                                failures.append(
                                    {
                                        "sourceKind": "folder",
                                        "sourceId": str(folder_id),
                                        "reason": type(exc).__name__,
                                    }
                                )
                                cursor.execute(
                                    "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('folder',%s,'failed',1,%s,now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error=EXCLUDED.last_error,updated_at=now()",
                                    (folder_id, type(exc).__name__),
                                )
                                connection.commit()
                                pending.remove(row)
                        if not progressed:
                            failures.extend(
                                {
                                    "sourceKind": "folder",
                                    "sourceId": str(row[0]),
                                    "reason": "cycle_or_missing_parent",
                                }
                                for row in pending
                            )
                            for row in pending:
                                cursor.execute(
                                    "INSERT INTO ima.workspace_authorization_migration(source_kind,source_id,status,attempts,last_error,updated_at) VALUES ('folder',%s,'failed',1,'cycle_or_missing_parent',now()) ON CONFLICT(source_kind,source_id) DO UPDATE SET status='failed',last_error='cycle_or_missing_parent',updated_at=now()",
                                    (row[0],),
                                )
                            connection.commit()
                            break
                if action == "verify":
                    cursor.execute(
                        "SELECT source_kind,source_id FROM ima.workspace_authorization_migration WHERE status='failed' ORDER BY source_kind,source_id"
                    )
                    failures = [
                        {
                            "sourceKind": str(row[0]),
                            "sourceId": str(row[1]),
                            "reason": "checkpoint_failed",
                        }
                        for row in cursor.fetchall()
                    ]
                    source_folders = {
                        str(row[0]): (
                            str(row[1]),
                            str(row[2]) if row[2] is not None else None,
                            row[5],
                        )
                        for row in folders
                    }
                    for workspace_id, _name, _owner_id in workspaces:
                        cursor.execute(
                            "SELECT 1 FROM ima.workspaces WHERE id=%s AND is_active",
                            (workspace_id,),
                        )
                        if not cursor.fetchone():
                            failures.append(
                                {
                                    "sourceKind": "workspace",
                                    "sourceId": str(workspace_id),
                                    "reason": "missing_target_workspace",
                                }
                            )
                        cursor.execute(
                            "SELECT 1 FROM ima.folders WHERE id=%s AND workspace_id=%s AND is_root",
                            (workspace_id, workspace_id),
                        )
                        if not cursor.fetchone():
                            failures.append(
                                {
                                    "sourceKind": "folder",
                                    "sourceId": str(workspace_id),
                                    "reason": "missing_target_root",
                                }
                            )
                    for member_id, user_id, source_role in members:
                        try:
                            mapped = legacy_role(str(source_role)).value
                        except KeyError:
                            continue
                        cursor.execute(
                            "SELECT 1 FROM ima.workspace_members WHERE workspace_id=(SELECT \"workspaceId\" FROM public.member WHERE id=%s) AND user_id=%s AND role=%s AND state='active'",
                            (member_id, user_id, mapped),
                        )
                        if not cursor.fetchone():
                            failures.append(
                                {
                                    "sourceKind": "member",
                                    "sourceId": str(member_id),
                                    "reason": "member_equivalence",
                                }
                            )
                    for folder_id, (root_id, parent_id, conf) in source_folders.items():
                        cursor.execute(
                            "SELECT parent_id,acl_anchor_id FROM ima.folders WHERE id=%s AND workspace_id=%s",
                            (folder_id, root_id),
                        )
                        target_folder = cursor.fetchone()
                        if not target_folder:
                            failures.append(
                                {
                                    "sourceKind": "folder",
                                    "sourceId": folder_id,
                                    "reason": "folder_equivalence",
                                }
                            )
                            continue
                        if parent_id is not None and str(target_folder[0]) != parent_id:
                            failures.append(
                                {
                                    "sourceKind": "folder",
                                    "sourceId": folder_id,
                                    "reason": "parent_equivalence",
                                }
                            )
                        ancestors: list[str] = []
                        current_id: str | None = folder_id
                        seen: set[str] = set()
                        while current_id is not None:
                            if current_id in seen or current_id not in source_folders:
                                failures.append(
                                    {
                                        "sourceKind": "folder",
                                        "sourceId": folder_id,
                                        "reason": "source_cycle_or_missing_parent",
                                    }
                                )
                                break
                            seen.add(current_id)
                            ancestors.append(current_id)
                            current_id = source_folders[current_id][1]
                        else:
                            cursor.execute(
                                "SELECT ancestor_id,depth FROM ima.folder_closure WHERE workspace_id=%s AND descendant_id=%s ORDER BY depth",
                                (root_id, folder_id),
                            )
                            actual_closure = {
                                (str(row[0]), int(row[1])) for row in cursor.fetchall()
                            }
                            expected_closure = {
                                (ancestor, depth)
                                for depth, ancestor in enumerate(reversed(ancestors))
                            }
                            if actual_closure != expected_closure:
                                failures.append(
                                    {
                                        "sourceKind": "folder",
                                        "sourceId": folder_id,
                                        "reason": "closure_equivalence",
                                    }
                                )
                        acl_entries, acl_error = _parse_legacy_acl(conf)
                        if acl_error:
                            continue
                        cursor.execute(
                            "SELECT id FROM ima.folder_acls WHERE folder_id=%s", (folder_id,)
                        )
                        acl_row = cursor.fetchone()
                        if acl_entries is None:
                            if folder_id != root_id and acl_row:
                                failures.append(
                                    {
                                        "sourceKind": "acl",
                                        "sourceId": folder_id,
                                        "reason": "unexpected_independent_acl",
                                    }
                                )
                        elif acl_row:
                            cursor.execute(
                                "SELECT subject_type,subject_id,action FROM ima.folder_acl_entries WHERE acl_id=%s",
                                (acl_row[0],),
                            )
                            actual_acl = {
                                (str(row[0]), str(row[1]), str(row[2])) for row in cursor.fetchall()
                            }
                            if actual_acl != set(acl_entries):
                                failures.append(
                                    {
                                        "sourceKind": "acl",
                                        "sourceId": folder_id,
                                        "reason": "acl_equivalence",
                                    }
                                )
                        else:
                            failures.append(
                                {
                                    "sourceKind": "acl",
                                    "sourceId": folder_id,
                                    "reason": "missing_independent_acl",
                                }
                            )
                if failures:
                    raise SystemExit(f"legacy authorization verification failed: {failures}")
                print({**summary, "failures": 0})
                return
            print(summary)


def _parse_legacy_acl(conf: Any) -> tuple[list[tuple[str, str, str]] | None, str | None]:
    """Normalize legacy folder ACL JSON without accepting ambiguous records."""
    if conf is None:
        return None, None
    try:
        payload = json.loads(conf) if isinstance(conf, str) else conf
        acl = payload.get("acl") if isinstance(payload, dict) else None
        if not acl:
            return None, None
        if not isinstance(acl, dict):
            return None, "malformed_acl"
        if acl.get("inherit", True):
            return None, None
        aces = acl.get("aces", [])
        if not isinstance(aces, list):
            return None, "malformed_acl"
        action_map = {
            "view": ("view_metadata", "view_content"),
            "view_metadata": ("view_metadata",),
            "view_content": ("view_content",),
            "download": ("download", "view_metadata", "view_content"),
            "ask": ("ask", "view_content"),
            "edit": ("edit",),
            "move": ("move",),
            "delete": ("delete",),
            "manage": ("manage_acl",),
            "manage_acl": ("manage_acl",),
        }
        result: list[tuple[str, str, str]] = []
        for ace in aces:
            if not isinstance(ace, dict):
                return None, "malformed_acl_subject"
            principal_type = ace.get("principalType")
            principal_id = str(ace.get("principalId", ""))
            if principal_type == "role":
                try:
                    subject_id = legacy_role(principal_id).value
                except KeyError:
                    return None, "unknown_acl_role"
                subject_type = "role"
            elif principal_type == "user" and principal_id:
                subject_type, subject_id = "user", principal_id
            else:
                return None, "unknown_acl_subject"
            actions = ace.get("actions", [])
            if not isinstance(actions, list):
                return None, "malformed_acl_actions"
            expanded: set[str] = set()
            for old_action in actions:
                grants = action_map.get(str(old_action))
                if grants is None:
                    return None, "unknown_acl_action"
                expanded.update(grants)
            if "ask" in expanded and "view_content" not in expanded:
                return None, "ask_without_view_content"
            if "download" in expanded and not {"view_metadata", "view_content"}.issubset(expanded):
                return None, "download_without_view"
            result.extend((subject_type, subject_id, grant) for grant in sorted(expanded))
        return result, None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "malformed_acl"


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
