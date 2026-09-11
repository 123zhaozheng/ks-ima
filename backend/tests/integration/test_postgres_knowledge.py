"""Real PostgreSQL coverage for the versioned knowledge tree slice."""

# These tests deliberately use the project database image.  The service tests
# exercise transaction boundaries and PostgreSQL constraints rather than mocks.
# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ima.application.knowledge import KnowledgeError, KnowledgeService
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.tasks.service import JobService

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


def settings() -> Settings:
    assert DATABASE_URL
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="knowledge-integration-session",
        token_pepper="knowledge-integration-token",
        totp_encryption_key="knowledge-integration-totp-key",
        smtp_host=None,
        smtp_from=None,
    )


async def context(label: str) -> tuple[object, KnowledgeService, str, str, str, str]:
    """Create an isolated knowledge base and members, cleaning a prior run."""
    engine = create_engine(settings())
    digest = hashlib.sha256(label.encode()).hexdigest()[:16]
    actor = f"knowledge-{digest}-a"
    editor = f"knowledge-{digest}-e"
    viewer = f"knowledge-{digest}-v"
    stamp = datetime.now(UTC)
    kb_id = uuid4().hex
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """DELETE FROM ima.document_versions WHERE document_id IN
                (SELECT id FROM ima.documents WHERE kb_id IN
                 (SELECT id FROM ima.knowledge_bases WHERE created_by IN (:actor,:editor,:viewer)))"""
            ),
            {"actor": actor, "editor": editor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.knowledge_bases WHERE created_by IN (:actor,:editor,:viewer)"),
            {"actor": actor, "editor": editor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN (:actor,:editor,:viewer)"),
            {"actor": actor, "editor": editor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN (:actor,:editor,:viewer)"),
            {"actor": actor, "editor": editor, "viewer": viewer},
        )
        for user_id in (actor, editor, viewer):
            await conn.execute(
                text(
                    """INSERT INTO ima.users
                    (id,email,normalized_email,display_name,is_active,password_reset_required,
                     security_stamp,created_at,updated_at)
                    VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"""
                ),
                {"id": user_id, "email": f"{user_id}@example.test", "stamp": user_id, "now": stamp},
            )
        await conn.execute(
            text(
                """INSERT INTO ima.knowledge_bases(id,name,is_active,created_by,created_at,updated_at)
                VALUES (:kb,:name,true,:actor,:now,:now)"""
            ),
            {"kb": kb_id, "name": f"Knowledge {label}", "actor": actor, "now": stamp},
        )
        for user_id, role in ((actor, "owner"), (editor, "editor"), (viewer, "viewer")):
            await conn.execute(
                text(
                    """INSERT INTO ima.kb_members(kb_id,user_id,role,state,version,joined_at)
                    VALUES (:kb,:user,:role,'active',1,:now)"""
                ),
                {"kb": kb_id, "user": user_id, "role": role, "now": stamp},
            )
        await conn.execute(
            text(
                """INSERT INTO ima.folders
                (id,kb_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,
                 created_by,created_at,updated_at)
                VALUES (:kb,:kb,NULL,'Knowledge','knowledge',0,'active',1,true,:actor,:now,:now)"""
            ),
            {"kb": kb_id, "actor": actor, "now": stamp},
        )
        await conn.execute(
            text(
                """INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth)
                VALUES (:kb,:kb,:kb,0)"""
            ),
            {"kb": kb_id},
        )
    return (
        engine,
        KnowledgeService(engine, JobService(settings(), engine)),
        kb_id,
        actor,
        editor,
        viewer,
    )


async def close_context(engine: object, kb_id: str, actor: str, editor: str, viewer: str) -> None:
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text(
                "DELETE FROM ima.document_versions WHERE document_id IN (SELECT id FROM ima.documents WHERE kb_id=:kb)"
            ),
            {"kb": kb_id},
        )
        await conn.execute(text("DELETE FROM ima.knowledge_bases WHERE id=:kb"), {"kb": kb_id})
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN (:actor,:editor,:viewer)"),
            {"actor": actor, "editor": editor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN (:actor,:editor,:viewer)"),
            {"actor": actor, "editor": editor, "viewer": viewer},
        )
    await engine.dispose()  # type: ignore[attr-defined]


pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")


@pytest.mark.postgres
def test_knowledge_migration_is_fresh_and_repeatable() -> None:
    migrate()
    migrate()
    assert SYNC_URL
    with psycopg.connect(SYNC_URL) as connection:
        assert (
            connection.execute("SELECT version_num FROM ima.alembic_version").fetchone()[0]
            == "20260910_0013"
        )
        for table in (
            "documents",
            "document_versions",
            "knowledge_bases",
            "kb_members",
            "legacy_knowledge_migration",
        ):
            assert connection.execute("SELECT to_regclass(%s)", (f"ima.{table}",)).fetchone()[0]
        for removed in ("tags", "document_tags", "workspaces", "workspace_members"):
            assert (
                connection.execute("SELECT to_regclass(%s)", (f"ima.{removed}",)).fetchone()[0]
                is None
            )
        assert connection.execute(
            "SELECT 1 FROM pg_trigger WHERE tgname='trg_document_version_immutable'"
        ).fetchone()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_document_versions_are_immutable() -> None:
    engine, service, kb_id, actor, editor, viewer = await context("immutable")
    try:
        note = await service.create_note(actor, kb_id, "Immutable", "# first")
        with pytest.raises(DBAPIError, match="immutable"):
            async with engine.begin() as conn:  # type: ignore[attr-defined]
                await conn.execute(
                    text(
                        "UPDATE ima.document_versions SET markdown='rewritten' WHERE document_id=:id AND version=1"
                    ),
                    {"id": note["id"]},
                )
        async with engine.connect() as conn:  # type: ignore[attr-defined]
            assert (
                await conn.scalar(
                    text(
                        "SELECT markdown FROM ima.document_versions WHERE document_id=:id AND version=1"
                    ),
                    {"id": note["id"]},
                )
                == "# first"
            )
    finally:
        await close_context(engine, kb_id, actor, editor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_concurrent_note_edits_return_one_typed_conflict() -> None:
    engine, service, kb_id, actor, editor, viewer = await context("concurrent")
    try:
        note = await service.create_note(actor, kb_id, "Concurrent", "one")

        async def edit(markdown: str) -> object:
            try:
                return await service.patch_document(
                    actor,
                    UUID(str(note["id"])),
                    title=None,
                    markdown=markdown,
                    expected_version=1,
                    expected_content_version=1,
                )
            except Exception as exc:  # assert the exact typed result below
                return exc

        results = await asyncio.gather(edit("two"), edit("three"))
        assert sum(isinstance(result, dict) for result in results) == 1
        conflicts = [result for result in results if isinstance(result, KnowledgeError)]
        assert len(conflicts) == 1
        assert conflicts[0].code == "VERSION_CONFLICT"
        assert all(not isinstance(result, DBAPIError) for result in results)
    finally:
        await close_context(engine, kb_id, actor, editor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_101_siblings_have_stable_cursor_and_stale_listing_conflict() -> None:
    engine, service, kb_id, actor, editor, viewer = await context("pagination")
    try:
        now = datetime.now(UTC)
        async with engine.begin() as conn:  # type: ignore[attr-defined]
            for index in range(101):
                await conn.execute(
                    text(
                        """INSERT INTO ima.documents
                        (id,kb_id,folder_id,kind,title,normalized_title,order_key,
                         current_version,created_by,updated_by,created_at,updated_at)
                        VALUES (:id,:kb,:folder,'file',:title,:normalized,:order_key,
                                NULL,:actor,:actor,:now,:now)"""
                    ),
                    {
                        "id": uuid4(),
                        "kb": kb_id,
                        "folder": kb_id,
                        "title": f"Sibling {index:03}",
                        "normalized": f"sibling {index:03}",
                        "order_key": index,
                        "actor": actor,
                        "now": now,
                    },
                )
        folder_only = await service.list_contents(actor, kb_id, None, 100, kind="folder")
        assert folder_only["items"] == []
        file_only = await service.list_contents(actor, kb_id, None, 100, kind="file")
        assert len(file_only["items"]) == 100
        assert all(item["kind"] == "file" for item in file_only["items"])
        first = await service.list_contents(actor, kb_id, None, 100)
        assert len(first["items"]) == 100
        assert first["nextCursor"]
        second = await service.list_contents(actor, kb_id, first["nextCursor"], 100)
        assert len(second["items"]) == 1
        await service.create_note(actor, kb_id, "After page", "changed")
        with pytest.raises(KnowledgeError) as stale:
            await service.list_contents(actor, kb_id, first["nextCursor"], 100)
        assert stale.value.code == "LISTING_CHANGED"
    finally:
        await close_context(engine, kb_id, actor, editor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_member_role_is_the_single_authorization_vote() -> None:
    engine, service, kb_id, actor, editor, viewer = await context("membership")
    outsider = f"knowledge-outsider-{uuid4().hex[:8]}"
    try:
        note = await service.create_note(actor, kb_id, "Shared", "visible to members")
        document_id = UUID(str(note["id"]))
        # Viewer: read-only membership grants the whole tree, never writes.
        assert (await service.get_document(viewer, document_id))["kbId"] == kb_id
        assert (await service.list_contents(viewer, kb_id, None, 50))["items"]
        with pytest.raises(KnowledgeError) as viewer_write:
            await service.create_note(viewer, kb_id, "Viewer note", "denied")
        assert viewer_write.value.code == "KB_NOT_FOUND"
        with pytest.raises(KnowledgeError) as viewer_delete:
            await service.delete_document(viewer, document_id)
        assert viewer_delete.value.code == "KB_NOT_FOUND"
        # Editor: writes allowed through the same membership decision.
        created = await service.create_note(editor, kb_id, "Editor note", "allowed")
        assert created["kbId"] == kb_id
        # Non-member: every action is refused as not found.
        with pytest.raises(KnowledgeError) as outsider_read:
            await service.get_document(outsider, document_id)
        assert outsider_read.value.code == "KB_NOT_FOUND"
        with pytest.raises(KnowledgeError) as outsider_list:
            await service.list_contents(outsider, kb_id, None, 50)
        assert outsider_list.value.code == "KB_NOT_FOUND"
    finally:
        await close_context(engine, kb_id, actor, editor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_delete_document_is_immediate_and_physical() -> None:
    engine, service, kb_id, actor, editor, viewer = await context("delete")
    try:
        note = await service.create_note(actor, kb_id, "Deleted", "gone")
        document_id = UUID(str(note["id"]))
        await service.delete_document(actor, document_id)
        async with engine.connect() as conn:  # type: ignore[attr-defined]
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.documents WHERE id=:id"),
                    {"id": document_id},
                )
                == 0
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.document_versions WHERE document_id=:id"),
                    {"id": document_id},
                )
                == 0
            )
        with pytest.raises(KnowledgeError) as gone:
            await service.delete_document(actor, document_id)
        assert gone.value.code == "DOCUMENT_NOT_FOUND"
    finally:
        await close_context(engine, kb_id, actor, editor, viewer)


@pytest.mark.postgres
def test_legacy_knowledge_checkpoint_table_is_repeatable() -> None:
    migrate()
    assert SYNC_URL
    source_id = f"knowledge-checkpoint-{uuid4().hex[:12]}"
    with psycopg.connect(SYNC_URL) as connection:
        try:
            with pytest.raises(RuntimeError):
                with connection.transaction():
                    connection.execute(
                        "INSERT INTO ima.legacy_knowledge_migration(source_kind,source_id,source_fingerprint,status,attempts,updated_at) VALUES ('entity',%s,'fp-1','running',1,now())",
                        (source_id,),
                    )
                    raise RuntimeError("simulated interruption")
            assert (
                connection.execute(
                    "SELECT 1 FROM ima.legacy_knowledge_migration WHERE source_id=%s", (source_id,)
                ).fetchone()
                is None
            )
            connection.execute(
                "INSERT INTO ima.legacy_knowledge_migration(source_kind,source_id,source_fingerprint,status,attempts,last_error,updated_at) VALUES ('entity',%s,'fp-1','failed',1,'source_changed',now())",
                (source_id,),
            )
            connection.execute(
                "UPDATE ima.legacy_knowledge_migration SET status='running',attempts=attempts+1,last_error=NULL WHERE source_kind='entity' AND source_id=%s",
                (source_id,),
            )
            connection.execute(
                "UPDATE ima.legacy_knowledge_migration SET status='complete',processed_at=now(),updated_at=now() WHERE source_kind='entity' AND source_id=%s",
                (source_id,),
            )
            row = connection.execute(
                "SELECT status,attempts,source_fingerprint FROM ima.legacy_knowledge_migration WHERE source_id=%s",
                (source_id,),
            ).fetchone()
            assert row == ("complete", 2, "fp-1")
            connection.execute(
                "INSERT INTO ima.legacy_knowledge_migration(source_kind,source_id,source_fingerprint,status,attempts,updated_at) VALUES ('entity',%s,'fp-1','running',1,now()) ON CONFLICT(source_kind,source_id) DO NOTHING",
                (source_id,),
            )
            assert (
                connection.execute(
                    "SELECT attempts FROM ima.legacy_knowledge_migration WHERE source_id=%s",
                    (source_id,),
                ).fetchone()[0]
                == 2
            )
        finally:
            connection.execute(
                "DELETE FROM ima.legacy_knowledge_migration WHERE source_kind='entity' AND source_id=%s",
                (source_id,),
            )
