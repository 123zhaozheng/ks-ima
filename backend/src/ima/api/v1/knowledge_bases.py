"""Knowledge base membership, folder tree, and share link HTTP adapters."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request

from ima.api.v1.auth import Current, check_csrf
from ima.api.v1.identity_contracts import KnowledgeBaseCreateResponse
from ima.api.v1.kb_contracts import (
    Folder,
    FolderCreateRequest,
    FolderMoveRequest,
    FolderPatchRequest,
    FolderReorderRequest,
    KbMember,
    KnowledgeBase,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseRenameRequest,
    MemberRolePatchRequest,
    ShareLink,
    ShareLinkCreateRequest,
)
from ima.application.authorization import KbError, KbService

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def kb_service(request: Request) -> KbService:
    return cast(KbService, request.app.state.kb_service)


def map_error(exc: KbError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("", operation_id="listKnowledgeBases")
async def list_knowledge_bases(request: Request, current: Current) -> list[dict[str, Any]]:
    try:
        return await kb_service(request).list_knowledge_bases(current[1].id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.post("", response_model=KnowledgeBaseCreateResponse, operation_id="createKnowledgeBase")
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest, request: Request, current: Current
) -> KnowledgeBaseCreateResponse:
    session, actor = current
    check_csrf(request, session)
    try:
        knowledge_base = await kb_service(request).create_knowledge_base(actor.id, payload.name)
    except KbError as exc:
        raise map_error(exc) from exc
    return KnowledgeBaseCreateResponse(
        id=knowledge_base["id"], name=knowledge_base["name"], isActive=True
    )


@router.get("/{kb_id}", response_model=KnowledgeBase, operation_id="getKnowledgeBase")
async def get_knowledge_base(kb_id: str, request: Request, current: Current) -> dict[str, Any]:
    try:
        return await kb_service(request).get_knowledge_base(current[1].id, kb_id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.patch("/{kb_id}", response_model=KnowledgeBase, operation_id="renameKnowledgeBase")
async def rename_knowledge_base(
    kb_id: str, payload: KnowledgeBaseRenameRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).rename_knowledge_base(actor.id, kb_id, payload.name)
    except KbError as exc:
        raise map_error(exc) from exc


@router.post("/{kb_id}/archive", operation_id="archiveKnowledgeBase")
async def archive_knowledge_base(kb_id: str, request: Request, current: Current) -> dict[str, bool]:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).archive_knowledge_base(actor.id, kb_id)
    except KbError as exc:
        raise map_error(exc) from exc
    return {"archived": True}


@router.post("/{kb_id}/restore", operation_id="restoreKnowledgeBase")
async def restore_knowledge_base(kb_id: str, request: Request, current: Current) -> dict[str, bool]:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).restore_knowledge_base(actor.id, kb_id)
    except KbError as exc:
        raise map_error(exc) from exc
    return {"restored": True}


@router.delete("/{kb_id}", operation_id="deleteKnowledgeBase")
async def delete_knowledge_base(kb_id: str, request: Request, current: Current) -> dict[str, bool]:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).delete_archived_knowledge_base(actor.id, kb_id)
    except KbError as exc:
        raise map_error(exc) from exc
    return {"deleted": True}


@router.get(
    "/{kb_id}/members",
    response_model=tuple[KbMember, ...],
    operation_id="listKnowledgeBaseMembers",
)
async def list_members(
    kb_id: str, request: Request, current: Current, q: str = ""
) -> list[dict[str, Any]]:
    try:
        return await kb_service(request).list_members(current[1].id, kb_id, q)
    except KbError as exc:
        raise map_error(exc) from exc


@router.patch(
    "/{kb_id}/members/{user_id}",
    response_model=KbMember,
    operation_id="updateKnowledgeBaseMemberRole",
)
async def update_member_role(
    kb_id: str, user_id: str, payload: MemberRolePatchRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).update_member_role(
            actor.id, kb_id, user_id, payload.role, payload.expected_version
        )
    except KbError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{kb_id}/members/{user_id}", status_code=204, operation_id="removeKnowledgeBaseMember"
)
async def remove_member(
    kb_id: str,
    user_id: str,
    request: Request,
    current: Current,
    expected_version: int | None = None,
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).remove_member(actor.id, kb_id, user_id, expected_version)
    except KbError as exc:
        raise map_error(exc) from exc


@router.post("/{kb_id}/leave", status_code=204, operation_id="leaveKnowledgeBase")
async def leave_knowledge_base(kb_id: str, request: Request, current: Current) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).leave_knowledge_base(actor.id, kb_id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{kb_id}/share-links",
    response_model=tuple[ShareLink, ...],
    operation_id="listKnowledgeBaseShareLinks",
)
async def list_share_links(kb_id: str, request: Request, current: Current) -> list[dict[str, Any]]:
    try:
        return await kb_service(request).list_share_links(current[1].id, kb_id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{kb_id}/share-links", response_model=ShareLink, operation_id="createKnowledgeBaseShareLink"
)
async def create_share_link(
    kb_id: str, payload: ShareLinkCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).create_share_link(
            actor.id, kb_id, payload.role, expires_in_days=payload.expires_in_days
        )
    except KbError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{kb_id}/share-links/{link_id}", status_code=204, operation_id="revokeKnowledgeBaseShareLink"
)
async def revoke_share_link(kb_id: str, link_id: str, request: Request, current: Current) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).revoke_share_link(actor.id, kb_id, link_id)
    except KbError as exc:
        raise map_error(exc) from exc


share_router = APIRouter(prefix="/kb-share-links", tags=["knowledge-bases"])


@share_router.post("/{token}/accept", operation_id="acceptKbShareLink")
async def accept_share_link(token: str, request: Request, current: Current) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).accept_share_link(actor.id, token)
    except KbError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{kb_id}/folders",
    response_model=tuple[Folder, ...],
    operation_id="listKnowledgeBaseFolders",
)
async def list_folders(
    kb_id: str, request: Request, current: Current, parent_id: str | None = None
) -> list[dict[str, Any]]:
    try:
        return await kb_service(request).folders(current[1].id, kb_id, parent_id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.post("/{kb_id}/folders", response_model=Folder, operation_id="createKnowledgeBaseFolder")
async def create_folder(
    kb_id: str, payload: FolderCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).create_folder(
            actor.id, kb_id, payload.parent_id, payload.name
        )
    except KbError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{kb_id}/folders/{folder_id}", response_model=Folder, operation_id="getKnowledgeBaseFolder"
)
async def get_folder(
    kb_id: str, folder_id: str, request: Request, current: Current
) -> dict[str, Any]:
    try:
        return await kb_service(request).folder(current[1].id, kb_id, folder_id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.get(
    "/{kb_id}/folders/{folder_id}/breadcrumbs",
    response_model=tuple[Folder, ...],
    operation_id="getKnowledgeBaseFolderBreadcrumbs",
)
async def folder_breadcrumbs(
    kb_id: str, folder_id: str, request: Request, current: Current
) -> list[dict[str, Any]]:
    try:
        return await kb_service(request).breadcrumbs(current[1].id, kb_id, folder_id)
    except KbError as exc:
        raise map_error(exc) from exc


@router.patch(
    "/{kb_id}/folders/{folder_id}",
    response_model=Folder,
    operation_id="renameKnowledgeBaseFolder",
)
async def rename_folder(
    kb_id: str,
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
        return await kb_service(request).rename_folder(
            actor.id, kb_id, folder_id, payload.name, payload.expected_version
        )
    except KbError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{kb_id}/folders/{folder_id}/move",
    response_model=Folder,
    operation_id="moveKnowledgeBaseFolder",
)
async def move_folder(
    kb_id: str,
    folder_id: str,
    payload: FolderMoveRequest,
    request: Request,
    current: Current,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).move_folder(
            actor.id, kb_id, folder_id, payload.destination_id, payload.expected_version
        )
    except KbError as exc:
        raise map_error(exc) from exc


@router.post(
    "/{kb_id}/folders/{folder_id}/reorder",
    response_model=Folder,
    operation_id="reorderKnowledgeBaseFolder",
)
async def reorder_folder(
    kb_id: str,
    folder_id: str,
    payload: FolderReorderRequest,
    request: Request,
    current: Current,
) -> dict[str, Any]:
    session, actor = current
    check_csrf(request, session)
    try:
        return await kb_service(request).reorder_folder(
            actor.id,
            kb_id,
            folder_id,
            payload.order_key,
            payload.expected_version,
        )
    except KbError as exc:
        raise map_error(exc) from exc


@router.delete(
    "/{kb_id}/folders/{folder_id}", status_code=204, operation_id="deleteKnowledgeBaseFolder"
)
async def delete_folder(
    kb_id: str, folder_id: str, request: Request, current: Current, expected_version: int
) -> None:
    session, actor = current
    check_csrf(request, session)
    try:
        await kb_service(request).delete_folder(actor.id, kb_id, folder_id, expected_version)
    except KbError as exc:
        raise map_error(exc) from exc
