"""Generated OpenAPI source contracts for workspace authorization."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ima.api.v1.identity_contracts import IdentityModel

WorkspaceRoleLiteral = Literal["workspace_admin", "knowledge_manager", "editor", "viewer"]
MembershipStateLiteral = Literal["active", "invited", "disabled"]
AclActionLiteral = Literal[
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


class WorkspaceMember(IdentityModel):
    workspace_id: str = Field(alias="workspaceId")
    user_id: str = Field(alias="userId")
    role: WorkspaceRoleLiteral
    state: MembershipStateLiteral
    version: int
    joined_at: datetime | None = Field(default=None, alias="joinedAt")
    disabled_at: datetime | None = Field(default=None, alias="disabledAt")
    email: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    is_active: bool | None = Field(default=None, alias="isActive")


class MemberWorkspace(IdentityModel):
    id: str
    name: str
    is_active: bool = Field(alias="isActive")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    role: WorkspaceRoleLiteral


class MemberAddRequest(IdentityModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=64)
    role: WorkspaceRoleLiteral = "viewer"


class MemberPatchRequest(IdentityModel):
    role: WorkspaceRoleLiteral | None = None
    state: MembershipStateLiteral | None = None
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class WorkspaceGroup(IdentityModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    name: str
    version: int
    member_count: int = Field(alias="memberCount")


class GroupCreateRequest(IdentityModel):
    name: str = Field(min_length=1, max_length=120)


class GroupDeleteRequest(IdentityModel):
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class InvitationCreateRequest(IdentityModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=64)
    role: WorkspaceRoleLiteral = "viewer"


class Invitation(IdentityModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    user_id: str = Field(alias="userId")
    role: WorkspaceRoleLiteral
    delivery: Literal["manual", "sent"] | None = None
    expires_at: datetime = Field(alias="expiresAt")
    accepted_at: datetime | None = Field(default=None, alias="acceptedAt")
    revoked_at: datetime | None = Field(default=None, alias="revokedAt")
    bound_link: str | None = Field(default=None, alias="boundLink")


class InvitationAcceptRequest(IdentityModel):
    token: str = Field(min_length=16, max_length=256)


class Folder(IdentityModel):
    id: str
    workspace_id: str = Field(alias="workspaceId")
    parent_id: str | None = Field(default=None, alias="parentId")
    name: str
    order_key: int = Field(alias="orderKey")
    lifecycle: Literal["active", "trashed"]
    version: int
    is_root: bool = Field(alias="isRoot")
    acl_anchor_id: str = Field(alias="aclAnchorId")


class FolderCreateRequest(IdentityModel):
    parent_id: str = Field(alias="parentId", min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)


class FolderPatchRequest(IdentityModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class FolderMoveRequest(IdentityModel):
    destination_id: str = Field(alias="destinationId", min_length=1, max_length=64)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class FolderReorderRequest(IdentityModel):
    order_key: int = Field(alias="orderKey", ge=0, le=2_000_000_000)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class FolderLifecycleRequest(IdentityModel):
    expected_version: int = Field(alias="expectedVersion", ge=1)


class AclEntry(IdentityModel):
    subject_type: Literal["role", "group", "user"] = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId", min_length=1, max_length=128)
    action: AclActionLiteral


class AclReplaceRequest(IdentityModel):
    inherit: bool = False
    entries: tuple[AclEntry, ...] = Field(default=(), max_length=500)
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class FolderAcl(IdentityModel):
    folder_id: str = Field(alias="folderId")
    inherited: bool
    effective_source: str = Field(alias="effectiveSource")
    version: int
    entries: tuple[AclEntry, ...]


class PermissionPreviewRequest(IdentityModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=64)


class UserSearchResult(IdentityModel):
    id: str
    email: str
    display_name: str = Field(alias="displayName")


class AclSubject(IdentityModel):
    subject_type: Literal["role", "group", "user"] = Field(alias="subjectType")
    subject_id: str = Field(alias="subjectId")
    label: str
    email: str | None = None


class WorkspaceAdminRepairRequest(IdentityModel):
    user_id: str = Field(alias="userId", min_length=1, max_length=64)
