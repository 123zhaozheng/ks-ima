"""PostgreSQL authorization gate for the knowledge base slice."""

# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from ima.application.authorization import KbError, KbService
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")

OWNER_ID = "authz-admin"
VIEWER_ID = "authz-viewer"
JOINER_ID = "authz-joiner"
USER_IDS = (OWNER_ID, VIEWER_ID, JOINER_ID)


def integration_settings() -> Settings:
    assert DATABASE_URL is not None
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="authorization-integration-session",
        token_pepper="authorization-integration-token",
        totp_encryption_key="authorization-integration-key",
        smtp_host=None,
        smtp_from=None,
    )


async def create_fixture(engine: object, service: KbService) -> tuple[str, str, str]:
    stamp = datetime.now(UTC)
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN (:owner,:viewer,:joiner)"),
            {"owner": OWNER_ID, "viewer": VIEWER_ID, "joiner": JOINER_ID},
        )
        await conn.execute(
            text("DELETE FROM ima.knowledge_bases WHERE created_by IN (:owner,:viewer,:joiner)"),
            {"owner": OWNER_ID, "viewer": VIEWER_ID, "joiner": JOINER_ID},
        )
        await conn.execute(text("DELETE FROM ima.knowledge_bases WHERE id LIKE 'authz-%'"))
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN (:owner,:viewer,:joiner)"),
            {"owner": OWNER_ID, "viewer": VIEWER_ID, "joiner": JOINER_ID},
        )
        for user_id, email in (
            (OWNER_ID, "authz-admin@example.test"),
            (VIEWER_ID, "authz-viewer@example.test"),
            (JOINER_ID, "authz-joiner@example.test"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (:id,:email,:email,:id,true,false,:stamp,:now,:now)"
                ),
                {"id": user_id, "email": email, "stamp": user_id, "now": stamp},
            )
        await conn.execute(
            text(
                "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (:id,'platform_admin',:now)"
            ),
            {"id": OWNER_ID, "now": stamp},
        )
    knowledge_base = await service.create_knowledge_base(OWNER_ID, "Authorization Fixture")
    kb_id = str(knowledge_base["id"])
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text(
                "INSERT INTO ima.kb_members(kb_id,user_id,role,state,version,joined_at) VALUES (:kb,:u,'viewer','active',1,:now)"
            ),
            {"kb": kb_id, "u": VIEWER_ID, "now": stamp},
        )
    return kb_id, OWNER_ID, VIEWER_ID


