"""Real migration smoke, enabled in CI/deployment with IMA_TEST_DATABASE_URL."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_DATABASE_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None
)
ALEMBIC_DATABASE_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") if DATABASE_URL else None
)

# Terminal inventory: every legacy public table must be gone after the final
# cleanup migration (20260829_0011_legacy_schema_removal).
LEGACY_PUBLIC_TABLES = (
    "account",
    "assistant",
    "blob",
    "channel",
    "chat",
    "connector",
    "entity",
    "entityAccess",
    "entityPermission",
    "globalSettings",
    "item",
    "mcpPlugin",
    "member",
    "mergePatchesRule",
    "message",
    "messageEntity",
    "model",
    "order",
    "page",
    "pagePatch",
    "plan",
    "planPrice",
    "provider",
    "search",
    "searchRecord",
    "session",
    "shortcut",
    "toolCall",
    "translation",
    "translationRecord",
    "two_factor",
    "usage",
    "user",
    "userData",
    "verification",
    "workspace",
    "workspaceInvitation",
)


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_migration_drops_legacy_public_tables_and_requires_extensions() -> None:
    assert DATABASE_URL is not None
    assert SYNC_DATABASE_URL is not None
    assert ALEMBIC_DATABASE_URL is not None
    env = {**os.environ, "IMA_DATABASE_URL": ALEMBIC_DATABASE_URL}
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env=env,
        check=True,
    )
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env=env,
        check=True,
    )
    with psycopg.connect(SYNC_DATABASE_URL) as connection:
        remaining = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
        assert remaining.isdisjoint(LEGACY_PUBLIC_TABLES)
        assert connection.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'ima'").fetchone()
        assert connection.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname = 'ima_jobs'"
        ).fetchone()
        extensions = {
            row[0]
            for row in connection.execute(
                "SELECT extname FROM pg_extension WHERE extname IN ('vector', 'zhparser')"
            )
        }
        assert extensions == {"vector", "zhparser"}
        legacy_functions = {
            row[0]
            for row in connection.execute(
                "SELECT proname FROM pg_proc WHERE proname IN "
                "('kb_acl_granted','kb_acl_can','kb_nearest_acl_break',"
                "'kb_rebuild_one_entity_permissions','kb_rebuild_workspace_permissions',"
                "'kb_entity_permission_trigger','kb_member_permission_trigger',"
                "'update_storage_and_refcount')"
            )
        }
        assert legacy_functions == set()
