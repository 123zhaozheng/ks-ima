"""Real PostgreSQL authorization checks for the in-process Ask tools."""

from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from ima.application.ask_tools import AskToolError, AskToolExecutor
from ima.application.search import SearchService

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


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
async def test_ask_tools_cannot_cross_knowledge_base_boundaries() -> None:
    """User A cannot read user B's folder, document, or chunk by changing arguments."""
    migrate()
    assert SYNC_URL and DATABASE_URL
    suffix = uuid4().hex[:20]
    actor_a = f"it-a-{suffix}"
    actor_b = f"it-b-{suffix}"
    kb_a = f"it-kba-{suffix}"
    kb_b = f"it-kbb-{suffix}"
    folder_a = f"it-fa-{suffix}"
    folder_b = f"it-fb-{suffix}"
    document_a, document_b = uuid4(), uuid4()
    now = datetime.now(UTC)
    secret_a = "KB A private policy"
    secret_b = "KB B private policy"

    with psycopg.connect(SYNC_URL) as connection:
        for user_id, label in ((actor_a, "A"), (actor_b, "B")):
            connection.execute(
                """INSERT INTO ima.users
                (id,email,normalized_email,display_name,security_stamp,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (
                    user_id,
                    f"{user_id}@ask-tools.test",
                    f"{user_id}@ask-tools.test",
                    f"Ask user {label}",
                    f"stamp-{suffix}-{label}",
                    now,
                    now,
                ),
            )
        for kb_id, name, owner in ((kb_a, "KB A", actor_a), (kb_b, "KB B", actor_b)):
            connection.execute(
                """INSERT INTO ima.knowledge_bases
                (id,name,created_by,created_at,updated_at) VALUES (%s,%s,%s,%s,%s)""",
                (kb_id, name, owner, now, now),
            )
            connection.execute(
                """INSERT INTO ima.folders
                (id,kb_id,parent_id,name,normalized_name,is_root,created_by,created_at,updated_at)
                VALUES (%s,%s,NULL,%s,%s,true,%s,%s,%s)""",
                (kb_id, kb_id, name, name.casefold(), owner, now, now),
            )
        for kb_id, folder_id, name, owner in (
            (kb_a, folder_a, "A folder", actor_a),
            (kb_b, folder_b, "B folder", actor_b),
        ):
            connection.execute(
                """INSERT INTO ima.folders
                (id,kb_id,parent_id,name,normalized_name,created_by,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (folder_id, kb_id, kb_id, name, name.casefold(), owner, now, now),
            )
            connection.execute(
                """INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth)
                VALUES (%s,%s,%s,0),(%s,%s,%s,1)""",
                (kb_id, kb_id, kb_id, kb_id, kb_id, folder_id),
            )
        for kb_id, owner in ((kb_a, actor_a), (kb_b, actor_b)):
            connection.execute(
                """INSERT INTO ima.kb_members(kb_id,user_id,role,state,joined_at)
                VALUES (%s,%s,'owner','active',%s)""",
                (kb_id, owner, now),
            )
        for document_id, kb_id, folder_id, owner, title, content in (
            (document_a, kb_a, folder_a, actor_a, "A policy", secret_a),
            (document_b, kb_b, folder_b, actor_b, "B policy", secret_b),
        ):
            digest = _digest(content)
            connection.execute(
                """INSERT INTO ima.documents
                (id,kb_id,folder_id,kind,title,normalized_title,lifecycle,current_version,
                 file_state,created_by,updated_by,created_at,updated_at)
                VALUES (%s,%s,%s,'file',%s,%s,'active',1,'ready',%s,%s,%s,%s)""",
                (document_id, kb_id, folder_id, title, title.casefold(), owner, owner, now, now),
            )
            connection.execute(
                """INSERT INTO ima.document_versions
                (document_id,version,kind,markdown,digest,created_by,created_at)
                VALUES (%s,1,'file',NULL,%s,%s,%s)""",
                (document_id, digest, owner, now),
            )
            connection.execute(
                """INSERT INTO ima.document_file_versions
                (document_id,version,kb_id,generation,object_state,object_key,checksum,
                 size_bytes,mime_type,original_filename,created_by,created_at,verified_at)
                VALUES (%s,1,%s,1,'verified',%s,%s,1,'text/plain',%s,%s,%s,%s)""",
                (document_id, kb_id, f"{kb_id}/document", digest, title, owner, now, now),
            )
            connection.execute(
                """INSERT INTO ima.document_derived_text
                (document_id,version,generation,parser_name,parser_version,source_checksum,
                 text_digest,text_content,status,created_at)
                VALUES (%s,1,1,'test','1',%s,%s,%s,'ready',%s)""",
                (document_id, digest, digest, content, now),
            )
            connection.execute(
                """INSERT INTO ima.document_chunks
                (document_id,version,generation,ordinal,text_content,content_digest,kb_id,created_at,updated_at)
                VALUES (%s,1,1,0,%s,%s,%s,%s,%s)""",
                (document_id, content, digest, kb_id, now, now),
            )
        connection.commit()

    engine = create_async_engine(DATABASE_URL)
    search = SearchService(engine, SimpleNamespace())

    async def profile(*_: object, **__: object) -> object:
        return SimpleNamespace(
            retrieval_mode="keyword",
            top_k=8,
            score_threshold=0.0,
            vector_weight=0.5,
            rerank_model_id=None,
        )

    search._profile = profile  # type: ignore[method-assign]
    executor = AskToolExecutor(search)
    try:
        with pytest.raises(AskToolError) as search_error:
            await executor.execute(
                "search_knowledge",
                {"query": "private", "documentId": str(document_b)},
                actor=actor_a,
                kb_id=kb_a,
                scope=None,
            )
        assert search_error.value.code == "DOCUMENT_NOT_FOUND"
        assert secret_b not in str(search_error.value)

        with pytest.raises(AskToolError) as folder_error:
            await executor.execute(
                "list_dir",
                {"folderId": folder_b},
                actor=actor_a,
                kb_id=kb_a,
                scope=None,
            )
        assert folder_error.value.code == "FOLDER_NOT_FOUND"

        with pytest.raises(AskToolError) as document_error:
            await executor.execute(
                "get_document_outline",
                {"documentId": str(document_b)},
                actor=actor_a,
                kb_id=kb_a,
                scope=None,
            )
        assert document_error.value.code == "DOCUMENT_NOT_FOUND"
    finally:
        await engine.dispose()
        with psycopg.connect(SYNC_URL) as connection:
            connection.execute(
                "DELETE FROM ima.document_chunks WHERE document_id IN (%s,%s)",
                (document_a, document_b),
            )
            connection.execute(
                "DELETE FROM ima.document_derived_text WHERE document_id IN (%s,%s)",
                (document_a, document_b),
            )
            connection.execute(
                "DELETE FROM ima.document_file_versions WHERE document_id IN (%s,%s)",
                (document_a, document_b),
            )
            connection.execute(
                "DELETE FROM ima.document_versions WHERE document_id IN (%s,%s)",
                (document_a, document_b),
            )
            connection.execute(
                "DELETE FROM ima.documents WHERE id IN (%s,%s)", (document_a, document_b)
            )
            connection.execute(
                "DELETE FROM ima.folder_closure WHERE kb_id IN (%s,%s)", (kb_a, kb_b)
            )
            connection.execute("DELETE FROM ima.folders WHERE kb_id IN (%s,%s)", (kb_a, kb_b))
            connection.execute("DELETE FROM ima.kb_members WHERE kb_id IN (%s,%s)", (kb_a, kb_b))
            connection.execute("DELETE FROM ima.knowledge_bases WHERE id IN (%s,%s)", (kb_a, kb_b))
            connection.execute("DELETE FROM ima.users WHERE id IN (%s,%s)", (actor_a, actor_b))
            connection.commit()
