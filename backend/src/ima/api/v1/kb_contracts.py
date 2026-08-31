"""Generated OpenAPI source contracts for knowledge base authorization."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ima.api.v1.identity_contracts import IdentityModel

KbRoleLiteral = Literal["owner", "editor", "viewer"]
ShareRoleLiteral = Literal["editor", "viewer"]
MembershipStateLiteral = Literal["active"]


class KnowledgeBaseCreateRequest(IdentityModel):
    name: str = Field(min_length=1, max_length=200)


class KnowledgeBaseRenameRequest(IdentityModel):
    name: str = Field(min_length=1, max_length=200)


class KnowledgeBase(IdentityModel):
    id: str
    name: str
    is_active: bool = Field(alias="isActive")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    role: KbRoleLiteral
    owned: bool = False


class KbMember(IdentityModel):
    kb_id: str = Field(alias="kbId")
    user_id: str = Field(alias="userId")
    role: KbRoleLiteral
    state: MembershipStateLiteral
    version: int
    joined_at: datetime | None = Field(default=None, alias="joinedAt")
    email: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    is_active: bool | None = Field(default=None, alias="isActive")


class MemberRolePatchRequest(IdentityModel):
    role: ShareRoleLiteral
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class ShareLinkCreateRequest(IdentityModel):
    role: ShareRoleLiteral = "viewer"
    expires_in_days: int | None = Field(default=None, alias="expiresInDays", ge=1, le=365)


class ShareLink(IdentityModel):
    id: str
    kb_id: str = Field(alias="kbId")
    # The share URL is only returned once, at creation time; the stored
    # token digest cannot be reversed into the link again.
    url: str | None = None
    role: ShareRoleLiteral
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    revoked_at: datetime | None = Field(default=None, alias="revokedAt")
    created_at: datetime = Field(alias="createdAt")


class Folder(IdentityModel):
    id: str
    kb_id: str = Field(alias="kbId")
    parent_id: str | None = Field(default=None, alias="parentId")
    name: str
    order_key: int = Field(alias="orderKey")
    lifecycle: Literal["active"]
    version: int
    is_root: bool = Field(alias="isRoot")


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
