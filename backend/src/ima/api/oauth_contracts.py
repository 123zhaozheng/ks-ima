"""Public OAuth consent and service-principal HTTP contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

BoundedScope = Annotated[str, StringConstraints(min_length=1, max_length=64)]
BoundedCidr = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class ConsentView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    client_id: str = Field(alias="clientId")
    client_name: str = Field(alias="clientName")
    redirect_uri: str = Field(alias="redirectUri")
    resource: str
    scopes: tuple[str, ...]
    write_access: bool = Field(alias="writeAccess")
    expires_at: datetime = Field(alias="expiresAt")
    refresh_enabled: bool = Field(default=True, alias="refreshEnabled")
    consent_required: bool = Field(alias="consentRequired")


class ConsentSubmit(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    approved: bool
    client_id: str = Field(alias="clientId", min_length=1, max_length=128)
    redirect_uri: str = Field(alias="redirectUri", min_length=1, max_length=512)
    resource: str = Field(min_length=1, max_length=512)
    scope: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=128)
    code_challenge: str = Field(alias="codeChallenge", min_length=43, max_length=43, repr=False)
    code_challenge_method: Literal["S256"] = Field(alias="codeChallengeMethod")
    expires_at: datetime = Field(alias="expiresAt")


class ServicePrincipalCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)
    owner_user_id: str = Field(alias="ownerUserId", min_length=1, max_length=32)
    scopes: tuple[BoundedScope, ...] = Field(min_length=1, max_length=5)
    expires_at: datetime = Field(alias="expiresAt")
    rate_limit: int = Field(default=300, alias="rateLimit", ge=1)
    concurrency_limit: int = Field(default=10, alias="concurrencyLimit", ge=1)
    cidr_allowlist: tuple[BoundedCidr, ...] = Field(
        default=(), alias="cidrAllowlist", max_length=32
    )


class CredentialViewResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    principal_id: UUID = Field(alias="principalId")
    credential_id: str = Field(alias="credentialId")
    secret_prefix: str = Field(alias="secretPrefix")
    expires_at: datetime = Field(alias="expiresAt")
    created_at: datetime = Field(alias="createdAt")
    revoked_at: datetime | None = Field(alias="revokedAt")
    last_used_at: datetime | None = Field(alias="lastUsedAt")


class ServicePrincipalResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    display_name: str = Field(alias="displayName")
    purpose: str
    owner_user_id: str = Field(alias="ownerUserId")
    scopes: tuple[str, ...]
    state: str
    expires_at: datetime = Field(alias="expiresAt")
    rate_limit: int = Field(alias="rateLimit")
    concurrency_limit: int = Field(alias="concurrencyLimit")
    cidr_allowlist: tuple[str, ...] = Field(alias="cidrAllowlist")


class ServicePrincipalDetailResponse(ServicePrincipalResponse):
    credentials: tuple[CredentialViewResponse, ...] = ()


class ConnectedGrantResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: UUID
    client_name: str = Field(alias="clientName")
    scopes: tuple[str, ...]
    expires_at: datetime = Field(alias="expiresAt")


class CredentialIssueResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    secret: str = Field(repr=False)
    credential: CredentialViewResponse
    principal: ServicePrincipalResponse


class CredentialRotate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    expires_at: datetime = Field(alias="expiresAt")
    overlap_expires_at: datetime | None = Field(default=None, alias="overlapExpiresAt")


class LifecycleResult(BaseModel):
    revoked: bool = True
