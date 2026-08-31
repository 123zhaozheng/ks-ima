import os
import subprocess
from pathlib import Path

import psycopg
import pytest

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")
SYNC_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://") if DATABASE_URL else None
ALEMBIC_URL = (
    DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://") if DATABASE_URL else None
)


def migrate() -> None:
    assert ALEMBIC_URL
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).parents[2],
        env={**os.environ, "IMA_DATABASE_URL": ALEMBIC_URL},
        check=True,
    )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
def test_search_migration_installs_real_fts_and_exact_chunk_citation_dependency() -> None:
    migrate()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        assert connection.execute(
            "SELECT attgenerated FROM pg_attribute WHERE attrelid='ima.document_chunks'::regclass "
            "AND attname='search_vector'"
        ).fetchone() == ("s",)
        assert (
            connection.execute(
                "SELECT indexdef FROM pg_indexes WHERE schemaname='ima' "
                "AND indexname='ix_document_chunks_search'"
            )
            .fetchone()[0]
            .endswith("USING gin (search_vector)")
        )
        assert connection.execute(
            "SELECT attnotnull FROM pg_attribute WHERE attrelid='ima.document_chunks'::regclass "
            "AND attname='kb_id'"
        ).fetchone() == (True,)
        chunk_kb_fk = (
            "FOREIGN KEY (kb_id, document_id) REFERENCES "
            "ima.documents(kb_id, id) ON DELETE RESTRICT"
        )
        assert (
            connection.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='ima.document_chunks'::regclass "
                "AND conname='fk_document_chunks_kb_document'"
            ).fetchone()[0]
            == chunk_kb_fk
        )
        conversation_owner_fk = (
            "FOREIGN KEY (kb_id, owner_user_id) REFERENCES "
            "ima.kb_members(kb_id, user_id) ON DELETE RESTRICT"
        )
        assert (
            connection.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='ima.conversations'::regclass "
                "AND contype='f' AND pg_get_constraintdef(oid) LIKE '%kb_members%'"
            ).fetchone()[0]
            == conversation_owner_fk
        )
        trigger = connection.execute(
            "SELECT tgname FROM pg_trigger WHERE "
            "tgrelid='ima.message_citations'::regclass "
            "AND tgname='trg_message_citation_immutable'"
        ).fetchone()
        assert trigger == ("trg_message_citation_immutable",)
        constraints = {
            row[0]
            for row in connection.execute(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid='ima.message_citations'::regclass"
            )
        }
        assert any(
            "document_versions" in constraint and "ON DELETE RESTRICT" in constraint
            for constraint in constraints
        )
        assert any(
            "document_chunks" in constraint
            and "content_digest" in constraint
            and "ON DELETE RESTRICT" in constraint
            for constraint in constraints
        )
