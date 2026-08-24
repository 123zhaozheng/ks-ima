from pathlib import Path


def test_initial_migration_isolated_from_legacy_public_schema() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations/versions/20260824_0001_foundation.py"
    ).read_text()
    assert "CREATE SCHEMA IF NOT EXISTS ima" in migration
    assert "CREATE SCHEMA IF NOT EXISTS ima_jobs" in migration
    assert "public." not in migration
    assert "DROP SCHEMA IF EXISTS public" not in migration
