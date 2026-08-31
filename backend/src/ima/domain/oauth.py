"""Transport-independent OAuth/MCP record contracts.

These dataclasses model the durable rows owned by the OAuth and service-principal
repositories.  They carry no SQLAlchemy or FastAPI imports; repository and
service layers translate them.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from ipaddress import ip_network
from uuid import UUID


class GrantState(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class PrincipalState(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


class ClientType(StrEnum):
    PUBLIC = "public"
    CONFIDENTIAL = "confidential"


class ClientApplicationType(StrEnum):
    NATIVE = "native"
    WEB = "web"


class TokenAuthMethod(StrEnum):
    NONE = "none"
    CLIENT_SECRET_BASIC = "client_secret_basic"


class RateBucketKind(StrEnum):
    TOKEN = "token"
    TOOL = "tool"
    SERVICE = "service"
    AUTHORIZE = "authorize"
    SOURCE = "source"


class ClientRecord:
    """Pre-registered MCP client + its exact redirect URIs."""

    def __init__(
        self,
        id: UUID,
        client_id: str,
        client_name: str,
        client_type: ClientType,
        token_endpoint_auth_method: TokenAuthMethod,
        client_secret_digest: str | None,
        application_type: ClientApplicationType,
        canonical_resource: str,
        is_enabled: bool,
        redirect_uris: tuple[str, ...] = (),
        **_: object,
    ) -> None:
        self.id = id
        self.client_id = client_id
        self.client_name = client_name
        self.client_type = client_type
        self.token_endpoint_auth_method = token_endpoint_auth_method
        self.client_secret_digest = client_secret_digest
        self.application_type = application_type
        self.canonical_resource = canonical_resource
        self.is_enabled = is_enabled
        self.redirect_uris = redirect_uris


class GrantRecord:
    """A persisted human authorization grant; user-level (kb_id null)."""

    def __init__(
        self,
        id: UUID,
        user_id: str,
        client_id: UUID,
        canonical_resource: str,
        scopes: tuple[str, ...],
        state: GrantState,
        expires_at: datetime,
        kb_id: str | None = None,
        **_: object,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.client_id = client_id
        self.canonical_resource = canonical_resource
        self.kb_id = kb_id
        self.scopes = scopes
        self.state = state
        self.expires_at = expires_at


class AuthorizationCodeRecord:
    """A one-time authorization code bound to a grant and PKCE challenge."""

    def __init__(
        self,
        id: UUID,
        grant_id: UUID,
        user_id: str,
        client_id: UUID,
        redirect_uri: str,
        canonical_resource: str,
        scopes: tuple[str, ...],
        code_challenge: str,
        expires_at: datetime,
        state: str,
        **_: object,
    ) -> None:
        self.id = id
        self.grant_id = grant_id
        self.user_id = user_id
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.canonical_resource = canonical_resource
        self.scopes = scopes
        self.code_challenge = code_challenge
        self.expires_at = expires_at
        self.state = state


class AccessTokenRecord:
    """A short-lived opaque access token bound to a grant or principal."""

    def __init__(
        self,
        id: UUID,
        token_digest: str,
        grant_id: UUID | None,
        principal_id: UUID | None,
        client_id: UUID | None,
        canonical_resource: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        security_stamp: str | None = None,
        **_: object,
    ) -> None:
        self.id = id
        self.token_digest = token_digest
        self.grant_id = grant_id
        self.principal_id = principal_id
        self.client_id = client_id
        self.canonical_resource = canonical_resource
        self.scopes = scopes
        self.expires_at = expires_at
        self.security_stamp = security_stamp


class RefreshTokenRecord:
    """A single rotated refresh token in a family lineage."""

    def __init__(
        self,
        id: UUID,
        family_id: UUID,
        grant_id: UUID,
        client_id: UUID,
        canonical_resource: str,
        scopes: tuple[str, ...],
        token_digest: str,
        expires_at: datetime,
        replaced_at: datetime | None = None,
        replaced_by: UUID | None = None,
        **_: object,
    ) -> None:
        self.id = id
        self.family_id = family_id
        self.grant_id = grant_id
        self.client_id = client_id
        self.canonical_resource = canonical_resource
        self.scopes = scopes
        self.token_digest = token_digest
        self.expires_at = expires_at
        self.replaced_at = replaced_at
        self.replaced_by = replaced_by


class AuthorizationTokenBundle:
    """One atomically committed authorization-code token bundle."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        access: AccessTokenRecord,
        refresh: RefreshTokenRecord,
        code: AuthorizationCodeRecord,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access = access
        self.refresh = refresh
        self.code = code


class RefreshAccessTokenBundle:
    """One atomically committed refresh rotation and access-token issue."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        access: AccessTokenRecord,
        refresh: RefreshTokenRecord,
        grant: GrantRecord,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.access = access
        self.refresh = refresh
        self.grant = grant


class ServicePrincipalRecord:
    """A user-level delegated principal for unattended agents."""

    def __init__(
        self,
        id: UUID,
        display_name: str,
        purpose: str,
        owner_user_id: str,
        scopes: tuple[str, ...],
        state: PrincipalState,
        expires_at: datetime,
        rate_limit: int,
        concurrency_limit: int,
        cidr_allowlist: tuple[str, ...] = (),
        **_: object,
    ) -> None:
        self.id = id
        self.display_name = display_name
        self.purpose = purpose
        self.owner_user_id = owner_user_id
        self.scopes = scopes
        self.state = state
        self.expires_at = expires_at
        self.rate_limit = rate_limit
        self.concurrency_limit = concurrency_limit
        self.cidr_allowlist = tuple(cidr_allowlist)


class CredentialRecord:
    """A single service-principal credential: ID, pepper digest, lifecycle."""

    def __init__(
        self,
        id: UUID,
        principal_id: UUID,
        credential_id: str,
        digest: str,
        secret_prefix: str,
        expires_at: datetime,
        created_at: datetime,
        revoked_at: datetime | None = None,
        revoke_reason: str | None = None,
        last_used_at: datetime | None = None,
        replaced_by: UUID | None = None,
        **_: object,
    ) -> None:
        self.id = id
        self.principal_id = principal_id
        self.credential_id = credential_id
        self.digest = digest
        self.secret_prefix = secret_prefix
        self.expires_at = expires_at
        self.created_at = created_at
        self.revoked_at = revoked_at
        self.revoke_reason = revoke_reason
        self.last_used_at = last_used_at
        self.replaced_by = replaced_by


def normalize_cidr_allowlist(values: tuple[str, ...]) -> tuple[str, ...]:
    """Validate service-principal CIDR allowlist strings and dedupe preserving order."""
    seen: list[str] = []
    for value in values:
        network = ip_network(value, strict=False)
        normalized = str(network)
        if normalized not in seen:
            seen.append(normalized)
    return tuple(seen)
