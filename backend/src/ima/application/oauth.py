"""Transport-neutral OAuth and MCP service-principal application services."""

from __future__ import annotations

import hmac
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit
from uuid import UUID

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.identity import IdentityService
from ima.application.mcp_contracts import (
    KNOWN_TOOLS,
    OAUTH_MAPPING,
    McpActor,
    OAuthErrorCode,
    parse_scopes,
    pkce_s256,
)
from ima.config import Settings
from ima.domain.authorization import AclAction
from ima.domain.oauth import ClientRecord, CredentialRecord, GrantRecord, ServicePrincipalRecord
from ima.infrastructure.oauth import McpOauthRepository, McpRepositoryError

PKCE_CHALLENGE_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")
SERVICE_PRINCIPAL_SCOPES = frozenset(
    {
        "mcp:workspaces:read",
        "mcp:knowledge:read",
        "mcp:knowledge:search",
    }
)

TOOL_ACL_ACTION: dict[str, AclAction] = {
    "kb_list_dir": AclAction.VIEW_METADATA,
    "kb_get_tree": AclAction.VIEW_METADATA,
    "kb_get_note": AclAction.VIEW_CONTENT,
    "kb_get_file": AclAction.DOWNLOAD,
    "kb_list_tags": AclAction.VIEW_METADATA,
    "kb_search": AclAction.VIEW_CONTENT,
    "kb_ask": AclAction.ASK,
    "kb_mkdir": AclAction.CREATE_CHILD,
    "kb_create_note": AclAction.CREATE_CHILD,
    "kb_update_note": AclAction.EDIT,
    "kb_upload_file": AclAction.CREATE_CHILD,
    "kb_move": AclAction.MOVE,
    "kb_set_tags": AclAction.EDIT,
    "kb_delete": AclAction.DELETE,
}


def utcnow() -> datetime:
    return datetime.now(UTC)


