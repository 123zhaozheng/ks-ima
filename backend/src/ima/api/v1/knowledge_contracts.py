"""OpenAPI DTOs for the versioned knowledge tree."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from ima.api.contracts import ContractModel


class Capability(ContractModel):
    status: Literal["available", "unavailable"]
    reason: str | None = None


class KnowledgeCapabilities(ContractModel):
    upload: Capability
    download: Capability
    preview: Capability


class ContentRow(ContractModel):
    id: str
    kind: Literal["folder", "file", "note"]
    title: str
    order_key: int = Field(alias="orderKey")
    version: int
    lifecycle: Literal["active", "trashed"]
    file_state: Literal["pending", "ready", "failed"] | None = Field(
        default=None, alias="fileState"
    )
    metadata: dict[str, object] | None = None


class ContentPage(ContractModel):
    items: tuple[ContentRow, ...]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
    children_version: int = Field(alias="childrenVersion")


class NoteCreateRequest(ContractModel):
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(max_length=1_000_000)


class DocumentPatchRequest(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    markdown: str | None = Field(default=None, max_length=1_000_000)
    expected_version: int = Field(alias="expectedVersion", gt=0)
    expected_content_version: int | None = Field(default=None, alias="expectedContentVersion", gt=0)


class MoveRequest(ContractModel):
    folder_id: str = Field(alias="folderId", min_length=1, max_length=32)
    expected_version: int = Field(alias="expectedVersion", gt=0)


class LifecycleRequest(ContractModel):
    expected_version: int = Field(alias="expectedVersion", gt=0)
    destination_folder_id: str | None = Field(default=None, alias="destinationFolderId")


class DocumentResponse(ContractModel):
    id: UUID
    workspace_id: str = Field(alias="workspaceId")
    folder_id: str = Field(alias="folderId")
    kind: Literal["file", "note"]
    title: str
    version: int
    current_content_version: int | None = Field(default=None, alias="currentContentVersion")
    lifecycle: Literal["active", "trashed"]
    markdown: str | None = None
    file_state: Literal["pending", "ready", "failed"] = Field(alias="fileState")
    metadata: dict[str, object]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class VersionResponse(ContractModel):
    document_id: UUID = Field(alias="documentId")
    version: int
    kind: Literal["file", "note"]
    markdown: str | None = None
    digest: str
    created_at: datetime = Field(alias="createdAt")


class TagResponse(ContractModel):
    id: UUID
    name: str
    version: int
    count: int = 0


class TagCreateRequest(ContractModel):
    name: str = Field(min_length=1, max_length=120)


class TagPatchRequest(ContractModel):
    name: str = Field(min_length=1, max_length=120)
    expected_version: int = Field(alias="expectedVersion", gt=0)


class TagDeleteRequest(ContractModel):
    expected_version: int = Field(alias="expectedVersion", gt=0)


class TagMergeRequest(ContractModel):
    target_tag_id: UUID = Field(alias="targetTagId")
    expected_version: int = Field(alias="expectedVersion", gt=0)
    expected_target_version: int = Field(alias="expectedTargetVersion", gt=0)


class TagAssignmentRequest(ContractModel):
    tag_ids: tuple[UUID, ...] = Field(alias="tagIds")


class TrashPage(ContractModel):
    items: tuple[ContentRow, ...]
    next_cursor: str | None = Field(default=None, alias="nextCursor")