async def cleanup(engine: object, kb_id: str, user_ids: tuple[str, ...]) -> None:
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN :ids").bindparams(
                __import__("sqlalchemy").bindparam("ids", expanding=True)
            ),
            {"ids": user_ids},
        )
        await conn.execute(text("DELETE FROM ima.kb_share_links WHERE kb_id=:kb"), {"kb": kb_id})
        await conn.execute(text("DELETE FROM ima.kb_members WHERE kb_id=:kb"), {"kb": kb_id})
        await conn.execute(text("DELETE FROM ima.folder_closure WHERE kb_id=:kb"), {"kb": kb_id})
        await conn.execute(text("DELETE FROM ima.folders WHERE kb_id=:kb"), {"kb": kb_id})
        await conn.execute(text("DELETE FROM ima.knowledge_bases WHERE id=:kb"), {"kb": kb_id})
        await conn.execute(
            text("DELETE FROM ima.platform_role_assignments WHERE user_id IN :ids").bindparams(
                __import__("sqlalchemy").bindparam("ids", expanding=True)
            ),
            {"ids": user_ids},
        )
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN :ids").bindparams(
                __import__("sqlalchemy").bindparam("ids", expanding=True)
            ),
            {"ids": user_ids},
        )


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_kb_role_matrix_hidden_membership_and_archive() -> None:
    assert DATABASE_URL is not None
    root = Path(__file__).parents[2]
    env = {
        **os.environ,
        "IMA_DATABASE_URL": DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://"),
    }
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
    )
    subprocess.run(
        ["uv", "run", "alembic", "-c", "alembic.ini", "upgrade", "head"],
        cwd=root,
        env=env,
        check=True,
    )
    settings = integration_settings()
    engine = create_engine(settings)
    service = KbService(engine, settings)
    kb_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        # Viewers read the tree but never mutate it.
        assert await service.folders(viewer_id, kb_id)
        with pytest.raises(KbError, match="Folder not found"):
            await service.create_folder(viewer_id, kb_id, kb_id, "Blocked")
        # Non-members cannot even see the knowledge base.
        with pytest.raises(KbError, match="Knowledge base not found"):
            await service.folders(JOINER_ID, kb_id)
        # Denial audits survive the rolled-back caller transactions.
        async with engine.connect() as conn:
            denied = (
                await conn.execute(
                    text(
                        "SELECT actor_id, reason_code FROM ima.audit_events "
                        "WHERE action = 'kb.authorization.denied' AND result = 'failure' "
                        "AND actor_id IN (:viewer, :joiner)"
                    ),
                    {"viewer": viewer_id, "joiner": JOINER_ID},
                )
            ).all()
        assert {row.actor_id for row in denied} == {viewer_id, JOINER_ID}
        # Only the owner manages members, and the owner role is protected.
        with pytest.raises(KbError, match="owner access is required"):
            await service.update_member_role(viewer_id, kb_id, viewer_id, "editor")
        with pytest.raises(KbError, match="owner role cannot be changed"):
            await service.update_member_role(actor_id, kb_id, actor_id, "viewer")
        promoted = await service.update_member_role(actor_id, kb_id, viewer_id, "editor")
        assert promoted["role"] == "editor"
        editor_folder = await service.create_folder(viewer_id, kb_id, kb_id, "Editor Space")
        assert editor_folder["kbId"] == kb_id
        # Archival hides the knowledge base from every member read.
        await service.archive_knowledge_base(actor_id, kb_id)
        with pytest.raises(KbError, match="Knowledge base not found"):
            await service.folders(viewer_id, kb_id)
        with pytest.raises(KbError, match="Knowledge base not found"):
            await service.folders(actor_id, kb_id)
        # The owner keeps restore authority while everyone else stays hidden.
        await service.restore_knowledge_base(actor_id, kb_id)
        assert await service.folders(viewer_id, kb_id)
    finally:
        await cleanup(engine, kb_id, USER_IDS)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_kb_move_closure_and_owner_protection() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = KbService(engine, settings)
    kb_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        first = await service.create_folder(actor_id, kb_id, kb_id, "First")
        second = await service.create_folder(actor_id, kb_id, kb_id, "Second")
        nested = await service.create_folder(actor_id, kb_id, first["id"], "Nested")
        moved = await service.move_folder(actor_id, kb_id, nested["id"], second["id"], 1)
        assert moved["parentId"] == second["id"]
        async with engine.connect() as conn:
            closure = (
                await conn.execute(
                    text(
                        "SELECT ancestor_id,depth FROM ima.folder_closure WHERE kb_id=:kb AND descendant_id=:d ORDER BY depth"
                    ),
                    {"kb": kb_id, "d": nested["id"]},
                )
            ).all()
            assert (kb_id, 2) in {(str(row[0]), int(row[1])) for row in closure}
        # The single owner cannot be removed, demoted, or leave.
        with pytest.raises(KbError, match="owner cannot be removed"):
            await service.remove_member(actor_id, kb_id, actor_id)
        with pytest.raises(KbError, match="owner cannot leave"):
            await service.leave_knowledge_base(actor_id, kb_id)
        # Removing a non-owner member deletes the membership row.
        await service.remove_member(actor_id, kb_id, viewer_id)
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u"),
                    {"kb": kb_id, "u": viewer_id},
                )
                == 0
            )
    finally:
        await cleanup(engine, kb_id, USER_IDS)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_share_link_join_is_idempotent_and_revocable() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = KbService(engine, settings)
    kb_id, actor_id, _viewer_id = await create_fixture(engine, service)
    try:
        link = await service.create_share_link(actor_id, kb_id, "viewer")
        token = str(link["url"]).rsplit("/", 1)[-1]
        joined = await service.accept_share_link(JOINER_ID, token)
        assert joined["role"] == "viewer"
        # Accepting again is idempotent and never demotes the member.
        again = await service.accept_share_link(JOINER_ID, token)
        assert again["role"] == "viewer"
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u AND state='active'"
                    ),
                    {"kb": kb_id, "u": JOINER_ID},
                )
                == 1
            )
        # Revocation blocks new joiners but keeps joined members.
        await service.revoke_share_link(actor_id, kb_id, str(link["id"]))
        with pytest.raises(KbError, match="invalid or has been revoked"):
            await service.accept_share_link(VIEWER_ID, token)
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u AND state='active'"
                    ),
                    {"kb": kb_id, "u": JOINER_ID},
                )
                == 1
            )
    finally:
        await cleanup(engine, kb_id, USER_IDS)
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_archived_kb_delete_refuses_content_then_removes_target_authorization() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = KbService(engine, settings)
    kb_id, actor_id, _viewer_id = await create_fixture(engine, service)
    try:
        await service.create_folder(actor_id, kb_id, kb_id, "Retained")
        await service.archive_knowledge_base(actor_id, kb_id)
        with pytest.raises(KbError, match="content dependencies"):
            await service.delete_archived_knowledge_base(actor_id, kb_id)
    finally:
        await cleanup(engine, kb_id, USER_IDS)
        await engine.dispose()

    engine = create_engine(settings)
    service = KbService(engine, settings)
    kb_id, actor_id, _viewer_id = await create_fixture(engine, service)
    try:
        child = await service.create_folder(actor_id, kb_id, kb_id, "Removed")
        await service.delete_folder(actor_id, kb_id, child["id"], child["version"])
        await service.archive_knowledge_base(actor_id, kb_id)
        await service.delete_archived_knowledge_base(actor_id, kb_id)
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT 1 FROM ima.knowledge_bases WHERE id=:kb"), {"kb": kb_id}
                )
                is None
            )
            assert (
                await conn.scalar(
                    text("SELECT count(*) FROM ima.kb_members WHERE kb_id=:kb"), {"kb": kb_id}
                )
                == 0
            )
    finally:
        await engine.dispose()
        # The successful path has no knowledge base left; clean users and audit rows.
        cleanup_engine = create_engine(settings)
        async with cleanup_engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM ima.audit_events WHERE actor_id IN ('authz-admin','authz-viewer','authz-joiner')"
                )
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.platform_role_assignments WHERE user_id IN ('authz-admin','authz-viewer','authz-joiner')"
                )
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.users WHERE id IN ('authz-admin','authz-viewer','authz-joiner')"
                )
            )
        await cleanup_engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_kb_closure_query_plan_uses_target_indexes() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = KbService(engine, settings)
    kb_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL enable_seqscan=off"))
            plan = (
                (
                    await conn.execute(
                        text(
                            "EXPLAIN SELECT descendant_id FROM ima.folder_closure WHERE kb_id=:kb AND ancestor_id=:kb"
                        ),
                        {"kb": kb_id},
                    )
                )
                .scalars()
                .all()
            )
            assert "Index" in " ".join(str(line) for line in plan)
    finally:
        await cleanup(engine, kb_id, (actor_id, viewer_id, JOINER_ID))
        await engine.dispose()
