"""Bounded, fail-closed authorization bridge for remaining Bun readers."""

# Keep private bridge SQL visible for review.
# ruff: noqa: E501

from __future__ import annotations

import hmac
from typing import Literal

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.maintenance import MUTATING_ACTIONS, freeze_active
from ima.domain.authorization import AclAction

router = APIRouter(prefix="/internal/authorization", tags=["internal"], include_in_schema=False)

BridgeAction = Literal[
    "view_metadata",
    "view_content",
    "download",
    "ask",
    "create_child",
    "edit",
    "move",
    "delete",
    "manage_acl",
]


class AuthorizationBridgeRequest(BaseModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=64)
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=64)
    folder_id: str = Field(alias="folderId", min_length=1, max_length=64)
    action: BridgeAction


class AuthorizationBatchRequest(BaseModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=64)
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=64)
    folder_ids: tuple[str, ...] = Field(alias="folderIds", min_length=1, max_length=500)
    action: BridgeAction


async def _target_decision(
    service: WorkspaceService, payload: AuthorizationBridgeRequest
) -> dict[str, object]:
    from ima.infrastructure.db.authorization import accessible_folder_ids, load_subject

    async with service.engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM ima.folders WHERE id=:folder AND workspace_id=:workspace"),
            {"folder": payload.folder_id, "workspace": payload.workspace_id},
        )
        if not exists:
            return {"allowed": False, "reason": "unavailable", "source": "legacy"}
        subject = await load_subject(conn, payload.user_id, payload.workspace_id)
        if not subject:
            return {"allowed": False, "reason": "hidden", "source": "target"}
        ids = await accessible_folder_ids(conn, subject, AclAction(payload.action))
        return {
            "allowed": payload.folder_id in ids,
            "reason": "allowed" if payload.folder_id in ids else "hidden",
            "source": "target",
        }


@router.post("/decide", operation_id="internalAuthorizationDecide")
async def decide(
    payload: AuthorizationBridgeRequest,
    request: Request,
    x_ima_bridge_token: str | None = Header(default=None),
) -> dict[str, object]:
    expected = request.app.state.settings.bridge_token.get_secret_value()
    if not x_ima_bridge_token or not hmac.compare_digest(x_ima_bridge_token, expected):
        return {"allowed": False, "reason": "bridge_unauthorized"}
    service = WorkspaceService(request.app.state.db_engine, request.app.state.settings)
    action = AclAction(payload.action)
    if action in MUTATING_ACTIONS:
        async with service.engine.connect() as conn:
            if await freeze_active(conn):
                return {"allowed": False, "reason": "maintenance_freeze", "source": "target"}
    try:
        return await _target_decision(service, payload)
    except (WorkspaceError, ValueError):
        return {"allowed": False, "reason": "hidden"}


@router.post("/batch", operation_id="internalAuthorizationBatch")
async def batch_decide(
    payload: AuthorizationBatchRequest,
    request: Request,
    x_ima_bridge_token: str | None = Header(default=None),
) -> dict[str, object]:
    expected = request.app.state.settings.bridge_token.get_secret_value()
    if not x_ima_bridge_token or not hmac.compare_digest(x_ima_bridge_token, expected):
        return {"items": []}
    service = WorkspaceService(request.app.state.db_engine, request.app.state.settings)
    if AclAction(payload.action) in MUTATING_ACTIONS:
        async with service.engine.connect() as conn:
            if await freeze_active(conn):
                return {
                    "items": [
                        {
                            "folderId": folder_id,
                            "allowed": False,
                            "reason": "maintenance_freeze",
                            "source": "target",
                        }
                        for folder_id in payload.folder_ids
                    ]
                }
    try:
        from ima.infrastructure.db.authorization import accessible_folder_ids, load_subject

        async with service.engine.connect() as conn:
            target_ids = {
                str(row[0])
                for row in (
                    await conn.execute(
                        text(
                            "SELECT id FROM ima.folders WHERE workspace_id=:workspace AND id IN :ids"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"workspace": payload.workspace_id, "ids": payload.folder_ids},
                    )
                )
            }
            subject = await load_subject(conn, payload.user_id, payload.workspace_id)
            allowed_ids = (
                await accessible_folder_ids(conn, subject, AclAction(payload.action))
                if subject
                else set()
            )
            return {
                "items": [
                    {
                        "folderId": folder_id,
                        "allowed": folder_id in allowed_ids,
                        "reason": "allowed" if folder_id in allowed_ids else "hidden",
                        "source": "target" if folder_id in target_ids else "legacy",
                    }
                    for folder_id in payload.folder_ids
                ]
            }
    except (WorkspaceError, ValueError):
        return {"items": []}


@router.post("/member", operation_id="internalAuthorizationMember")
async def member(
    payload: dict[str, str],
    request: Request,
    x_ima_bridge_token: str | None = Header(default=None),
) -> dict[str, object]:
    expected = request.app.state.settings.bridge_token.get_secret_value()
    if not x_ima_bridge_token or not hmac.compare_digest(x_ima_bridge_token, expected):
        return {"member": None, "source": "denied"}
    user_id = payload.get("userId", "")
    workspace_id = payload.get("workspaceId", "")
    service = WorkspaceService(request.app.state.db_engine, request.app.state.settings)
    async with service.engine.connect() as conn:
        workspace_exists = await conn.scalar(
            text("SELECT 1 FROM ima.workspaces WHERE id=:workspace"), {"workspace": workspace_id}
        )
        if not workspace_exists:
            return {"member": None, "source": "legacy"}
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT role,state FROM ima.workspace_members WHERE workspace_id=:workspace AND user_id=:user"
                    ),
                    {"workspace": workspace_id, "user": user_id},
                )
            )
            .mappings()
            .first()
        )
        if not row or row["state"] != "active":
            return {"member": None, "source": "target"}
        return {"member": {"role": row["role"], "state": row["state"]}, "source": "target"}
