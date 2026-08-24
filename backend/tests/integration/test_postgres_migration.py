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


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_migration_keeps_legacy_public_tables_and_requires_extensions() -> None:
    assert DATABASE_URL is not None
    assert SYNC_DATABASE_URL is not None
    assert ALEMBIC_DATABASE_URL is not None
    with psycopg.connect(SYNC_DATABASE_URL) as connection:
        before = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
    env = {**os.environ, "IMA_DATABASE_URL": ALEMBIC_DATABASE_URL}
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env=env,
        check=True,
    )
    with psycopg.connect(SYNC_DATABASE_URL) as connection:
        after = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        ).fetchall()
        assert before == after
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
