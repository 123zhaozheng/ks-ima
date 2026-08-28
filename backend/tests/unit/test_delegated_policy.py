"""Service-principal policy tests with no user-membership fallback."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.mcp_contracts import McpActor
from ima.config import Settings
from ima.domain.authorization import AclAction


class _Mappings:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def first(self) -> dict[str, object] | None:
        return self.row


class _Result:
    def __init__(self, row: dict[str, object] | None) -> None:
        self.row = row

    def mappings(self) -> _Mappings:
        return _Mappings(self.row)


class _Connection:
    def __init__(self, *, active: bool = True, within_root: bool = True) -> None:
        self.active = active
        self.within_root = within_root
        self.statements: list[str] = []
        self.scalar_calls = 0

    async def execute(self, statement: object, _: object) -> _Result:
        sql = str(statement)
        self.statements.append(sql)
        row = (
            {
                "workspace_id": "workspace-1",
                "folder_root_id": "root-1",
                "scopes": ("mcp:knowledge:read",),
                "is_active": True,
            }
            if self.active
            else None
        )
        return _Result(row)

    async def scalar(self, statement: object, _: object) -> bool:
        self.statements.append(str(statement))
        self.scalar_calls += 1
        return True if self.scalar_calls == 1 else self.within_root


def service() -> WorkspaceService:
    return WorkspaceService(cast(Any, SimpleNamespace()), Settings(environment="test"))


def actor() -> McpActor:
    return McpActor(
        actor_type="service_principal",
        principal_id="11111111-1111-1111-1111-111111111111",
        workspace_id="workspace-1",
        folder_root_id="root-1",
        scopes=("mcp:knowledge:read",),
    )


@pytest.mark.asyncio
async def test_delegated_action_uses_principal_policy_without_owner_membership() -> None:
    conn = _Connection()
    await service()._require_delegated_action(
        cast(Any, conn), actor(), "workspace-1", "child-1", AclAction.VIEW_CONTENT
    )
    sql = " ".join(conn.statements).lower()
    assert "mcp_service_principals" in sql
    assert "owner_user_id" not in sql
    assert "workspace_members" not in sql


@pytest.mark.asyncio
async def test_delegated_action_denies_revoked_principal_and_outside_root() -> None:
    with pytest.raises(WorkspaceError):
        await service()._require_delegated_action(
            cast(Any, _Connection(active=False)),
            actor(),
            "workspace-1",
            "child-1",
            AclAction.VIEW_CONTENT,
        )
    with pytest.raises(WorkspaceError) as outside:
        await service()._require_delegated_action(
            cast(Any, _Connection(within_root=False)),
            actor(),
            "workspace-1",
            "outside-1",
            AclAction.DOWNLOAD,
        )
    assert outside.value.code == "FOLDER_NOT_FOUND"
