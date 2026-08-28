"""Focused policy tests for the transport-neutral OAuth application service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ima.application.mcp_contracts import McpActor
from ima.application.oauth import (
    CredentialView,
    McpAuthorizationError,
    McpAuthorizationService,
)
from ima.config import Settings
from ima.domain.authorization import AclAction
from ima.domain.oauth import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    AuthorizationTokenBundle,
    ClientRecord,
    CredentialRecord,
    GrantRecord,
    RefreshAccessTokenBundle,
    ServicePrincipalRecord,
)
from ima.infrastructure.oauth import McpRepositoryError

RESOURCE = "https://ima.example.test/mcp"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
SCOPES = ("mcp:knowledge:read", "mcp:knowledge:search")


def client() -> ClientRecord:
    return ClientRecord(
        id=uuid4(),
        client_id="desktop",
        client_name="Desktop",
        client_type="public",
        token_endpoint_auth_method="none",
        client_secret_digest=None,
        application_type="native",
        canonical_resource=RESOURCE,
        is_enabled=True,
        redirect_uris=("http://localhost:8765/callback",),
    )


def grant(value: ClientRecord, *, scopes: tuple[str, ...] = SCOPES) -> GrantRecord:
    return GrantRecord(
        id=uuid4(),
        user_id="user-1",
        client_id=value.id,
        canonical_resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scopes=scopes,
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=5),
    )


def service() -> tuple[McpAuthorizationService, Any, Any, Any, Settings]:
    repository = SimpleNamespace(
        rate_allowed=AsyncMock(return_value=True),
        find_client_by_public_id=AsyncMock(),
        find_active_grant=AsyncMock(return_value=None),
        append_audit=AsyncMock(),
        upsert_grant=AsyncMock(),
        create_authorization_code=AsyncMock(),
        consume_authorization_code=AsyncMock(),
        exchange_authorization_code_bundle=AsyncMock(),
        create_access_token=AsyncMock(),
        load_grant=AsyncMock(),
        exchange_refresh_token_bundle=AsyncMock(),
        revoke_access_token=AsyncMock(),
        revoke_refresh_token=AsyncMock(),
        load_access_token=AsyncMock(),
        load_service_principal=AsyncMock(),
        touch_access_token=AsyncMock(),
        create_service_principal=AsyncMock(),
        create_credential=AsyncMock(),
        list_service_principals=AsyncMock(),
        rotate_credential=AsyncMock(),
        set_principal_state=AsyncMock(),
        exchange_credential=AsyncMock(),
        find_credential_by_id=AsyncMock(),
        revoke_credential=AsyncMock(),
        acquire_concurrency_lease=AsyncMock(return_value=uuid4()),
        release_concurrency_lease=AsyncMock(),
    )
    identity = SimpleNamespace(active_security_stamp=AsyncMock(return_value="stamp-1"))
    workspace = SimpleNamespace(
        authorize_oauth_boundary=AsyncMock(),
        require_workspace_admin=AsyncMock(),
        authorize_delegated_boundary=AsyncMock(),
    )
    settings = Settings(environment="test", public_origin="https://ima.example.test")
    subject = McpAuthorizationService(
        cast(Any, repository), cast(Any, identity), cast(Any, workspace), settings
    )
    return subject, repository, identity, workspace, settings


def test_credential_view_excludes_digest() -> None:
    record = CredentialRecord(
        id=uuid4(),
        principal_id=uuid4(),
        credential_id="key-1",
        digest="must-not-escape",
        secret_prefix="mcpsc_123",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        created_at=datetime.now(UTC),
    )
    view = CredentialView.from_record(record)
    assert not hasattr(view, "digest")
    assert "must-not-escape" not in repr(view)


@pytest.mark.asyncio
async def test_begin_authorization_reuses_only_an_exact_subset() -> None:
    subject, repository, _, workspace, _ = service()
    registered = client()
    existing = grant(registered)
    repository.find_client_by_public_id.return_value = registered
    repository.find_active_grant.return_value = existing

    context = await subject.begin_authorization(
        user_id="user-1",
        response_type="code",
        client_id="desktop",
        redirect_uri="http://localhost:8765/callback",
        resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scope="mcp:knowledge:read",
        state="opaque-state",
        code_challenge=CHALLENGE,
        code_challenge_method="S256",
        grant_expires_at=datetime.now(UTC) + timedelta(days=1),
        source_bucket="127.0.0.1",
    )

    assert context.consent_required is False
    workspace.authorize_oauth_boundary.assert_awaited_once_with("user-1", "workspace-1", None)


@pytest.mark.asyncio
async def test_begin_authorization_requires_consent_for_scope_expansion() -> None:
    subject, repository, _, _, _ = service()
    registered = client()
    repository.find_client_by_public_id.return_value = registered
    repository.find_active_grant.return_value = grant(registered, scopes=("mcp:knowledge:read",))

    context = await subject.begin_authorization(
        user_id="user-1",
        response_type="code",
        client_id="desktop",
        redirect_uri="http://localhost:8765/callback",
        resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scope="mcp:knowledge:read mcp:knowledge:write",
        state="opaque-state",
        code_challenge=CHALLENGE,
        code_challenge_method="S256",
        grant_expires_at=datetime.now(UTC) + timedelta(days=1),
        source_bucket="127.0.0.1",
    )

    assert context.consent_required is True


@pytest.mark.asyncio
async def test_code_issue_honors_explicit_denial_even_for_reusable_prior_consent() -> None:
    subject, repository, _, _, _ = service()
    registered = client()
    existing = grant(registered)
    repository.find_client_by_public_id.return_value = registered
    repository.find_active_grant.return_value = existing
    context = await subject.begin_authorization(
        user_id="user-1",
        response_type="code",
        client_id=registered.client_id,
        redirect_uri=registered.redirect_uris[0],
        resource=RESOURCE,
        workspace_id=existing.workspace_id,
        folder_root_id=None,
        scope="mcp:knowledge:read",
        state="state",
        code_challenge=CHALLENGE,
        code_challenge_method="S256",
        grant_expires_at=datetime.now(UTC) + timedelta(days=1),
        source_bucket="127.0.0.1",
    )
    assert context.consent_required is False

    with pytest.raises(McpAuthorizationError) as denied:
        await subject.issue_authorization_code(context, consent_approved=False)
    assert denied.value.reason == "policy_denied"
    repository.create_authorization_code.assert_not_awaited()


@pytest.mark.asyncio
async def test_begin_authorization_rejects_non_s256_and_redirect_mismatch() -> None:
    subject, repository, _, _, _ = service()
    repository.find_client_by_public_id.return_value = client()
    common = dict(
        user_id="user-1",
        response_type="code",
        client_id="desktop",
        resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scope="mcp:knowledge:read",
        state="opaque-state",
        code_challenge=CHALLENGE,
        grant_expires_at=datetime.now(UTC) + timedelta(days=1),
        source_bucket="127.0.0.1",
    )
    with pytest.raises(McpAuthorizationError) as method:
        await subject.begin_authorization(
            **common,
            redirect_uri="http://localhost:8765/callback",
            code_challenge_method="plain",
        )
    assert method.value.reason == "invalid_request"
    with pytest.raises(McpAuthorizationError) as redirect:
        await subject.begin_authorization(
            **common,
            redirect_uri="http://localhost:9999/callback",
            code_challenge_method="S256",
        )
    assert redirect.value.reason == "invalid_redirect"

    registered = client()
    registered.redirect_uris = ("http://localhost:8765/callback#fragment",)
    repository.find_client_by_public_id.return_value = registered
    with pytest.raises(McpAuthorizationError) as fragment:
        await subject.begin_authorization(
            **common,
            redirect_uri=registered.redirect_uris[0],
            code_challenge_method="S256",
        )
    assert fragment.value.reason == "invalid_redirect"

    with pytest.raises(McpAuthorizationError) as response_type:
        await subject.begin_authorization(
            **{**common, "response_type": "token"},
            redirect_uri="http://localhost:8765/callback",
            code_challenge_method="S256",
        )
    assert response_type.value.reason == "unsupported_response_type"


@pytest.mark.asyncio
async def test_code_exchange_issues_bound_access_and_rotating_refresh() -> None:
    subject, repository, _, _, settings = service()
    registered = client()
    approved = grant(registered)
    consumed = AuthorizationCodeRecord(
        id=uuid4(),
        grant_id=approved.id,
        user_id="user-1",
        client_id=registered.id,
        redirect_uri="http://localhost:8765/callback",
        canonical_resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scopes=SCOPES,
        code_challenge=CHALLENGE,
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
        state="state",
    )
    repository.find_client_by_public_id.return_value = registered
    repository.exchange_authorization_code_bundle.return_value = AuthorizationTokenBundle(
        "access",
        "refresh",
        SimpleNamespace(expires_at=datetime.now(UTC) + timedelta(minutes=10)),
        SimpleNamespace(),
        consumed,
    )
    assert "access" not in repr(repository.exchange_authorization_code_bundle.return_value)
    assert "refresh" not in repr(repository.exchange_authorization_code_bundle.return_value)

    result = await subject.exchange_authorization_code(
        code="code",
        client_id="desktop",
        redirect_uri="http://localhost:8765/callback",
        resource=RESOURCE,
        code_verifier=VERIFIER,
        source_bucket="127.0.0.1",
    )

    assert result.access_token == "access"
    assert result.refresh_token == "refresh"
    assert 0 < result.expires_in <= settings.oauth_access_token_seconds
    assert "access" not in repr(result) and "refresh" not in repr(result)
    repository.exchange_authorization_code_bundle.assert_awaited_once_with(
        "code",
        expected_client_id=registered.id,
        expected_redirect_uri="http://localhost:8765/callback",
        expected_resource=RESOURCE,
        expected_code_challenge=CHALLENGE,
        correlation_id=None,
    )


@pytest.mark.asyncio
async def test_code_exchange_failure_never_needs_compensating_revoke() -> None:
    subject, repository, _, _, _ = service()
    registered = client()
    repository.find_client_by_public_id.return_value = registered
    repository.exchange_authorization_code_bundle.side_effect = McpRepositoryError(
        "invalid_grant", "failed"
    )

    with pytest.raises(McpAuthorizationError):
        await subject.exchange_authorization_code(
            code="code",
            client_id=registered.client_id,
            redirect_uri=registered.redirect_uris[0],
            resource=RESOURCE,
            code_verifier=VERIFIER,
            source_bucket="127.0.0.1",
        )
    repository.revoke_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_exchange_consumes_secret_safe_atomic_bundle() -> None:
    subject, repository, _, _, _ = service()
    registered = client()
    approved = grant(registered)
    repository.find_client_by_public_id.return_value = registered
    repository.exchange_refresh_token_bundle.return_value = RefreshAccessTokenBundle(
        "new-access",
        "new-refresh",
        SimpleNamespace(expires_at=datetime.now(UTC) + timedelta(minutes=5)),
        SimpleNamespace(scopes=SCOPES),
        approved,
    )

    result = await subject.refresh_access_token(
        refresh_token="old-refresh",
        client_id=registered.client_id,
        resource=RESOURCE,
        source_bucket="127.0.0.1",
    )

    assert result.access_token == "new-access"
    assert result.refresh_token == "new-refresh"
    assert result.scope == " ".join(SCOPES)
    assert "new-access" not in repr(repository.exchange_refresh_token_bundle.return_value)
    assert "new-refresh" not in repr(repository.exchange_refresh_token_bundle.return_value)
    assert "new-access" not in repr(result) and "new-refresh" not in repr(result)
    repository.create_access_token.assert_not_awaited()
    repository.exchange_refresh_token_bundle.assert_awaited_once_with(
        "old-refresh",
        expected_client_id=registered.id,
        expected_resource=RESOURCE,
        requested_scopes=None,
        correlation_id=None,
    )


@pytest.mark.asyncio
async def test_refresh_bundle_failure_never_needs_compensating_revoke() -> None:
    subject, repository, _, _, _ = service()
    registered = client()
    repository.find_client_by_public_id.return_value = registered
    repository.exchange_refresh_token_bundle.side_effect = McpRepositoryError(
        "invalid_grant", "failed"
    )

    with pytest.raises(McpAuthorizationError):
        await subject.refresh_access_token(
            refresh_token="old-refresh",
            client_id=registered.client_id,
            resource=RESOURCE,
            source_bucket="127.0.0.1",
        )
    repository.revoke_refresh_token.assert_not_awaited()
    repository.create_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_exchange_enforces_network_and_scope_narrowing() -> None:
    subject, repository, _, workspace, _ = service()
    principal = ServicePrincipalRecord(
        id=uuid4(),
        workspace_id="workspace-1",
        folder_root_id="root-1",
        display_name="CI",
        purpose="Ingestion",
        owner_user_id="owner-1",
        scopes=SCOPES,
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        rate_limit=10,
        concurrency_limit=2,
        cidr_allowlist=("10.0.0.0/8",),
    )
    credential = CredentialRecord(
        id=uuid4(),
        principal_id=principal.id,
        credential_id="key-1",
        digest="never-exposed",
        secret_prefix="mcpsc_123",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        created_at=datetime.now(UTC),
    )
    repository.exchange_credential.return_value = (credential, principal)
    repository.create_access_token.return_value = (
        "access",
        SimpleNamespace(expires_at=datetime.now(UTC) + timedelta(minutes=10)),
    )

    result = await subject.exchange_service_credential(
        credential_id="key-1",
        secret="one-time-secret",
        source_ip="10.2.3.4",
        requested_scopes=("mcp:knowledge:read",),
    )
    assert result.refresh_token is None
    assert result.scope == "mcp:knowledge:read"
    workspace.authorize_delegated_boundary.assert_awaited_once_with("workspace-1", "root-1")

    with pytest.raises(McpAuthorizationError) as denied:
        await subject.exchange_service_credential(
            credential_id="key-1",
            secret="one-time-secret",
            source_ip="192.0.2.10",
        )
    assert denied.value.reason == "network_denied"
    assert subject._source_allowed("10.2.3.4", ("not-a-network",)) is False


@pytest.mark.asyncio
async def test_service_principal_creation_revokes_partial_principal_on_secret_failure() -> None:
    subject, repository, _, _, _ = service()
    principal = ServicePrincipalRecord(
        id=uuid4(),
        workspace_id="workspace-1",
        folder_root_id=None,
        display_name="CI",
        purpose="Ingestion",
        owner_user_id="owner-1",
        scopes=("mcp:knowledge:read",),
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        rate_limit=10,
        concurrency_limit=2,
    )
    repository.create_service_principal.return_value = principal
    repository.create_credential.side_effect = McpRepositoryError("invalid_principal", "failed")

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.create_service_principal(
            actor_id="admin-1",
            workspace_id="workspace-1",
            folder_root_id=None,
            display_name="CI",
            purpose="Ingestion",
            owner_user_id="owner-1",
            scopes=("mcp:knowledge:read",),
            expires_at=principal.expires_at,
            rate_limit=10,
            concurrency_limit=2,
        )
    assert exc.value.reason == "invalid_principal"
    repository.set_principal_state.assert_awaited_once_with(
        principal.id,
        "revoked",
        actor_id="admin-1",
        reason="credential_issue_failed",
    )


@pytest.mark.asyncio
async def test_service_principal_rejects_scopes_without_delegated_target_paths() -> None:
    subject, repository, _, _, _ = service()
    with pytest.raises(McpAuthorizationError) as exc:
        await subject.create_service_principal(
            actor_id="admin-1",
            workspace_id="workspace-1",
            folder_root_id=None,
            display_name="CI",
            purpose="Unsupported write",
            owner_user_id="owner-1",
            scopes=("mcp:knowledge:write",),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            rate_limit=10,
            concurrency_limit=2,
        )
    assert exc.value.reason == "invalid_scope"
    repository.create_service_principal.assert_not_awaited()


@pytest.mark.asyncio
async def test_credential_rotation_rejects_cross_principal_identifier() -> None:
    subject, repository, _, _, _ = service()
    principal = ServicePrincipalRecord(
        id=uuid4(),
        workspace_id="workspace-1",
        folder_root_id=None,
        display_name="CI",
        purpose="Ingestion",
        owner_user_id="owner-1",
        scopes=("mcp:knowledge:read",),
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        rate_limit=10,
        concurrency_limit=2,
    )
    repository.load_service_principal.return_value = principal
    repository.find_credential_by_id.return_value = CredentialRecord(
        id=uuid4(),
        principal_id=uuid4(),
        credential_id="other-key",
        digest="hidden",
        secret_prefix="mcpsc_other",
        expires_at=principal.expires_at,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.rotate_service_credential(
            actor_id="admin-1",
            principal_id=principal.id,
            credential_id="other-key",
            expires_at=principal.expires_at,
        )
    assert exc.value.reason == "invalid_credential"
    repository.rotate_credential.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_bearer_builds_human_actor_from_current_grant() -> None:
    subject, repository, _, workspace, _ = service()
    registered = client()
    approved = grant(registered)
    token = AccessTokenRecord(
        id=uuid4(),
        token_digest="digest",
        grant_id=approved.id,
        principal_id=None,
        client_id=registered.id,
        canonical_resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scopes=SCOPES,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        security_stamp="stamp-1",
    )
    repository.load_access_token.return_value = token
    repository.load_grant.return_value = approved

    actor = await subject.authenticate_bearer("raw-access", source_ip="127.0.0.1")

    assert actor.actor_type == "human"
    assert actor.user_id == "user-1"
    workspace.authorize_oauth_boundary.assert_awaited_once_with("user-1", "workspace-1", None)
    repository.touch_access_token.assert_awaited_once_with(token.id)


@pytest.mark.asyncio
async def test_tool_scope_denial_and_allow_are_audited() -> None:
    subject, repository, _, workspace, _ = service()
    actor = McpActor(
        actor_type="service_principal",
        principal_id=str(uuid4()),
        workspace_id="workspace-1",
        folder_root_id="root-1",
        scopes=("mcp:knowledge:read",),
        correlationId="corr-1",
    )

    with pytest.raises(McpAuthorizationError) as denied:
        await subject.authorize_tool(actor, "kb_ask", target_folder_id="child-1")
    assert denied.value.reason == "insufficient_scope"
    assert repository.append_audit.await_args_list[-1].args[1] == "mcp.tool.denied"

    with pytest.raises(McpAuthorizationError):
        await subject.authorize_tool(actor, "attacker-controlled-" * 100)
    assert repository.append_audit.await_args_list[-1].kwargs["metadata"]["tool"] == "unknown"

    await subject.authorize_tool(actor, "kb_get_note", target_folder_id="child-1")
    workspace.authorize_delegated_boundary.assert_awaited_once_with(
        "workspace-1", "root-1", "child-1"
    )
    assert repository.append_audit.await_args_list[-1].args[1] == "mcp.tool.allowed"


@pytest.mark.asyncio
async def test_human_tool_authorization_uses_the_actual_acl_action() -> None:
    subject, _, _, workspace, _ = service()
    actor = McpActor(
        actor_type="human",
        user_id="user-1",
        workspace_id="workspace-1",
        folder_root_id="root-1",
        scopes=("mcp:knowledge:ask",),
    )

    await subject.authorize_tool(actor, "kb_ask", target_folder_id="child-1")
    workspace.authorize_oauth_boundary.assert_awaited_once_with(
        "user-1", "workspace-1", "root-1", "child-1", AclAction.ASK
    )


@pytest.mark.asyncio
async def test_concurrency_denial_maps_to_safe_rate_limit_and_release_is_idempotent() -> None:
    subject, repository, _, _, _ = service()
    repository.acquire_concurrency_lease.return_value = None
    actor = McpActor(
        actor_type="human",
        user_id="user-1",
        workspace_id="workspace-1",
        scopes=("mcp:workspaces:read",),
        token_id=str(uuid4()),
        source_ip="10.0.0.1",
        concurrency_limit=1,
    )
    with pytest.raises(McpAuthorizationError) as exc:
        await subject.acquire_tool_lease(actor, "request-1")
    assert exc.value.reason == "rate_limited"
    lease_id = uuid4()
    await subject.release_tool_lease(lease_id)
    repository.release_concurrency_lease.assert_awaited_once_with(lease_id)