class McpAuthorizationError(Exception):
    """Safe application error translated by OAuth or Problem Details adapters."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.oauth_code = OAUTH_MAPPING.get(reason, OAuthErrorCode.INVALID_REQUEST)


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    user_id: str
    client: ClientRecord
    redirect_uri: str
    resource: str
    workspace_id: str
    folder_root_id: str | None
    scopes: tuple[str, ...]
    code_challenge: str = field(repr=False)
    state: str = field(repr=False)
    grant_expires_at: datetime
    existing_grant: GrantRecord | None
    consent_required: bool


@dataclass(frozen=True, slots=True)
class AuthorizationCodeResult:
    code: str = field(repr=False)
    state: str
    issuer: str


@dataclass(frozen=True, slots=True)
class TokenResult:
    access_token: str = field(repr=False)
    expires_in: int
    scope: str
    refresh_token: str | None = field(default=None, repr=False)
    token_type: str = "Bearer"


@dataclass(frozen=True, slots=True)
class CredentialView:
    id: UUID
    principal_id: UUID
    credential_id: str
    secret_prefix: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None

    @classmethod
    def from_record(cls, record: CredentialRecord) -> CredentialView:
        return cls(
            id=record.id,
            principal_id=record.principal_id,
            credential_id=record.credential_id,
            secret_prefix=record.secret_prefix,
            expires_at=record.expires_at,
            created_at=record.created_at,
            revoked_at=record.revoked_at,
            last_used_at=record.last_used_at,
        )


@dataclass(frozen=True, slots=True)
class CredentialIssue:
    secret: str = field(repr=False)
    credential: CredentialView
    principal: ServicePrincipalRecord


@dataclass(frozen=True, slots=True)
class ConnectedGrantView:
    id: UUID
    client_name: str
    workspace_id: str
    folder_root_id: str | None
    scopes: tuple[str, ...]
    expires_at: datetime


class McpAuthorizationService:
    """Policy orchestration over identity, workspace, and digest-only state."""

    def __init__(
        self,
        repository: McpOauthRepository,
        identity: IdentityService,
        workspace: WorkspaceService,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.identity = identity
        self.workspace = workspace
        self.settings = settings

    @staticmethod
    def _scopes(value: str | tuple[str, ...], *, required: bool = True) -> tuple[str, ...]:
        try:
            scopes = parse_scopes(value if isinstance(value, str) else " ".join(value))
        except ValueError as exc:
            raise McpAuthorizationError("invalid_scope", "Unsupported MCP scope") from exc
        if required and not scopes:
            raise McpAuthorizationError("invalid_scope", "At least one MCP scope is required")
        return scopes

    @staticmethod
    def redirect_is_safe(uri: str) -> bool:
        try:
            parsed = urlsplit(uri)
            _ = parsed.port
        except ValueError:
            return False
        if not parsed.hostname or parsed.fragment or parsed.username or parsed.password:
            return False
        if parsed.scheme == "https":
            return True
        return parsed.scheme == "http" and parsed.hostname.casefold() in {
            "localhost",
            "127.0.0.1",
            "::1",
        }

    async def begin_authorization(
        self,
        *,
        user_id: str,
        response_type: str,
        client_id: str,
        redirect_uri: str,
        resource: str,
        workspace_id: str,
        folder_root_id: str | None,
        scope: str,
        state: str,
        code_challenge: str,
        code_challenge_method: str,
        grant_expires_at: datetime,
        source_bucket: str,
    ) -> AuthorizationContext:
        if response_type != "code":
            raise McpAuthorizationError(
                "unsupported_response_type", "Only authorization code is supported"
            )
        if not await self.repository.rate_allowed(
            "authorize",
            "request",
            source_bucket,
            limit=self.settings.oauth_authorize_rate_limit,
        ):
            raise McpAuthorizationError("rate_limited", "Authorization temporarily unavailable")
        client = await self.repository.find_client_by_public_id(client_id)
        if client is None or not client.is_enabled:
            raise McpAuthorizationError("invalid_client", "OAuth client is not registered")
        if client.client_type != "public" or client.token_endpoint_auth_method != "none":
            raise McpAuthorizationError("invalid_client", "Client type is not permitted")
        if redirect_uri not in client.redirect_uris or not self.redirect_is_safe(redirect_uri):
            raise McpAuthorizationError("invalid_redirect", "Redirect URI is not registered")
        if resource != self.settings.mcp_resource_url or resource != client.canonical_resource:
            raise McpAuthorizationError("invalid_resource", "Resource is not canonical")
        if code_challenge_method != "S256" or not PKCE_CHALLENGE_PATTERN.fullmatch(code_challenge):
            raise McpAuthorizationError("invalid_request", "PKCE S256 is required")
        if not state or len(state) > 128:
            raise McpAuthorizationError("invalid_request", "A bounded state value is required")
        scopes = self._scopes(scope)
        now = utcnow()
        if grant_expires_at <= now or grant_expires_at > now + timedelta(
            seconds=self.settings.oauth_refresh_absolute_seconds
        ):
            raise McpAuthorizationError("invalid_request", "Grant expiry is outside policy")
        try:
            await self.workspace.authorize_oauth_boundary(user_id, workspace_id, folder_root_id)
        except WorkspaceError as exc:
            raise McpAuthorizationError("policy_denied", exc.detail) from exc
        existing = await self.repository.find_active_grant(
            user_id, client.id, resource, workspace_id, folder_root_id
        )
        consent_required = (
            existing is None
            or not set(scopes).issubset(set(existing.scopes))
            or grant_expires_at > existing.expires_at
        )
        return AuthorizationContext(
            user_id=user_id,
            client=client,
            redirect_uri=redirect_uri,
            resource=resource,
            workspace_id=workspace_id,
            folder_root_id=folder_root_id,
            scopes=scopes,
            code_challenge=code_challenge,
            state=state,
            grant_expires_at=grant_expires_at,
            existing_grant=existing,
            consent_required=consent_required,
        )

    async def issue_authorization_code(
        self,
        context: AuthorizationContext,
        *,
        consent_approved: bool,
        correlation_id: str | None = None,
    ) -> AuthorizationCodeResult:
        current_client = await self.repository.find_client_by_public_id(context.client.client_id)
        if (
            current_client is None
            or current_client.id != context.client.id
            or not current_client.is_enabled
            or context.redirect_uri not in current_client.redirect_uris
            or not self.redirect_is_safe(context.redirect_uri)
            or context.resource != self.settings.mcp_resource_url
            or context.resource != current_client.canonical_resource
        ):
            raise McpAuthorizationError("invalid_client", "OAuth client is no longer active")
        try:
            await self.workspace.authorize_oauth_boundary(
                context.user_id, context.workspace_id, context.folder_root_id
            )
        except WorkspaceError as exc:
            raise McpAuthorizationError("policy_denied", exc.detail) from exc
        security_stamp = await self.identity.active_security_stamp(context.user_id)
        if security_stamp is None:
            raise McpAuthorizationError("invalid_grant", "The local account is inactive")
        if not consent_approved:
            await self.repository.append_audit(
                context.user_id,
                "oauth.consent.denied",
                "failure",
                target_type="oauth_client",
                target_id=context.client.client_id,
                reason="access_denied",
                correlation_id=correlation_id,
            )
            raise McpAuthorizationError("policy_denied", "Authorization was denied")
        if context.consent_required:
            grant = await self.repository.upsert_grant(
                user_id=context.user_id,
                client_id=context.client.id,
                canonical_resource=context.resource,
                workspace_id=context.workspace_id,
                folder_root_id=context.folder_root_id,
                scopes=context.scopes,
                expires_at=context.grant_expires_at,
                consent_granted_by=context.user_id,
                correlation_id=correlation_id,
            )
        else:
            existing_grant = context.existing_grant
            if existing_grant is None:
                raise McpAuthorizationError("invalid_grant", "Prior consent is unavailable")
            current_grant = await self.repository.load_grant(existing_grant.id)
            if (
                current_grant is None
                or current_grant.state != "active"
                or current_grant.expires_at <= utcnow()
                or current_grant.expires_at < context.grant_expires_at
                or not set(context.scopes).issubset(set(current_grant.scopes))
                or current_grant.user_id != context.user_id
                or current_grant.client_id != context.client.id
                or current_grant.canonical_resource != context.resource
                or current_grant.workspace_id != context.workspace_id
                or current_grant.folder_root_id != context.folder_root_id
            ):
                raise McpAuthorizationError("invalid_grant", "Prior consent is no longer active")
            grant = current_grant
        raw_code, _ = await self.repository.create_authorization_code(
            grant_id=grant.id,
            user_id=context.user_id,
            client_id=context.client.id,
            redirect_uri=context.redirect_uri,
            canonical_resource=context.resource,
            workspace_id=context.workspace_id,
            folder_root_id=context.folder_root_id,
            scopes=context.scopes,
            code_challenge=context.code_challenge,
            security_stamp=security_stamp,
            state=context.state,
            expires_at=utcnow() + timedelta(seconds=self.settings.oauth_authorization_code_seconds),
            correlation_id=correlation_id,
        )
        return AuthorizationCodeResult(
            code=raw_code, state=context.state, issuer=self.settings.public_origin
        )

    async def exchange_authorization_code(
        self,
        *,
        code: str,
        client_id: str,
        redirect_uri: str,
        resource: str,
        code_verifier: str,
        source_bucket: str,
        correlation_id: str | None = None,
    ) -> TokenResult:
        if not await self.repository.rate_allowed(
            "token", "authorization_code", source_bucket, limit=self.settings.oauth_token_rate_limit
        ):
            raise McpAuthorizationError("rate_limited", "Token exchange is rate limited")
        client = await self.repository.find_client_by_public_id(client_id)
        if (
            client is None
            or not client.is_enabled
            or client.client_type != "public"
            or client.token_endpoint_auth_method != "none"
        ):
            raise McpAuthorizationError("invalid_client", "OAuth client is not registered")
        if redirect_uri not in client.redirect_uris or not self.redirect_is_safe(redirect_uri):
            raise McpAuthorizationError("invalid_redirect", "Redirect URI is not registered")
        if resource != self.settings.mcp_resource_url or resource != client.canonical_resource:
            raise McpAuthorizationError("invalid_resource", "Resource is not canonical")
        try:
            challenge = pkce_s256(code_verifier)
            bundle = await self.repository.exchange_authorization_code_bundle(
                code,
                expected_client_id=client.id,
                expected_redirect_uri=redirect_uri,
                expected_resource=resource,
                expected_code_challenge=challenge,
                correlation_id=correlation_id,
            )
        except ValueError as exc:
            raise McpAuthorizationError("verifier_mismatch", "Invalid PKCE verifier") from exc
        except McpRepositoryError as exc:
            reason = exc.reason
            raise McpAuthorizationError(reason, "Authorization code exchange failed") from exc
        return TokenResult(
            access_token=bundle.access_token,
            refresh_token=bundle.refresh_token,
            expires_in=max(1, int((bundle.access.expires_at - utcnow()).total_seconds())),
            scope=" ".join(bundle.code.scopes),
        )

    async def refresh_access_token(
        self,
        *,
        refresh_token: str,
        client_id: str,
        resource: str,
        scope: str | None = None,
        source_bucket: str,
        correlation_id: str | None = None,
    ) -> TokenResult:
        if not await self.repository.rate_allowed(
            "token", "refresh_token", source_bucket, limit=self.settings.oauth_token_rate_limit
        ):
            raise McpAuthorizationError("rate_limited", "Token exchange is rate limited")
        client = await self.repository.find_client_by_public_id(client_id)
        if (
            client is None
            or not client.is_enabled
            or client.client_type != "public"
            or client.token_endpoint_auth_method != "none"
        ):
            raise McpAuthorizationError("invalid_client", "OAuth client is not registered")
        if resource != self.settings.mcp_resource_url or resource != client.canonical_resource:
            raise McpAuthorizationError("invalid_resource", "Resource is not canonical")
        requested = self._scopes(scope, required=False) if scope is not None else None
        try:
            bundle = await self.repository.exchange_refresh_token_bundle(
                refresh_token,
                expected_client_id=client.id,
                expected_resource=resource,
                requested_scopes=requested,
                correlation_id=correlation_id,
            )
        except McpRepositoryError as exc:
            raise McpAuthorizationError(exc.reason, "Refresh token exchange failed") from exc
        return TokenResult(
            access_token=bundle.access_token,
            refresh_token=bundle.refresh_token,
            expires_in=max(1, int((bundle.access.expires_at - utcnow()).total_seconds())),
            scope=" ".join(bundle.refresh.scopes),
        )

    async def revoke_token(self, token: str, *, reason: str = "user_request") -> None:
        """Idempotently revoke either opaque token class without disclosing its kind."""
        await self.repository.revoke_access_token(token, reason=reason)
        await self.repository.revoke_refresh_token(token, reason=reason)

    async def list_connected_grants(self, user_id: str) -> tuple[ConnectedGrantView, ...]:
        values = await self.repository.list_grants_for_user(user_id)
        return tuple(
            ConnectedGrantView(
                id=grant.id,
                client_name=client_name,
                workspace_id=grant.workspace_id,
                folder_root_id=grant.folder_root_id,
                scopes=grant.scopes,
                expires_at=grant.expires_at,
            )
            for grant, client_name in values
        )

    async def revoke_connected_grant(self, user_id: str, grant_id: UUID) -> None:
        grant = await self.repository.load_grant(grant_id)
        if grant is None or grant.user_id != user_id:
            return
        await self.repository.revoke_grant(grant_id, actor_id=user_id, reason="user_request")

    async def authenticate_bearer(
        self,
        raw_token: str,
        *,
        source_ip: str,
        correlation_id: str | None = None,
    ) -> McpActor:
        record = await self.repository.load_access_token(
            raw_token,
            expected_resource=self.settings.mcp_resource_url,
            correlation_id=correlation_id,
        )
        if record is None:
            raise McpAuthorizationError("invalid_token", "Bearer token is invalid")
        if record.grant_id is not None:
            grant = await self.repository.load_grant(record.grant_id)
            if (
                grant is None
                or grant.state != "active"
                or grant.expires_at <= utcnow()
                or grant.client_id != record.client_id
                or grant.canonical_resource != record.canonical_resource
                or grant.workspace_id != record.workspace_id
                or grant.folder_root_id != record.folder_root_id
                or not set(record.scopes).issubset(set(grant.scopes))
            ):
                raise McpAuthorizationError("invalid_token", "Bearer grant is inactive")
            current_stamp = await self.identity.active_security_stamp(grant.user_id)
            if (
                current_stamp is None
                or record.security_stamp is None
                or not hmac.compare_digest(record.security_stamp, current_stamp)
            ):
                raise McpAuthorizationError("invalid_token", "Bearer grant is inactive")
            try:
                await self.workspace.authorize_oauth_boundary(
                    grant.user_id, record.workspace_id, record.folder_root_id
                )
            except WorkspaceError as exc:
                raise McpAuthorizationError("policy_denied", exc.detail) from exc
            actor = McpActor(
                actor_type="human",
                user_id=grant.user_id,
                workspace_id=record.workspace_id,
                folder_root_id=record.folder_root_id,
                scopes=record.scopes,
                correlationId=correlation_id or "",
                token_id=str(record.id),
                source_ip=source_ip,
                concurrency_limit=self.settings.mcp_default_concurrency,
            )
            rate_limit = self.settings.mcp_default_rate_limit
        else:
            assert record.principal_id is not None
            principal = await self.repository.load_service_principal(record.principal_id)
            if (
                principal is None
                or principal.workspace_id != record.workspace_id
                or principal.folder_root_id != record.folder_root_id
                or not set(record.scopes).issubset(set(principal.scopes))
            ):
                raise McpAuthorizationError("invalid_token", "Bearer principal is inactive")
            if not self._source_allowed(source_ip, principal.cidr_allowlist):
                raise McpAuthorizationError("network_denied", "Service policy denied")
            try:
                await self.workspace.authorize_delegated_boundary(
                    principal.workspace_id, principal.folder_root_id
                )
            except WorkspaceError as exc:
                raise McpAuthorizationError("policy_denied", exc.detail) from exc
            actor = McpActor(
                actor_type="service_principal",
                principal_id=str(principal.id),
                workspace_id=principal.workspace_id,
                folder_root_id=principal.folder_root_id,
                scopes=record.scopes,
                correlationId=correlation_id or "",
                token_id=str(record.id),
                source_ip=source_ip,
                concurrency_limit=principal.concurrency_limit,
            )
            rate_limit = principal.rate_limit
            if not await self.repository.rate_allowed(
                "service",
                "mcp_request",
                f"{principal.id}:{source_ip}",
                limit=principal.rate_limit,
            ):
                raise McpAuthorizationError("rate_limited", "Principal rate is exceeded")
        if not await self.repository.rate_allowed(
            "tool",
            "request",
            f"{record.id}:{source_ip}",
            limit=rate_limit,
        ):
            raise McpAuthorizationError("rate_limited", "MCP request rate is exceeded")
        await self.repository.touch_access_token(record.id)
        return actor

    async def acquire_tool_lease(self, actor: McpActor, request_id: str) -> UUID:
        if actor.token_id is None or actor.source_ip is None:
            raise McpAuthorizationError("invalid_token", "Bearer token context is incomplete")
        lease = await self.repository.acquire_concurrency_lease(
            token_id=UUID(actor.token_id),
            principal_id=UUID(actor.principal_id) if actor.principal_id else None,
            source=actor.source_ip,
            request_id=request_id,
            limit=actor.concurrency_limit,
            correlation_id=actor.correlation_id or None,
        )
        if lease is None:
            raise McpAuthorizationError("rate_limited", "MCP concurrency limit is exceeded")
        return lease

    async def release_tool_lease(self, lease_id: UUID) -> None:
        await self.repository.release_concurrency_lease(lease_id)

    async def authorize_tool(
        self, actor: McpActor, tool_name: str, *, target_folder_id: str | None = None
    ) -> None:
        required_scope = KNOWN_TOOLS.get(tool_name)
        safe_tool_name = tool_name if required_scope is not None else "unknown"
        target_type = "service_principal" if actor.principal_id else "user"
        target_id = actor.principal_id or actor.user_id
        try:
            if required_scope is None or required_scope not in actor.scopes:
                raise McpAuthorizationError("insufficient_scope", "Tool scope is not granted")
            assert actor.workspace_id is not None
            if actor.actor_type == "service_principal":
                await self.workspace.authorize_delegated_boundary(
                    actor.workspace_id, actor.folder_root_id, target_folder_id
                )
            else:
                assert actor.user_id is not None
                await self.workspace.authorize_oauth_boundary(
                    actor.user_id,
                    actor.workspace_id,
                    actor.folder_root_id,
                    target_folder_id,
                    TOOL_ACL_ACTION.get(tool_name, AclAction.VIEW_METADATA),
                )
        except (McpAuthorizationError, WorkspaceError) as exc:
            reason = exc.reason if isinstance(exc, McpAuthorizationError) else "policy_denied"
            await self.repository.append_audit(
                actor.user_id,
                "mcp.tool.denied",
                "failure",
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                metadata={"tool": safe_tool_name, "workspace_id": actor.workspace_id},
                correlation_id=actor.correlation_id or None,
            )
            if isinstance(exc, McpAuthorizationError):
                raise
            raise McpAuthorizationError(reason, exc.detail) from exc
        await self.repository.append_audit(
            actor.user_id,
            "mcp.tool.allowed",
            "success",
            target_type=target_type,
            target_id=target_id,
            metadata={"tool": safe_tool_name, "workspace_id": actor.workspace_id},
            correlation_id=actor.correlation_id or None,
        )

    async def create_service_principal(
        self,
        *,
        actor_id: str,
        workspace_id: str,
        folder_root_id: str | None,
        display_name: str,
        purpose: str,
        owner_user_id: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        rate_limit: int,
        concurrency_limit: int,
        cidr_allowlist: tuple[str, ...] = (),
        correlation_id: str | None = None,
    ) -> CredentialIssue:
        await self.workspace.require_workspace_admin(actor_id, workspace_id)
        await self.workspace.authorize_delegated_boundary(workspace_id, folder_root_id)
        if await self.identity.active_security_stamp(owner_user_id) is None:
            raise McpAuthorizationError("invalid_request", "Owner account is inactive")
        normalized_scopes = self._scopes(scopes)
        if not set(normalized_scopes).issubset(SERVICE_PRINCIPAL_SCOPES):
            raise McpAuthorizationError("invalid_scope", "Service principal scope is not supported")
        if not display_name.strip() or not purpose.strip():
            raise McpAuthorizationError("invalid_request", "Name and purpose are required")
        if rate_limit < 1 or concurrency_limit < 1:
            raise McpAuthorizationError("invalid_request", "Rate policy must be positive")
        try:
            principal = await self.repository.create_service_principal(
                workspace_id=workspace_id,
                folder_root_id=folder_root_id,
                display_name=display_name.strip(),
                purpose=purpose.strip(),
                owner_user_id=owner_user_id,
                scopes=normalized_scopes,
                expires_at=expires_at,
                rate_limit=rate_limit,
                concurrency_limit=concurrency_limit,
                cidr_allowlist=cidr_allowlist,
                created_by=actor_id,
                correlation_id=correlation_id,
            )
        except McpRepositoryError as exc:
            raise McpAuthorizationError(exc.reason, "Service principal creation failed") from exc
        try:
            secret, credential = await self.repository.create_credential(
                principal_id=principal.id,
                created_by=actor_id,
                expires_at=expires_at,
                correlation_id=correlation_id,
            )
        except McpRepositoryError as exc:
            await self.repository.set_principal_state(
                principal.id,
                "revoked",
                actor_id=actor_id,
                reason="credential_issue_failed",
            )
            raise McpAuthorizationError(exc.reason, "Credential issuance failed") from exc
        except BaseException:
            await self.repository.set_principal_state(
                principal.id,
                "revoked",
                actor_id=actor_id,
                reason="credential_issue_failed",
            )
            raise
        return CredentialIssue(
            secret=secret,
            credential=CredentialView.from_record(credential),
            principal=principal,
        )

    async def list_service_principals(
        self, actor_id: str, workspace_id: str
    ) -> tuple[ServicePrincipalRecord, ...]:
        await self.workspace.require_workspace_admin(actor_id, workspace_id)
        return await self.repository.list_service_principals(workspace_id)

    async def get_service_principal(
        self, actor_id: str, principal_id: UUID
    ) -> ServicePrincipalRecord:
        principal = await self.repository.load_service_principal(
            principal_id, include_inactive=True
        )
        if principal is None:
            raise McpAuthorizationError("invalid_principal", "Service principal not found")
        await self.workspace.require_workspace_admin(actor_id, principal.workspace_id)
        return principal

    async def list_service_credentials(
        self, actor_id: str, principal_id: UUID
    ) -> tuple[CredentialView, ...]:
        await self.get_service_principal(actor_id, principal_id)
        records = await self.repository.list_credentials_for_principal(principal_id)
        return tuple(CredentialView.from_record(record) for record in records)

    async def rotate_service_credential(
        self,
        *,
        actor_id: str,
        principal_id: UUID,
        credential_id: str,
        expires_at: datetime,
        overlap_expires_at: datetime | None = None,
        correlation_id: str | None = None,
    ) -> CredentialIssue:
        principal = await self.repository.load_service_principal(
            principal_id, include_inactive=True
        )
        if principal is None:
            raise McpAuthorizationError("invalid_principal", "Service principal not found")
        await self.workspace.require_workspace_admin(actor_id, principal.workspace_id)
        existing = await self.repository.find_credential_by_id(credential_id)
        if existing is None or existing.principal_id != principal.id:
            raise McpAuthorizationError("invalid_credential", "Credential not found")
        try:
            secret, credential, _ = await self.repository.rotate_credential(
                credential_id,
                created_by=actor_id,
                expires_at=expires_at,
                overlap_expires_at=overlap_expires_at,
                correlation_id=correlation_id,
            )
        except McpRepositoryError as exc:
            raise McpAuthorizationError(exc.reason, "Credential rotation failed") from exc
        return CredentialIssue(
            secret=secret,
            credential=CredentialView.from_record(credential),
            principal=principal,
        )

    async def revoke_service_principal(
        self,
        *,
        actor_id: str,
        principal_id: UUID,
        reason: str = "admin_revoked",
    ) -> None:
        principal = await self.repository.load_service_principal(
            principal_id, include_inactive=True
        )
        if principal is None:
            return
        await self.workspace.require_workspace_admin(actor_id, principal.workspace_id)
        await self.repository.set_principal_state(
            principal_id, "revoked", actor_id=actor_id, reason=reason
        )

    async def revoke_service_credential(
        self,
        *,
        actor_id: str,
        principal_id: UUID,
        credential_id: str,
        reason: str = "admin_revoked",
        correlation_id: str | None = None,
    ) -> None:
        principal = await self.get_service_principal(actor_id, principal_id)
        credential = await self.repository.find_credential_by_id(credential_id)
        if credential is None:
            return
        if credential.principal_id != principal.id:
            raise McpAuthorizationError("invalid_credential", "Credential not found")
        await self.repository.revoke_credential(
            credential_id,
            actor_id=actor_id,
            reason=reason,
            correlation_id=correlation_id,
        )

    async def exchange_service_credential(
        self,
        *,
        credential_id: str,
        secret: str,
        source_ip: str,
        requested_scopes: tuple[str, ...] | None = None,
        correlation_id: str | None = None,
    ) -> TokenResult:
        if not await self.repository.rate_allowed(
            "service",
            "exchange",
            f"{credential_id}:{source_ip}",
            limit=self.settings.oauth_token_rate_limit,
        ):
            raise McpAuthorizationError("rate_limited", "Credential exchange is rate limited")
        resolved = await self.repository.exchange_credential(
            credential_id, secret, correlation_id=correlation_id
        )
        if resolved is None:
            raise McpAuthorizationError("invalid_grant", "Service credential is invalid")
        _, principal = resolved
        if not self._source_allowed(source_ip, principal.cidr_allowlist):
            await self.repository.append_audit(
                None,
                "mcp.network.denied",
                "failure",
                target_type="service_principal",
                target_id=str(principal.id),
                reason="network_denied",
                metadata={"workspace_id": principal.workspace_id},
                correlation_id=correlation_id,
            )
            raise McpAuthorizationError("network_denied", "Source network is not allowed")
        if not await self.repository.rate_allowed(
            "service",
            "principal_exchange",
            f"{principal.id}:{source_ip}",
            limit=principal.rate_limit,
        ):
            raise McpAuthorizationError("rate_limited", "Principal rate is exceeded")
        scopes = principal.scopes if requested_scopes is None else self._scopes(requested_scopes)
        if not set(scopes).issubset(set(principal.scopes)):
            raise McpAuthorizationError("invalid_scope", "Credential scope cannot be widened")
        try:
            await self.workspace.authorize_delegated_boundary(
                principal.workspace_id, principal.folder_root_id
            )
        except WorkspaceError as exc:
            raise McpAuthorizationError("policy_denied", exc.detail) from exc
        access, access_record = await self.repository.create_access_token(
            grant_id=None,
            principal_id=principal.id,
            client_id=None,
            canonical_resource=self.settings.mcp_resource_url,
            workspace_id=principal.workspace_id,
            folder_root_id=principal.folder_root_id,
            scopes=scopes,
            expires_at=min(
                principal.expires_at,
                utcnow() + timedelta(seconds=self.settings.oauth_access_token_seconds),
            ),
            correlation_id=correlation_id,
        )
        return TokenResult(
            access_token=access,
            expires_in=max(1, int((access_record.expires_at - utcnow()).total_seconds())),
            scope=" ".join(scopes),
        )

    @staticmethod
    def _source_allowed(source_ip: str, cidr_allowlist: tuple[str, ...]) -> bool:
        try:
            address = ip_address(source_ip)
            networks = tuple(ip_network(network, strict=False) for network in cidr_allowlist)
        except ValueError:
            return False
        return not networks or any(address in network for network in networks)
