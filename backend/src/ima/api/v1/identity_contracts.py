"""Identity and platform API DTOs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from ima.application.contracts import IdentityUser as IdentityUser


class IdentityModel(BaseModel):
    model_config = ConfigDict(alias_generator=None, populate_by_name=True, extra="forbid")


class SignInRequest(IdentityModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class SignInResponse(IdentityModel):
    status: Literal["authenticated", "totp_required"]
    challenge: str | None = None
    user: IdentityUser | None = None


class TotpVerifyRequest(IdentityModel):
    challenge: str | None = None
    code: str = Field(min_length=6, max_length=16)


class RecoveryVerifyRequest(IdentityModel):
    challenge: str
    code: str = Field(min_length=8, max_length=32)


class RegisterRequest(IdentityModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200, alias="displayName")


class AcceptTokenRequest(IdentityModel):
    token: str = Field(min_length=16, max_length=256)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str | None = Field(default=None, alias="displayName", max_length=200)


class PasswordForgotRequest(IdentityModel):
    email: EmailStr


class PasswordResetRequest(IdentityModel):
    token: str = Field(min_length=16, max_length=256)
    password: str = Field(min_length=12, max_length=1024)


class AuthCapabilities(IdentityModel):
    registration: bool


class PasswordChangeRequest(IdentityModel):
    current_password: str = Field(alias="currentPassword", min_length=1, max_length=1024)
    password: str = Field(min_length=12, max_length=1024)


class SessionInfo(IdentityModel):
    id: UUID
    created_at: datetime = Field(alias="createdAt")
    last_activity_at: datetime = Field(alias="lastActivityAt")
    expires_at: datetime = Field(alias="expiresAt")
    current: bool
    user_agent: str | None = Field(default=None, alias="userAgent")


class SessionList(IdentityModel):
    items: tuple[SessionInfo, ...]


class KnowledgeBaseInfo(IdentityModel):
    id: str
    name: str
    is_active: bool = Field(alias="isActive")
    archived_at: datetime | None = Field(default=None, alias="archivedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class KnowledgeBaseCreateResponse(IdentityModel):
    id: str
    name: str
    is_active: bool = Field(alias="isActive")


class KnowledgeBaseList(IdentityModel):
    items: tuple[KnowledgeBaseInfo, ...]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class AdminUserList(IdentityModel):
    items: tuple[IdentityUser, ...]
    next_cursor: str | None = Field(default=None, alias="nextCursor")


class AdminUserDetail(IdentityModel):
    id: str
    email: str
    display_name: str = Field(alias="displayName")
    image_url: str | None = Field(default=None, alias="imageUrl")
    is_active: bool = Field(alias="isActive")
    password_reset_required: bool = Field(alias="passwordResetRequired")
    disabled_at: datetime | None = Field(default=None, alias="disabledAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    platform_roles: tuple[str, ...] = Field(default=(), alias="platformRoles")


class AdminCreateUserResponse(IdentityModel):
    user: IdentityUser
    invite_sent: bool = Field(alias="inviteSent")
    temporary_password_set: bool = Field(alias="temporaryPasswordSet")


class PlatformSettings(IdentityModel):
    allow_registration: bool = Field(alias="allowRegistration")
    smtp_enabled: bool = Field(alias="smtpEnabled")
    session_idle_seconds: int = Field(alias="sessionIdleSeconds")
    session_absolute_seconds: int = Field(alias="sessionAbsoluteSeconds")
    recent_auth_seconds: int = Field(alias="recentAuthSeconds")
    updated_at: datetime = Field(alias="updatedAt")


class ProfilePatch(IdentityModel):
    display_name: str | None = Field(default=None, alias="displayName", max_length=200)
    image_url: str | None = Field(default=None, alias="imageUrl", max_length=2048)


class CreateUserRequest(IdentityModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200, alias="displayName")
    temporary_password: str | None = Field(
        default=None, alias="temporaryPassword", min_length=12, max_length=1024
    )
    send_invite: bool = Field(default=True, alias="sendInvite")


class UserPatch(IdentityModel):
    display_name: str | None = Field(default=None, alias="displayName", max_length=200)
    email: EmailStr | None = None


class RoleRequest(IdentityModel):
    role: Literal["super_admin", "platform_admin", "security_auditor"]


class KnowledgeBaseRequest(IdentityModel):
    name: str = Field(min_length=1, max_length=200)
    initial_owner_user_id: str = Field(alias="initialOwnerUserId", min_length=1, max_length=64)


class SettingPatch(IdentityModel):
    allow_registration: bool | None = Field(default=None, alias="allowRegistration")
    session_idle_seconds: int | None = Field(
        default=None, alias="sessionIdleSeconds", ge=300, le=2592000
    )
    session_absolute_seconds: int | None = Field(
        default=None, alias="sessionAbsoluteSeconds", ge=3600, le=31536000
    )
    recent_auth_seconds: int | None = Field(
        default=None, alias="recentAuthSeconds", ge=60, le=86400
    )


class AuditEvent(IdentityModel):
    id: int
    actor_id: str | None = Field(default=None, alias="actorId")
    action: str
    target_type: str | None = Field(default=None, alias="targetType")
    target_id: str | None = Field(default=None, alias="targetId")
    result: str
    reason_code: str | None = Field(default=None, alias="reasonCode")
    metadata: dict[str, object]
    correlation_id: str | None = Field(default=None, alias="correlationId")
    created_at: datetime = Field(alias="createdAt")


class AuditEventList(IdentityModel):
    items: tuple[AuditEvent, ...]
