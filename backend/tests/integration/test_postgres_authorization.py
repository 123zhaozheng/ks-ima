"""PostgreSQL authorization gate for the target workspace slice."""

# ruff: noqa: E501, ASYNC221

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.config import Settings
from ima.domain.authorization import AclAction, MembershipState, WorkspaceRole
from ima.infrastructure.db.authorization import accessible_folder_ids, folder_decision, load_subject
from ima.infrastructure.db.engine import create_engine

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")


def integration_settings() -> Settings:
    assert DATABASE_URL is not None
    return Settings(
        environment="test",
        database_url=DATABASE_URL,
        session_pepper="authorization-integration-session",
        token_pepper="authorization-integration-token",
        totp_encryption_key="authorization-integration-key",
        bridge_token="authorization-integration-bridge",
        smtp_host=None,
        smtp_from=None,
    )


async def create_fixture(engine: object, service: WorkspaceService) -> tuple[str, str, str]:
    stamp = datetime.now(UTC)
    actor_id, viewer_id, invitee_id = "authz-admin", "authz-viewer", "authz-invitee"
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN (:actor,:viewer,:invitee)"),
            {"actor": actor_id, "viewer": viewer_id, "invitee": invitee_id},
        )
        await conn.execute(
            text("DELETE FROM ima.workspaces WHERE created_by IN (:actor,:viewer,:invitee)"),
            {"actor": actor_id, "viewer": viewer_id, "invitee": invitee_id},
        )
        await conn.execute(text("DELETE FROM ima.workspaces WHERE id LIKE 'authz-%'"))
        await conn.execute(
            text("DELETE FROM ima.users WHERE id IN (:actor,:viewer,:invitee)"),
            {"actor": actor_id, "viewer": viewer_id, "invitee": invitee_id},
        )
        for user_id, email in (
            (actor_id, "authz-admin@example.test"),
            (viewer_id, "authz-viewer@example.test"),
            (invitee_id, "authz-invitee@example.test"),
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
            {"id": actor_id, "now": stamp},
        )
    workspace = await service.create_workspace(actor_id, "Authorization Fixture", actor_id)
    workspace_id = str(workspace["id"])
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text(
                "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,joined_at,updated_at) VALUES (:w,:u,'viewer','active',:now,:now)"
            ),
            {"w": workspace_id, "u": viewer_id, "now": stamp},
        )
    return workspace_id, actor_id, viewer_id


