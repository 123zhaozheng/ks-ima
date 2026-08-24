from pathlib import Path


def test_identity_schema_preserves_opaque_legacy_ids() -> None:
    migration = (
        Path(__file__).parents[2] / "migrations" / "versions" / "20260824_0002_identity_platform.py"
    )
    source = migration.read_text(encoding="utf-8")
    assert "id varchar(32) PRIMARY KEY" in source
    assert "user_id varchar(32)" in source
    assert "workspace_id uuid" not in source
    assert "CREATE TABLE IF NOT EXISTS ima.users" in source
