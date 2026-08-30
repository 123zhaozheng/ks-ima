"""Workspace membership, folder, and ACL HTTP adapters."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request

from ima.api.v1.auth import Current, check_csrf
from ima.api.v1.identity_contracts import WorkspaceCreateResponse
from ima.api.v1.workspace_contracts import (
    AclReplaceRequest,
    AclSubject,
    Folder,
    FolderAcl,
    FolderCreateRequest,
    FolderLifecycleRequest,
    FolderMoveRequest,
    FolderPatchRequest,
    FolderReorderRequest,
    GroupCreateRequest,
    GroupDeleteRequest,
    Invitation,
    InvitationCreateRequest,
    MemberAddRequest,
    MemberPatchRequest,
    MemberWorkspace,
    MemberWorkspaceCreateRequest,
    PermissionPreviewRequest,
    UserSearchResult,
    WorkspaceAdminRepairRequest,
    WorkspaceGroup,
    WorkspaceMember,
)
from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.domain.authorization import MembershipState, WorkspaceRole

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def workspace_service(request: Request) -> WorkspaceService:
    return cast(WorkspaceService, request.app.state.workspace_service)


def map_error(exc: WorkspaceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def role(value: str) -> WorkspaceRole:
    return WorkspaceRole(value)


@router.get("", operation_id="listMemberWorkspaces")
async def list_member_workspaces(request: Request, current: Current) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).list_workspaces(current[1].id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "", response_model=WorkspaceCreateResponse, operation_id="createMemberWorkspace"
)
async def create_member_workspace(
    payload: MemberWorkspaceCreateRequest, request: Request, current: Current
) -> WorkspaceCreateResponse:
    session, actor = current
    check_csrf(request, session)
    try:
        workspace = await workspace_service(request).create_workspace(
            actor.id, payload.name, actor.id, self_service=True
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc
    return WorkspaceCreateResponse(id=workspace["id"], name=workspace["name"], isActive=True)


@router.get("/{workspace_id}", response_model=MemberWorkspace, operation_id="getMemberWorkspace")
async def get_member_workspace(
    workspace_id: str, request: Request, current: Current
) -> dict[str, Any]:
    try:
        return await workspace_service(request).get_workspace(current[1].id, workspace_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/members",
    response_model=tuple[WorkspaceMember, ...],
    operation_id="listWorkspaceMembers",
)
async def list_members(
    workspace_id: str, request: Request, current: Current, q: str = ""
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).members(current[1].id, workspace_id, q)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/members/search",
    response_model=tuple[UserSearchResult, ...],
    operation_id="searchWorkspaceUsers",
)
async def search_members(
    workspace_id: str, request: Request, current: Current, q: str = ""
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).search_users(current[1].id, workspace_id, q)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/members", response_model=WorkspaceMember, operation_id="addWorkspaceMember"
)
async def add_member(
    workspace_id: str, payload: MemberAddRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).add_member(
            actor.id, workspace_id, payload.user_id, role(payload.role)
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.patch(
    "/{workspace_id}/members/{user_id}",
    response_model=WorkspaceMember,
    operation_id="updateWorkspaceMember",
)
async def update_member(
    workspace_id: str, user_id: str, payload: MemberPatchRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).mutate_member(
            actor.id,
            workspace_id,
            user_id,
            role=role(payload.role) if payload.role else None,
            state=MembershipState(payload.state) if payload.state else None,
            expected_version=payload.expected_version,
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{workspace_id}/members/{user_id}", status_code=204, operation_id="removeWorkspaceMember"
)
async def remove_member(
    workspace_id: str,
    user_id: str,
    request: Request,
    current: Current,
    expected_version: int | None = None,
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).remove_member(
            actor.id, workspace_id, user_id, expected_version
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post("/{workspace_id}/leave", status_code=204, operation_id="leaveWorkspace")
async def leave_workspace(workspace_id: str, request: Request, current: Current) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).leave(actor.id, workspace_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/invitations",
    response_model=tuple[Invitation, ...],
    operation_id="listWorkspaceInvitations",
)
async def list_invitations(
    workspace_id: str, request: Request, current: Current
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).invitations(current[1].id, workspace_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/invitations",
    response_model=Invitation,
    operation_id="issueWorkspaceInvitation",
)
async def issue_invitation(
    workspace_id: str, payload: InvitationCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).issue_invitation(
            actor.id, workspace_id, payload.user_id, role(payload.role)
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{workspace_id}/invitations/{invitation_id}",
    status_code=204,
    operation_id="revokeWorkspaceInvitation",
)
async def revoke_invitation(
    workspace_id: str, invitation_id: str, request: Request, current: Current
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).revoke_invitation(actor.id, workspace_id, invitation_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


invitation_router = APIRouter(prefix="/workspace-invitations", tags=["workspaces"])


@invitation_router.post("/{token}/accept", operation_id="acceptWorkspaceInvitation")
async def accept_invitation(token: str, request: Request, current: Current) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).accept_invitation(actor.id, token)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/groups",
    response_model=tuple[WorkspaceGroup, ...],
    operation_id="listWorkspaceGroups",
)
async def list_groups(
    workspace_id: str, request: Request, current: Current
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).groups(current[1].id, workspace_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/groups", response_model=WorkspaceGroup, operation_id="createWorkspaceGroup"
)
async def create_group(
    workspace_id: str, payload: GroupCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).create_group(actor.id, workspace_id, payload.name)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/groups/{group_id}/members",
    response_model=tuple[UserSearchResult, ...],
    operation_id="listWorkspaceGroupMembers",
)
async def list_group_members(
    workspace_id: str, group_id: str, request: Request, current: Current
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).group_members(current[1].id, workspace_id, group_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.delete("/{workspace_id}/groups/{group_id}", operation_id="deleteWorkspaceGroup")
async def delete_group(
    workspace_id: str,
    group_id: str,
    request: Request,
    current: Current,
    payload: GroupDeleteRequest | None = None,
) -> dict[str, int]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).delete_group(
            actor.id, workspace_id, group_id, payload.expected_version if payload else None
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.put(
    "/{workspace_id}/groups/{group_id}/members/{user_id}",
    status_code=204,
    operation_id="addWorkspaceGroupMember",
)
async def add_group_member(
    workspace_id: str, group_id: str, user_id: str, request: Request, current: Current
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).group_member(
            actor.id, workspace_id, group_id, user_id, True
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{workspace_id}/groups/{group_id}/members/{user_id}",
    status_code=204,
    operation_id="removeWorkspaceGroupMember",
)
async def remove_group_member(
    workspace_id: str, group_id: str, user_id: str, request: Request, current: Current
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).group_member(
            actor.id, workspace_id, group_id, user_id, False
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/folders",
    response_model=tuple[Folder, ...],
    operation_id="listWorkspaceFolders",
)
async def list_folders(
    workspace_id: str, request: Request, current: Current, parent_id: str | None = None
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).folders(current[1].id, workspace_id, parent_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post("/{workspace_id}/folders", response_model=Folder, operation_id="createWorkspaceFolder")
async def create_folder(
    workspace_id: str, payload: FolderCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).create_folder(
            actor.id, workspace_id, payload.parent_id, payload.name
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/folders/{folder_id}", response_model=Folder, operation_id="getWorkspaceFolder"
)
async def get_folder(
    workspace_id: str, folder_id: str, request: Request, current: Current
) -> dict[str, Any]:
    try:
        return await workspace_service(request).folder(current[1].id, workspace_id, folder_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/folders/{folder_id}/breadcrumbs",
    response_model=tuple[Folder, ...],
    operation_id="getWorkspaceFolderBreadcrumbs",
)
async def folder_breadcrumbs(
    workspace_id: str, folder_id: str, request: Request, current: Current
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).breadcrumbs(current[1].id, workspace_id, folder_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.patch(
    "/{workspace_id}/folders/{folder_id}",
    response_model=Folder,
    operation_id="renameWorkspaceFolder",
)
async def rename_folder(
    workspace_id: str,
    folder_id: str,
    payload: FolderPatchRequest,
    request: Request,
    current: Current,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    if payload.name is None:
        raise HTTPException(422, "A folder name is required")
    try:
        return await workspace_service(request).rename_folder(
            actor.id, workspace_id, folder_id, payload.name, payload.expected_version
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/folders/{folder_id}/move",
    response_model=Folder,
    operation_id="moveWorkspaceFolder",
)
async def move_folder(
    workspace_id: str,
    folder_id: str,
    payload: FolderMoveRequest,
    request: Request,
    current: Current,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).move_folder(
            actor.id, workspace_id, folder_id, payload.destination_id, payload.expected_version
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/folders/{folder_id}/reorder",
    response_model=Folder,
    operation_id="reorderWorkspaceFolder",
)
async def reorder_folder(
    workspace_id: str,
    folder_id: str,
    payload: FolderReorderRequest,
    request: Request,
    current: Current,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).reorder_folder(
            actor.id,
            workspace_id,
            folder_id,
            payload.order_key,
            payload.expected_version,
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/folders/{folder_id}/trash",
    status_code=204,
    operation_id="trashWorkspaceFolder",
)
async def trash_folder(
    workspace_id: str,
    folder_id: str,
    payload: FolderLifecycleRequest,
    request: Request,
    current: Current,
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).trash_folder(
            actor.id, workspace_id, folder_id, payload.expected_version
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{workspace_id}/folders/{folder_id}/restore",
    status_code=204,
    operation_id="restoreWorkspaceFolder",
)
async def restore_folder(
    workspace_id: str,
    folder_id: str,
    payload: FolderLifecycleRequest,
    request: Request,
    current: Current,
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).restore_folder(
            actor.id, workspace_id, folder_id, payload.expected_version
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{workspace_id}/folders/{folder_id}", status_code=204, operation_id="deleteWorkspaceFolder"
)
async def delete_folder(
    workspace_id: str, folder_id: str, request: Request, current: Current, expected_version: int
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await workspace_service(request).delete_folder(
            actor.id, workspace_id, folder_id, expected_version
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/folders/{folder_id}/acl",
    response_model=FolderAcl,
    operation_id="getWorkspaceFolderAcl",
)
async def get_acl(
    workspace_id: str, folder_id: str, request: Request, current: Current
) -> dict[str, Any]:
    try:
        return await workspace_service(request).acl(current[1].id, workspace_id, folder_id)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.put(
    "/{workspace_id}/folders/{folder_id}/acl",
    response_model=FolderAcl,
    operation_id="replaceWorkspaceFolderAcl",
)
async def replace_acl(
    workspace_id: str,
    folder_id: str,
    payload: AclReplaceRequest,
    request: Request,
    current: Current,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).set_acl(
            actor.id,
            workspace_id,
            folder_id,
            inherit=payload.inherit,
            entries=[entry.model_dump() for entry in payload.entries],
            expected_version=payload.expected_version,
        )
    except (WorkspaceError, ValueError) as exc:
        if isinstance(exc, WorkspaceError):
            raise map_error(exc) from exc
        raise HTTPException(400, str(exc)) from exc


@router.delete(
    "/{workspace_id}/folders/{folder_id}/acl",
    response_model=FolderAcl,
    operation_id="inheritWorkspaceFolderAcl",
)
async def inherit_acl(
    workspace_id: str,
    folder_id: str,
    request: Request,
    current: Current,
    expected_version: int | None = None,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).set_acl(
            actor.id,
            workspace_id,
            folder_id,
            inherit=True,
            entries=[],
            expected_version=expected_version,
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{workspace_id}/acl-subjects",
    response_model=tuple[AclSubject, ...],
    operation_id="searchWorkspaceAclSubjects",
)
async def acl_subjects(
    workspace_id: str, request: Request, current: Current, q: str = ""
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).acl_subjects(current[1].id, workspace_id, q)
    except WorkspaceError as exc:
        raise map_error(exc) from exc


@router.post("/{workspace_id}/permission-preview", operation_id="previewWorkspacePermissions")
async def permission_preview(
    workspace_id: str, payload: PermissionPreviewRequest, request: Request, current: Current
) -> list[dict[str, Any]]:
    try:
        return await workspace_service(request).permission_preview(
            current[1].id, workspace_id, payload.user_id
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc


admin_router = APIRouter(prefix="/admin/workspaces", tags=["platform-admin"])


@admin_router.post("/{workspace_id}/workspace-admin-repair", operation_id="repairWorkspaceAdmin")
async def repair_workspace_admin(
    workspace_id: str, payload: WorkspaceAdminRepairRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await workspace_service(request).repair_admin(
            actor.id, workspace_id, payload.user_id
        )
    except WorkspaceError as exc:
        raise map_error(exc) from exc
