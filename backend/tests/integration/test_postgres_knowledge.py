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

from ima.application.authorization import WorkspaceService
from ima.application.knowledge import KnowledgeError, KnowledgeService
from ima.config import Settings
from ima.domain.authorization import AclAction
from ima.infrastructure.db.engine import create_engine

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


async def context(label: str) -> tuple[object, KnowledgeService, str, str, str]:
    """Create an isolated workspace and users, cleaning a prior interrupted run."""
    engine = create_engine(settings())
    workspace_service = WorkspaceService(engine, settings())
    digest = hashlib.sha256(label.encode()).hexdigest()[:16]
    actor = f"knowledge-{digest}-a"
    viewer = f"knowledge-{digest}-v"
    stamp = datetime.now(UTC)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """DELETE FROM ima.document_tags WHERE document_id IN
                (SELECT id FROM ima.documents WHERE workspace_id IN
                 (SELECT id FROM ima.workspaces WHERE created_by IN (:actor,:viewer)))"""
            ),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.document_versions WHERE document_id IN
                (SELECT id FROM ima.documents WHERE workspace_id IN
                 (SELECT id FROM ima.workspaces WHERE created_by IN (:actor,:viewer)))"""
            ),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text(
                """DELETE FROM ima.documents WHERE workspace_id IN
                (SELECT id FROM ima.workspaces WHERE created_by IN (:actor,:viewer))"""
            ),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.workspaces WHERE created_by IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
        )
        for user_id, email in (
            (actor, f"{actor}@example.test"),
            (viewer, f"{viewer}@example.test"),
        ):
            await conn.execute(
                text(
                    """INSERT INTO ima.users
                    (id,email,normalized_email,display_name,is_active,password_reset_required,
                     security_stamp,created_at,updated_at)
                    VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"""
                ),
                {"id": user_id, "email": email, "stamp": user_id, "now": stamp},
            )
        await conn.execute(
            text(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (:id,'platform_admin',:now)"
            ),
            {"id": actor, "now": stamp},
        )
    workspace = await workspace_service.create_workspace(actor, f"Knowledge {label}", actor)
    workspace_id = str(workspace["id"])
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """INSERT INTO ima.workspace_members
                (workspace_id,user_id,role,state,joined_at,updated_at)
                VALUES (:workspace,:viewer,'viewer','active',:now,:now)"""
            ),
            {"workspace": workspace_id, "viewer": viewer, "now": stamp},
        )
    return engine, KnowledgeService(engine, workspace_service), workspace_id, actor, viewer


async def close_context(engine: object, workspace_id: str, actor: str, viewer: str) -> None:
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text(
                "DELETE FROM ima.document_tags WHERE document_id IN (SELECT id FROM ima.documents WHERE workspace_id=:id)"
            ),
            {"id": workspace_id},
        )
        await conn.execute(
            text(
                "DELETE FROM ima.document_versions WHERE document_id IN (SELECT id FROM ima.documents WHERE workspace_id=:id)"
            ),
            {"id": workspace_id},
        )
        await conn.execute(
            text("DELETE FROM ima.documents WHERE workspace_id=:id"), {"id": workspace_id}
        )
        await conn.execute(text("DELETE FROM ima.workspaces WHERE id=:id"), {"id": workspace_id})
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
        )
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN (:actor,:viewer)"),
            {"actor": actor, "viewer": viewer},
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
            == "20260829_0011"
        )
        for table in (
            "documents",
            "document_versions",
            "tags",
            "document_tags",
            "legacy_knowledge_migration",
        ):
            assert connection.execute("SELECT to_regclass(%s)", (f"ima.{table}",)).fetchone()[0]
        assert connection.execute(
            "SELECT 1 FROM pg_trigger WHERE tgname='trg_document_version_immutable'"
        ).fetchone()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_document_versions_are_immutable() -> None:
    engine, service, workspace_id, actor, viewer = await context("immutable")
    try:
        note = await service.create_note(actor, workspace_id, "Immutable", "# first")
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
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_concurrent_note_edits_return_one_typed_conflict() -> None:
    engine, service, workspace_id, actor, viewer = await context("concurrent")
    try:
        note = await service.create_note(actor, workspace_id, "Concurrent", "one")

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
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_101_siblings_have_stable_cursor_and_stale_listing_conflict() -> None:
    engine, service, workspace_id, actor, viewer = await context("pagination")
    try:
        now = datetime.now(UTC)
        async with engine.begin() as conn:  # type: ignore[attr-defined]
            for index in range(101):
                await conn.execute(
                    text(
                        """INSERT INTO ima.documents
                        (id,workspace_id,folder_id,kind,title,normalized_title,order_key,
                         current_version,created_by,updated_by,created_at,updated_at)
                        VALUES (:id,:workspace,:folder,'file',:title,:normalized,:order_key,
                                NULL,:actor,:actor,:now,:now)"""
                    ),
                    {
                        "id": uuid4(),
                        "workspace": workspace_id,
                        "folder": workspace_id,
                        "title": f"Sibling {index:03}",
                        "normalized": f"sibling {index:03}",
                        "order_key": index,
                        "actor": actor,
                        "now": now,
                    },
                )
        folder_only = await service.list_contents(actor, workspace_id, None, 100, kind="folder")
        assert folder_only["items"] == []
        file_only = await service.list_contents(actor, workspace_id, None, 100, kind="file")
        assert len(file_only["items"]) == 100
        assert all(item["kind"] == "file" for item in file_only["items"])
        first = await service.list_contents(actor, workspace_id, None, 100)
        assert len(first["items"]) == 100
        assert first["nextCursor"]
        second = await service.list_contents(actor, workspace_id, first["nextCursor"], 100)
        assert len(second["items"]) == 1
        await service.create_note(actor, workspace_id, "After page", "changed")
        with pytest.raises(KnowledgeError) as stale:
            await service.list_contents(actor, workspace_id, first["nextCursor"], 100)
        assert stale.value.code == "LISTING_CHANGED"
    finally:
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_acl_hides_document_tag_and_trash_metadata() -> None:
    engine, service, workspace_id, actor, viewer = await context("privacy")
    try:
        private = await WorkspaceService(engine, settings()).create_folder(
            actor, workspace_id, workspace_id, "Private"
        )
        entries = [
            {"subject_type": "role", "subject_id": "workspace_admin", "action": action.value}
            for action in AclAction
        ]
        await WorkspaceService(engine, settings()).set_acl(
            actor, workspace_id, private["id"], inherit=False, entries=entries
        )
        note = await service.create_note(actor, private["id"], "Hidden note", "secret")
        tag = await service.create_tag(actor, workspace_id, "Restricted")
        await service.assign_tags(
            actor, UUID(str(note["id"])), (UUID(str(tag["id"])),), int(note["version"])
        )
        await service.trash_document(actor, UUID(str(note["id"])), int(note["version"]) + 1)
        with pytest.raises(KnowledgeError) as hidden:
            await service.get_document(viewer, UUID(str(note["id"])))
        assert hidden.value.code == "DOCUMENT_NOT_FOUND"
        assert all(
            item["id"] != tag["id"] for item in await service.list_tags(viewer, workspace_id)
        )
        assert all(
            item["id"] != str(note["id"])
            for item in (await service.list_trash(viewer, workspace_id, None, 50))["items"]
        )
    finally:
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_unicode_tags_normalize_assign_and_enforce_role() -> None:
    engine, service, workspace_id, actor, viewer = await context("tags")
    try:
        note = await service.create_note(actor, workspace_id, "Tagged", "text")
        tag = await service.create_tag(actor, workspace_id, "  Café  ")
        with pytest.raises(KnowledgeError) as duplicate:
            await service.create_tag(actor, workspace_id, "CAFE\u0301")
        assert duplicate.value.code == "NAME_CONFLICT"
        await service.assign_tags(
            actor, UUID(str(note["id"])), (UUID(str(tag["id"])),), int(note["version"])
        )
        listed = await service.list_tags(viewer, workspace_id)
        assert [(item["name"], item["count"]) for item in listed] == [("Café", 1)]
        with pytest.raises(KnowledgeError) as forbidden:
            await service.create_tag(viewer, workspace_id, "viewer-owned")
        assert forbidden.value.code == "TAG_FORBIDDEN"
    finally:
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_tag_merge_and_delete_are_versioned_and_dependency_safe() -> None:
    engine, service, workspace_id, actor, viewer = await context("tag-lifecycle")
    try:
        note = await service.create_note(actor, workspace_id, "Merge target", "text")
        source = await service.create_tag(actor, workspace_id, "Source")
        target = await service.create_tag(actor, workspace_id, "Target")
        await service.assign_tags(
            actor, UUID(str(note["id"])), (UUID(str(source["id"])),), int(note["version"])
        )
        with pytest.raises(KnowledgeError) as dependent:
            await service.delete_tag(actor, workspace_id, UUID(str(source["id"])), 1)
        assert dependent.value.code == "DEPENDENCY_EXISTS"
        await service.merge_tag(
            actor,
            workspace_id,
            UUID(str(source["id"])),
            UUID(str(target["id"])),
            1,
            1,
        )
        async with engine.connect() as conn:  # type: ignore[attr-defined]
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.document_tags WHERE document_id=:document AND tag_id=:tag"
                    ),
                    {"document": note["id"], "tag": target["id"]},
                )
                == 1
            )
        with pytest.raises(KnowledgeError) as hidden_source:
            await service.delete_tag(actor, workspace_id, UUID(str(source["id"])), 2)
        assert hidden_source.value.code == "TAG_NOT_FOUND"
        with pytest.raises(KnowledgeError) as stale:
            await service.delete_tag(actor, workspace_id, UUID(str(target["id"])), 2)
        assert stale.value.code == "VERSION_CONFLICT"
        other = await service.create_tag(actor, workspace_id, "Other")
        with pytest.raises(KnowledgeError) as viewer_forbidden:
            await service.merge_tag(
                viewer,
                workspace_id,
                UUID(str(target["id"])),
                UUID(str(other["id"])),
                1,
                1,
            )
        assert viewer_forbidden.value.code == "TAG_FORBIDDEN"
    finally:
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_mixed_trash_lists_files_and_notes_and_restricts_version_delete() -> None:
    engine, service, workspace_id, actor, viewer = await context("trash")
    try:
        note = await service.create_note(actor, workspace_id, "Trash note", "kept")
        file_id = uuid4()
        async with engine.begin() as conn:  # type: ignore[attr-defined]
            await conn.execute(
                text(
                    """INSERT INTO ima.documents
                    (id,workspace_id,folder_id,kind,title,normalized_title,file_state,
                     created_by,updated_by,created_at,updated_at)
                    VALUES (:id,:workspace,:folder,'file','Trash file','trash file','pending',:actor,:actor,:now,:now)"""
                ),
                {
                    "id": file_id,
                    "workspace": workspace_id,
                    "folder": workspace_id,
                    "actor": actor,
                    "now": datetime.now(UTC),
                },
            )
        await service.trash_document(actor, UUID(str(note["id"])), int(note["version"]))
        await service.trash_document(actor, file_id, 1)
        kinds = {
            item["kind"]
            for item in (await service.list_trash(actor, workspace_id, None, 50))["items"]
        }
        assert {"note", "file"} <= kinds
        with pytest.raises(KnowledgeError) as dependency:
            await service.delete_document(actor, UUID(str(note["id"])))
        assert dependency.value.code == "DEPENDENCY_EXISTS"
        await service.delete_document(actor, file_id)
    finally:
        await close_context(engine, workspace_id, actor, viewer)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_trash_paginates_and_hides_versions_for_trashed_documents() -> None:
    engine, service, workspace_id, actor, viewer = await context("trash-pagination")
    try:
        documents = [
            await service.create_note(actor, workspace_id, f"Trash {index}", "hidden")
            for index in range(3)
        ]
        for document in documents:
            await service.trash_document(actor, UUID(str(document["id"])), int(document["version"]))
        first = await service.list_trash(actor, workspace_id, None, 2)
        assert len(first["items"]) == 2
        assert first["nextCursor"]
        second = await service.list_trash(actor, workspace_id, first["nextCursor"], 2)
        assert len(second["items"]) == 1
        assert {item["id"] for item in first["items"]}.isdisjoint(
            item["id"] for item in second["items"]
        )
        with pytest.raises(KnowledgeError) as hidden:
            await service.list_versions(viewer, UUID(str(documents[0]["id"])))
        assert hidden.value.code == "DOCUMENT_NOT_FOUND"
        active = await service.create_note(actor, workspace_id, "Active", "visible")
        with pytest.raises(KnowledgeError) as active_delete:
            await service.delete_document(actor, UUID(str(active["id"])))
        assert active_delete.value.code == "VERSION_CONFLICT"
    finally:
        await close_context(engine, workspace_id, actor, viewer)
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
