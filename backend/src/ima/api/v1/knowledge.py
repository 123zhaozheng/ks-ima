"""Versioned knowledge tree HTTP adapters."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Query, Request

from ima.api.v1.auth import Current, check_csrf, check_recent_auth
from ima.api.v1.knowledge_contracts import (
    ContentPage,
    DocumentPatchRequest,
    DocumentResponse,
    FileAccessResponse,
    FileVersionPage,
    IngestionStatusResponse,
    KnowledgeCapabilities,
    LifecycleRequest,
    MoveRequest,
    NoteCreateRequest,
    ReplaceFileRequest,
    TagAssignmentRequest,
    TagCreateRequest,
    TagDeleteRequest,
    TagMergeRequest,
    TagPatchRequest,
    TagResponse,
    TrashPage,
    UploadCompleteRequest,
    UploadTicketRequest,
    UploadTicketResponse,
    VersionResponse,
)
from ima.application.knowledge import KnowledgeService
from ima.application.storage import StorageService

router = APIRouter(tags=["knowledge"])


def service(request: Request) -> KnowledgeService:
    return cast(KnowledgeService, request.app.state.knowledge_service)


def storage(request: Request) -> StorageService:
    return cast(StorageService, request.app.state.storage_service)


@router.get(
    "/workspaces/{workspace_id}/knowledge-capabilities",
    response_model=KnowledgeCapabilities,
    operation_id="getKnowledgeCapabilities",
)
async def capabilities(workspace_id: str, request: Request, current: Current) -> dict[str, object]:
    return await storage(request).capabilities(current[1].id, workspace_id)


@router.post(
    "/folders/{folder_id}/files/upload-ticket",
    response_model=UploadTicketResponse,
    operation_id="createFileUploadTicket",
)
async def upload_ticket(
    folder_id: str, payload: UploadTicketRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await storage(request).upload_ticket(
        actor.id,
        folder_id,
        payload.title,
        payload.filename,
        payload.mime_type,
        payload.size_bytes,
        payload.checksum,
    )


@router.post(
    "/documents/{document_id}/file-versions/upload-ticket",
    response_model=UploadTicketResponse,
    operation_id="createFileReplacementUploadTicket",
)
async def replacement_upload_ticket(
    document_id: UUID, payload: ReplaceFileRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await storage(request).replacement_ticket(
        actor.id,
        document_id,
        payload.filename,
        payload.mime_type,
        payload.size_bytes,
        payload.checksum,
        payload.expected_version,
        payload.expected_content_version,
    )


@router.get(
    "/documents/{document_id}/file-versions",
    response_model=FileVersionPage,
    operation_id="listFileVersions",
)
async def file_versions(document_id: UUID, request: Request, current: Current) -> dict[str, object]:
    return await storage(request).file_versions(current[1].id, document_id)


@router.post(
    "/documents/{document_id}/file-versions/complete",
    response_model=IngestionStatusResponse,
    operation_id="completeFileUpload",
)
async def complete_upload(
    document_id: UUID, payload: UploadCompleteRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await storage(request).complete(actor.id, document_id, payload.ticket_id)


@router.get(
    "/documents/{document_id}/file/download",
    response_model=FileAccessResponse,
    operation_id="getFileDownload",
)
async def download_file(document_id: UUID, request: Request, current: Current) -> dict[str, object]:
    return await storage(request).download(current[1].id, document_id)


@router.get(
    "/documents/{document_id}/file/preview",
    response_model=FileAccessResponse,
    operation_id="getFilePreview",
)
async def preview_file(document_id: UUID, request: Request, current: Current) -> dict[str, object]:
    return await storage(request).download(current[1].id, document_id, preview=True)


@router.get(
    "/documents/{document_id}/ingestion",
    response_model=IngestionStatusResponse,
    operation_id="getDocumentIngestion",
)
async def ingestion_status(
    document_id: UUID, request: Request, current: Current
) -> dict[str, object]:
    return await storage(request).status(current[1].id, document_id)


@router.post(
    "/documents/{document_id}/ingestion/retry",
    response_model=IngestionStatusResponse,
    operation_id="retryDocumentIngestion",
)
async def retry_ingestion(
    document_id: UUID, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await storage(request).retry(actor.id, document_id)


@router.post(
    "/documents/{document_id}/ingestion/cancel",
    response_model=IngestionStatusResponse,
    operation_id="cancelDocumentIngestion",
)
async def cancel_ingestion(
    document_id: UUID, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await storage(request).cancel(actor.id, document_id)


@router.get(
    "/folders/{folder_id}/contents", response_model=ContentPage, operation_id="listFolderContents"
)
async def contents(
    folder_id: str,
    request: Request,
    current: Current,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    kind: Annotated[str | None, Query(pattern="^(folder|file|note)$")] = None,
    tag_id: Annotated[UUID | None, Query(alias="tagId")] = None,
) -> dict[str, object]:
    return await service(request).list_contents(
        current[1].id, folder_id, cursor, limit, kind, tag_id
    )


@router.post(
    "/folders/{folder_id}/notes",
    response_model=DocumentResponse,
    operation_id="createKnowledgeNote",
)
async def create_note(
    folder_id: str, payload: NoteCreateRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await service(request).create_note(actor.id, folder_id, payload.title, payload.markdown)


@router.get(
    "/documents/{document_id}", response_model=DocumentResponse, operation_id="getKnowledgeDocument"
)
async def get_document(document_id: UUID, request: Request, current: Current) -> dict[str, object]:
    return await service(request).get_document(current[1].id, document_id)


@router.patch(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    operation_id="updateKnowledgeDocument",
)
async def update_document(
    document_id: UUID, payload: DocumentPatchRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await service(request).patch_document(
        actor.id,
        document_id,
        title=payload.title,
        markdown=payload.markdown,
        expected_version=payload.expected_version,
        expected_content_version=payload.expected_content_version,
    )


@router.post(
    "/documents/{document_id}/move",
    response_model=DocumentResponse,
    operation_id="moveKnowledgeDocument",
)
async def move_document(
    document_id: UUID, payload: MoveRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await service(request).move_document(
        actor.id, document_id, payload.folder_id, payload.expected_version
    )


@router.post(
    "/documents/{document_id}/trash", status_code=204, operation_id="trashKnowledgeDocument"
)
async def trash_document(
    document_id: UUID, payload: LifecycleRequest, request: Request, current: Current
) -> None:
    session, actor = current
    check_csrf(request, session)
    await service(request).trash_document(actor.id, document_id, payload.expected_version)


@router.post(
    "/documents/{document_id}/restore", status_code=204, operation_id="restoreKnowledgeDocument"
)
async def restore_document(
    document_id: UUID, payload: LifecycleRequest, request: Request, current: Current
) -> None:
    session, actor = current
    check_csrf(request, session)
    await service(request).restore_document(
        actor.id, document_id, payload.expected_version, payload.destination_folder_id
    )


@router.delete("/documents/{document_id}", status_code=204, operation_id="deleteKnowledgeDocument")
async def delete_document(document_id: UUID, request: Request, current: Current) -> None:
    session, actor = current
    check_recent_auth(request, session)
    check_csrf(request, session)
    await service(request).delete_document(actor.id, document_id)


@router.get(
    "/documents/{document_id}/versions",
    response_model=tuple[VersionResponse, ...],
    operation_id="listKnowledgeDocumentVersions",
)
async def versions(
    document_id: UUID, request: Request, current: Current
) -> list[dict[str, object]]:
    return await service(request).list_versions(current[1].id, document_id)


@router.get(
    "/documents/{document_id}/versions/{version}",
    response_model=VersionResponse,
    operation_id="getKnowledgeDocumentVersion",
)
async def version(
    document_id: UUID, version: int, request: Request, current: Current
) -> dict[str, object]:
    values = await service(request).list_versions(current[1].id, document_id)
    for item in values:
        if item["version"] == version:
            return item
    from ima.application.knowledge import KnowledgeError

    raise KnowledgeError(404, "VERSION_NOT_FOUND", "Version not found")


@router.post(
    "/documents/{document_id}/versions/{version}/restore",
    response_model=DocumentResponse,
    operation_id="restoreKnowledgeDocumentVersion",
)
async def restore_version(
    document_id: UUID,
    version: int,
    payload: DocumentPatchRequest,
    request: Request,
    current: Current,
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await service(request).restore_version(
        actor.id, document_id, version, payload.expected_version
    )


@router.get(
    "/workspaces/{workspace_id}/tags",
    response_model=tuple[TagResponse, ...],
    operation_id="listKnowledgeTags",
)
async def list_tags(
    workspace_id: str, request: Request, current: Current
) -> list[dict[str, object]]:
    return await service(request).list_tags(current[1].id, workspace_id)


@router.post(
    "/workspaces/{workspace_id}/tags", response_model=TagResponse, operation_id="createKnowledgeTag"
)
async def create_tag(
    workspace_id: str, payload: TagCreateRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_recent_auth(request, session)
    check_csrf(request, session)
    return await service(request).create_tag(actor.id, workspace_id, payload.name)


@router.patch(
    "/workspaces/{workspace_id}/tags/{tag_id}",
    response_model=TagResponse,
    operation_id="updateKnowledgeTag",
)
async def update_tag(
    workspace_id: str, tag_id: UUID, payload: TagPatchRequest, request: Request, current: Current
) -> dict[str, object]:
    session, actor = current
    check_recent_auth(request, session)
    check_csrf(request, session)
    return await service(request).patch_tag(
        actor.id, workspace_id, tag_id, payload.name, payload.expected_version
    )


@router.delete(
    "/workspaces/{workspace_id}/tags/{tag_id}", status_code=204, operation_id="deleteKnowledgeTag"
)
async def delete_tag(
    workspace_id: str, tag_id: UUID, payload: TagDeleteRequest, request: Request, current: Current
) -> None:
    session, actor = current
    check_recent_auth(request, session)
    check_csrf(request, session)
    await service(request).delete_tag(actor.id, workspace_id, tag_id, payload.expected_version)


@router.post(
    "/workspaces/{workspace_id}/tags/{tag_id}/merge",
    status_code=204,
    operation_id="mergeKnowledgeTag",
)
async def merge_tag(
    workspace_id: str, tag_id: UUID, payload: TagMergeRequest, request: Request, current: Current
) -> None:
    session, actor = current
    check_recent_auth(request, session)
    check_csrf(request, session)
    await service(request).merge_tag(
        actor.id,
        workspace_id,
        tag_id,
        payload.target_tag_id,
        payload.expected_version,
        payload.expected_target_version,
    )


@router.put(
    "/documents/{document_id}/tags", status_code=204, operation_id="replaceKnowledgeDocumentTags"
)
async def replace_tags(
    document_id: UUID, payload: TagAssignmentRequest, request: Request, current: Current
) -> None:
    session, actor = current
    check_csrf(request, session)
    await service(request).assign_tags(actor.id, document_id, payload.tag_ids)


@router.get(
    "/workspaces/{workspace_id}/trash", response_model=TrashPage, operation_id="listKnowledgeTrash"
)
async def trash(
    workspace_id: str,
    request: Request,
    current: Current,
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict[str, object]:
    return await service(request).list_trash(current[1].id, workspace_id, cursor, limit)
