"""Real PostgreSQL coverage for the retained maintenance write-freeze tool.

The freeze is a generic operations mechanism that guards Python knowledge
mutations while migration-tagged writers (direct ``ima`` CLI SQL) bypass it.
The retired Bun bridges and legacy importer rehearsals no longer exist.
"""

# ruff: noqa: E501,ASYNC221

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import text

from ima.application.authorization import WorkspaceService
from ima.application.knowledge import KnowledgeService
from ima.application.maintenance import (
    MAINTENANCE_WRITE_FREEZE,
    MaintenanceFreezeError,
    MaintenanceService,
)
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None

requires_database = pytest.mark.skipif(
    not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured"
)


def freeze_settings() -> Settings:
    assert DATABASE_URL
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="freeze-integration-session",
        token_pepper="freeze-integration-token",
        totp_encryption_key="freeze-integration-totp-key",
        smtp_host=None,
        smtp_from=None,
        storage_endpoint="https://storage.freeze-rehearsal.test",
        storage_bucket="freeze-rehearsal",
        storage_access_key_id="freeze-rehearsal-access",
        storage_secret_access_key="freeze-rehearsal-secret",
    )


def seed_user(connection: Any, user_id: str, *, super_admin: bool = False) -> None:
    stamp = datetime.now(UTC)
    connection.execute(
        """INSERT INTO ima.users
        (id,email,normalized_email,display_name,is_active,password_reset_required,
         security_stamp,created_at,updated_at)
        VALUES (%s,%s,%s,%s,true,false,%s,%s,%s)
        ON CONFLICT (id) DO UPDATE SET is_active=true,disabled_at=NULL""",
        (user_id, f"{user_id}@example.test", user_id, user_id, user_id, stamp, stamp),
    )
    if super_admin:
        connection.execute(
            "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) "
            "VALUES (%s,'super_admin',%s) ON CONFLICT DO NOTHING",
            (user_id, stamp),
        )


async def create_workspace_context(label: str) -> tuple[Any, str, str]:
    """Create engine + disposable workspace; returns (engine, workspace_id, actor)."""
    engine = create_engine(freeze_settings())
    workspace_service = WorkspaceService(engine, freeze_settings())
    digest = hashlib.sha256(label.encode()).hexdigest()[:16]
    actor = f"freeze-{digest}-actor"
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """DELETE FROM ima.document_tags WHERE document_id IN
                (SELECT id FROM ima.documents WHERE workspace_id IN
                 (SELECT id FROM ima.workspaces WHERE created_by=:actor))"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.document_versions WHERE document_id IN
                (SELECT id FROM ima.documents WHERE workspace_id IN
                 (SELECT id FROM ima.workspaces WHERE created_by=:actor))"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.documents WHERE workspace_id IN
                (SELECT id FROM ima.workspaces WHERE created_by=:actor)"""
            ),
            {"actor": actor},
        )
        await conn.execute(
            text("DELETE FROM ima.workspaces WHERE created_by=:actor"), {"actor": actor}
        )
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id=:actor"), {"actor": actor}
        )
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id=:actor"),
            {"actor": actor},
        )
        await conn.execute(text("DELETE FROM ima.users WHERE id=:actor"), {"actor": actor})
        stamp = datetime.now(UTC)
        await conn.execute(
            text(
                """INSERT INTO ima.users
                (id,email,normalized_email,display_name,is_active,password_reset_required,
                 security_stamp,created_at,updated_at)
                VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"""
            ),
            {"id": actor, "email": f"{actor}@example.test", "stamp": actor, "now": stamp},
        )
        await conn.execute(
            text(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) "
                "VALUES (:id,'platform_admin',:now)"
            ),
            {"id": actor, "now": stamp},
        )
    workspace = await workspace_service.create_workspace(actor, f"Freeze {label}", actor)
    return engine, str(workspace["id"]), actor