async def cleanup(engine: object, workspace_id: str, user_ids: tuple[str, ...]) -> None:
    async with engine.begin() as conn:  # type: ignore[attr-defined]
        await conn.execute(
            text("DELETE FROM ima.audit_events WHERE actor_id IN :ids").bindparams(
                __import__("sqlalchemy").bindparam("ids", expanding=True)
            ),
            {"ids": user_ids},
        )
        await conn.execute(text("DELETE FROM ima.workspaces WHERE id=:id"), {"id": workspace_id})
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
async def test_authorization_schema_policy_hidden_revoke_and_archive() -> None:
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
    service = WorkspaceService(engine, settings)
    workspace_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        child = await service.create_folder(actor_id, workspace_id, workspace_id, "Private")
        await service.set_acl(
            actor_id,
            workspace_id,
            child["id"],
            inherit=False,
            entries=[
                {"subject_type": "role", "subject_id": "workspace_admin", "action": "manage_acl"},
                {
                    "subject_type": "role",
                    "subject_id": "workspace_admin",
                    "action": "view_metadata",
                },
                {"subject_type": "role", "subject_id": "workspace_admin", "action": "view_content"},
                {"subject_type": "role", "subject_id": "viewer", "action": "view_metadata"},
                {"subject_type": "role", "subject_id": "viewer", "action": "view_content"},
            ],
        )
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT version FROM ima.folder_acls WHERE folder_id=:id"),
                    {"id": child["id"]},
                )
                == 1
            )
        await service.set_acl(
            actor_id,
            workspace_id,
            child["id"],
            inherit=False,
            entries=[
                {"subject_type": "role", "subject_id": "workspace_admin", "action": "manage_acl"},
                {
                    "subject_type": "role",
                    "subject_id": "workspace_admin",
                    "action": "view_metadata",
                },
                {"subject_type": "role", "subject_id": "workspace_admin", "action": "view_content"},
            ],
            expected_version=1,
        )
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT version FROM ima.folder_acls WHERE folder_id=:id"),
                    {"id": child["id"]},
                )
                == 2
            )
        async with engine.connect() as conn:
            subject = await load_subject(conn, viewer_id, workspace_id)
            assert subject is not None
            visible = await accessible_folder_ids(conn, subject, AclAction.ASK)
            assert child["id"] not in visible
            decision = await folder_decision(conn, subject, child["id"], AclAction.DOWNLOAD)
            assert not decision.allowed
        with pytest.raises(WorkspaceError, match="Folder not found"):
            await service.acl(viewer_id, workspace_id, child["id"])
        with pytest.raises(WorkspaceError, match="Folder not found|permission preview"):
            await service.permission_preview(viewer_id, workspace_id, viewer_id)
        await service.mutate_member(
            actor_id, workspace_id, viewer_id, state=MembershipState.DISABLED, expected_version=1
        )
        async with engine.connect() as conn:
            assert await load_subject(conn, viewer_id, workspace_id) is None
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.workspaces SET is_active=false,archived_at=now() WHERE id=:id"),
                {"id": workspace_id},
            )
            subject = await load_subject(conn, actor_id, workspace_id)
            assert subject is not None
            assert not await accessible_folder_ids(conn, subject, AclAction.VIEW_CONTENT)
    finally:
        await cleanup(engine, workspace_id, (actor_id, viewer_id, "authz-invitee"))
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_authorization_move_closure_acl_dependencies_and_last_admin() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = WorkspaceService(engine, settings)
    workspace_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        first = await service.create_folder(actor_id, workspace_id, workspace_id, "First")
        second = await service.create_folder(actor_id, workspace_id, workspace_id, "Second")
        nested = await service.create_folder(actor_id, workspace_id, first["id"], "Nested")
        moved = await service.move_folder(actor_id, workspace_id, nested["id"], second["id"], 1)
        assert moved["parent_id"] == second["id"]
        async with engine.connect() as conn:
            closure = (
                await conn.execute(
                    text(
                        "SELECT ancestor_id,depth FROM ima.folder_closure WHERE workspace_id=:w AND descendant_id=:d ORDER BY depth"
                    ),
                    {"w": workspace_id, "d": nested["id"]},
                )
            ).all()
            assert (workspace_id, 2) in {(str(row[0]), int(row[1])) for row in closure}
        with pytest.raises(WorkspaceError, match="administrable"):
            await service.set_acl(
                actor_id,
                workspace_id,
                second["id"],
                inherit=False,
                entries=[
                    {"subject_type": "role", "subject_id": "viewer", "action": "view_content"}
                ],
                expected_version=1,
            )
        await service.mutate_member(
            actor_id,
            workspace_id,
            viewer_id,
            role=WorkspaceRole.WORKSPACE_ADMIN,
            expected_version=1,
        )
        await service.mutate_member(
            actor_id, workspace_id, actor_id, role=WorkspaceRole.VIEWER, expected_version=1
        )
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.workspace_members WHERE workspace_id=:w AND role='workspace_admin' AND state='active'"
                    ),
                    {"w": workspace_id},
                )
                == 1
            )
    finally:
        await cleanup(engine, workspace_id, (actor_id, viewer_id, "authz-invitee"))
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_authorization_invitation_is_single_use_and_concurrent_admin_guard() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = WorkspaceService(engine, settings)
    workspace_id, actor_id, _viewer_id = await create_fixture(engine, service)
    try:
        invitation = await service.issue_invitation(
            actor_id, workspace_id, "authz-invitee", WorkspaceRole.VIEWER
        )
        assert invitation["delivery"] == "manual"
        await service.accept_invitation("authz-invitee", invitation["boundLink"].rsplit("/", 1)[-1])
        with pytest.raises(WorkspaceError, match="expired, revoked"):
            await service.accept_invitation(
                "authz-invitee", invitation["boundLink"].rsplit("/", 1)[-1]
            )
        await service.mutate_member(
            actor_id,
            workspace_id,
            "authz-viewer",
            role=WorkspaceRole.WORKSPACE_ADMIN,
            expected_version=1,
        )

        async def demote(user_id: str, expected_version: int) -> object:
            try:
                return await service.mutate_member(
                    actor_id,
                    workspace_id,
                    user_id,
                    role=WorkspaceRole.VIEWER,
                    expected_version=expected_version,
                )
            except WorkspaceError as exc:
                return exc

        results = await asyncio.gather(demote(actor_id, 1), demote("authz-viewer", 2))
        assert any(isinstance(result, WorkspaceError) for result in results)
    finally:
        await cleanup(engine, workspace_id, (actor_id, "authz-viewer", "authz-invitee"))
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_archived_workspace_delete_refuses_content_then_removes_target_authorization() -> (
    None
):
    settings = integration_settings()
    engine = create_engine(settings)
    service = WorkspaceService(engine, settings)
    workspace_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        child = await service.create_folder(actor_id, workspace_id, workspace_id, "Retained")
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.workspaces SET is_active=false,archived_at=now() WHERE id=:id"),
                {"id": workspace_id},
            )
        with pytest.raises(WorkspaceError, match="folder content"):
            await service.delete_archived_workspace(actor_id, workspace_id)
        # Recreate a clean target-only workspace for the successful deletion path.
    finally:
        await engine.dispose()

    engine = create_engine(settings)
    service = WorkspaceService(engine, settings)
    workspace_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        child = await service.create_folder(actor_id, workspace_id, workspace_id, "Removed")
        await service.trash_folder(actor_id, workspace_id, child["id"], child["version"])
        await service.delete_folder(actor_id, workspace_id, child["id"], child["version"] + 1)
        async with engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.workspaces SET is_active=false,archived_at=now() WHERE id=:id"),
                {"id": workspace_id},
            )
        await service.delete_archived_workspace(actor_id, workspace_id)
        async with engine.connect() as conn:
            assert (
                await conn.scalar(
                    text("SELECT 1 FROM ima.workspaces WHERE id=:id"), {"id": workspace_id}
                )
                is None
            )
    finally:
        await engine.dispose()
        # The successful path has no workspace left; clean users and audit rows.
        cleanup_engine = create_engine(settings)
        async with cleanup_engine.begin() as conn:
            await conn.execute(
                text(
                    "DELETE FROM ima.audit_events WHERE actor_id IN ('authz-admin','authz-viewer','authz-invitee')"
                )
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.users WHERE id IN ('authz-admin','authz-viewer','authz-invitee')"
                )
            )
        await cleanup_engine.dispose()


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_authorization_closure_query_plan_uses_target_indexes() -> None:
    settings = integration_settings()
    engine = create_engine(settings)
    service = WorkspaceService(engine, settings)
    workspace_id, actor_id, viewer_id = await create_fixture(engine, service)
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SET LOCAL enable_seqscan=off"))
            plan = (
                (
                    await conn.execute(
                        text(
                            "EXPLAIN SELECT descendant_id FROM ima.folder_closure WHERE workspace_id=:w AND ancestor_id=:w"
                        ),
                        {"w": workspace_id},
                    )
                )
                .scalars()
                .all()
            )
            assert "Index" in " ".join(str(line) for line in plan)
    finally:
        await cleanup(engine, workspace_id, (actor_id, viewer_id, "authz-invitee"))
        await engine.dispose()