def cleanup_workspace(connection: Any, workspace_id: str, actor_ids: tuple[str, ...]) -> None:
    connection.execute(
        "UPDATE ima.system_settings SET maintenance_write_freeze=false,"
        "maintenance_freeze_reason=NULL,maintenance_freeze_entered_at=NULL,"
        "maintenance_freeze_entered_by=NULL,updated_by=NULL"
    )
    connection.execute(
        "DELETE FROM ima.document_tags WHERE document_id IN "
        "(SELECT id FROM ima.documents WHERE workspace_id=%s)",
        (workspace_id,),
    )
    connection.execute(
        "DELETE FROM ima.document_versions WHERE document_id IN "
        "(SELECT id FROM ima.documents WHERE workspace_id=%s)",
        (workspace_id,),
    )
    connection.execute("DELETE FROM ima.documents WHERE workspace_id=%s", (workspace_id,))
    connection.execute("DELETE FROM ima.workspaces WHERE id=%s", (workspace_id,))
    for actor_id in actor_ids:
        connection.execute("DELETE FROM ima.audit_events WHERE actor_id=%s", (actor_id,))
        connection.execute(
            "DELETE FROM ima.platform_role_assignments WHERE user_id=%s", (actor_id,)
        )
        connection.execute("DELETE FROM ima.users WHERE id=%s", (actor_id,))


@pytest.mark.postgres
@requires_database
async def test_freeze_guard_blocks_python_mutations_but_not_direct_writers() -> None:
    assert SYNC_URL
    engine, workspace_id, actor = await create_workspace_context("guard")
    digest = uuid4().hex[:12]
    admin = f"freeze-{digest}-admin"
    service = MaintenanceService(engine)
    knowledge = KnowledgeService(engine, WorkspaceService(engine, freeze_settings()))
    try:
        with psycopg.connect(SYNC_URL) as connection:
            seed_user(connection, admin, super_admin=True)

        # Only active super-admins may operate the freeze.
        with pytest.raises(PermissionError):
            await service.enter_freeze(actor, "not authorized")

        entered = await service.enter_freeze(admin, f"freeze rehearsal {digest}")
        assert entered["frozen"] is True
        assert entered["enteredBy"] == admin
        assert entered["reason"] == f"freeze rehearsal {digest}"
        assert entered["secretValues"] is False

        # Python knowledge mutations are refused with the typed RFC 9457 problem.
        with pytest.raises(MaintenanceFreezeError) as refusal:
            await knowledge.create_note(actor, workspace_id, f"Frozen {digest}", "text")
        assert refusal.value.status_code == 503
        assert refusal.value.code == MAINTENANCE_WRITE_FREEZE

        # Migration-tagged writers issue direct SQL and bypass the guard by design.
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "INSERT INTO ima.audit_events(actor_id,action,target_type,target_id,result,metadata,created_at) "
                "VALUES (%s,'freeze.direct_writer','migration','all','success','{}'::jsonb,now())",
                (admin,),
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM ima.audit_events WHERE actor_id=%s AND action='freeze.direct_writer'",
                    (admin,),
                ).fetchone()[0]
                == 1
            )

        status = await service.freeze_status()
        assert status["frozen"] is True

        exited = await service.exit_freeze(admin)
        assert exited["frozen"] is False
        assert exited["enteredBy"] is None

        # Mutations succeed again after the freeze exits.
        note = await knowledge.create_note(actor, workspace_id, f"After freeze {digest}", "text")
        assert note["id"] is not None
        with psycopg.connect(SYNC_URL) as connection:
            actions = {
                row[0]
                for row in connection.execute(
                    "SELECT action FROM ima.audit_events WHERE actor_id=%s", (admin,)
                ).fetchall()
            }
            assert actions == {
                "maintenance.freeze.enter",
                "maintenance.freeze.exit",
                "freeze.direct_writer",
            }
            metadata = json.loads(
                connection.execute(
                    "SELECT metadata::text FROM ima.audit_events "
                    "WHERE actor_id=%s AND action='maintenance.freeze.enter'",
                    (admin,),
                ).fetchone()[0]
            )
            assert metadata == {"reason": f"freeze rehearsal {digest}", "secretValues": False}
    finally:
        with psycopg.connect(SYNC_URL) as connection:
            cleanup_workspace(connection, workspace_id, (actor, admin))
        await engine.dispose()
