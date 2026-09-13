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

# Membership fixture: user-1 owns an editable KB, can view a second one, and
# has no membership in anything else.
KB_SUMMARIES = [
    {"id": "kb-editor", "name": "Editable", "role": "editor", "owned": True},
    {"id": "kb-viewer", "name": "Read-only", "role": "viewer", "owned": False},
]


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
        scopes=scopes,
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=5),
    )


def principal(
    *,
    scopes: tuple[str, ...] = SCOPES,
    owner_user_id: str = "owner-1",
) -> ServicePrincipalRecord:
    return ServicePrincipalRecord(
        id=uuid4(),
        display_name="CI",
        purpose="Ingestion",
        owner_user_id=owner_user_id,
        scopes=scopes,
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        rate_limit=10,
        concurrency_limit=2,
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
        resolve_credential_bearer=AsyncMock(return_value=None),
        find_credential_by_id=AsyncMock(),
        revoke_credential=AsyncMock(),
        acquire_concurrency_lease=AsyncMock(return_value=uuid4()),
        release_concurrency_lease=AsyncMock(),
    )
    identity = SimpleNamespace(active_security_stamp=AsyncMock(return_value="stamp-1"))
    kb = SimpleNamespace(list_knowledge_bases=AsyncMock(return_value=KB_SUMMARIES))
    settings = Settings(environment="test", public_origin="https://ima.example.test")
    subject = McpAuthorizationService(
        cast(Any, repository), cast(Any, identity), cast(Any, kb), settings
    )
    return subject, repository, identity, kb, settings


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
    subject, repository, _, kb, _ = service()
    registered = client()
    repository.find_client_by_public_id.return_value = registered
    repository.find_active_grant.return_value = grant(registered)

    context = await subject.begin_authorization(
        user_id="user-1",
        response_type="code",
        client_id="desktop",
        redirect_uri="http://localhost:8765/callback",
        resource=RESOURCE,
        scope="mcp:knowledge:read",
        state="opaque-state",
        code_challenge=CHALLENGE,
        code_challenge_method="S256",
        grant_expires_at=datetime.now(UTC) + timedelta(days=1),
        source_bucket="127.0.0.1",
    )

    assert context.consent_required is False
    # User-level grants carry no knowledge-base boundary at consent time.
    kb.list_knowledge_bases.assert_not_awaited()
    assert context.existing_grant is not None and context.existing_grant.kb_id is None


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
    subject, repository, _, kb, _ = service()
    machine = principal()
    credential = CredentialRecord(
        id=uuid4(),
        principal_id=machine.id,
        credential_id="key-1",
        digest="never-exposed",
        secret_prefix="mcpsc_123",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        created_at=datetime.now(UTC),
    )
    machine.cidr_allowlist = ("10.0.0.0/8",)
    repository.exchange_credential.return_value = (credential, machine)
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
    # User-level principals carry no boundary; membership is checked per call.
    kb.list_knowledge_bases.assert_not_awaited()
    issued = repository.create_access_token.await_args.kwargs
    assert "workspace_id" not in issued and "folder_root_id" not in issued

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
    machine = principal(scopes=("mcp:knowledge:read",))
    repository.create_service_principal.return_value = machine
    repository.create_credential.side_effect = McpRepositoryError("invalid_principal", "failed")

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.create_service_principal(
            actor_id="admin-1",
            display_name="CI",
            purpose="Ingestion",
            owner_user_id="owner-1",
            scopes=("mcp:knowledge:read",),
            expires_at=machine.expires_at,
            rate_limit=10,
            concurrency_limit=2,
        )
    assert exc.value.reason == "invalid_principal"
    repository.set_principal_state.assert_awaited_once_with(
        machine.id,
        "revoked",
        actor_id="admin-1",
        reason="credential_issue_failed",
    )


@pytest.mark.asyncio
async def test_service_principal_rejects_human_only_scopes() -> None:
    subject, repository, _, _, _ = service()
    with pytest.raises(McpAuthorizationError) as exc:
        await subject.create_service_principal(
            actor_id="admin-1",
            display_name="CI",
            purpose="Ask automation",
            owner_user_id="owner-1",
            scopes=("mcp:knowledge:ask",),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            rate_limit=10,
            concurrency_limit=2,
        )
    assert exc.value.reason == "invalid_scope"
    repository.create_service_principal.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_principal_creation_requires_active_accounts() -> None:
    subject, repository, identity, _, _ = service()
    identity.active_security_stamp.return_value = None
    with pytest.raises(McpAuthorizationError) as exc:
        await subject.create_service_principal(
            actor_id="admin-1",
            display_name="CI",
            purpose="Ingestion",
            owner_user_id="owner-1",
            scopes=("mcp:knowledge:read",),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            rate_limit=10,
            concurrency_limit=2,
        )
    assert exc.value.reason == "invalid_request"
    repository.create_service_principal.assert_not_awaited()


@pytest.mark.asyncio
async def test_credential_rotation_rejects_cross_principal_identifier() -> None:
    subject, repository, _, _, _ = service()
    machine = principal(scopes=("mcp:knowledge:read",))
    repository.load_service_principal.return_value = machine
    repository.find_credential_by_id.return_value = CredentialRecord(
        id=uuid4(),
        principal_id=uuid4(),
        credential_id="other-key",
        digest="hidden",
        secret_prefix="mcpsc_other",
        expires_at=machine.expires_at,
        created_at=datetime.now(UTC),
    )

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.rotate_service_credential(
            actor_id=machine.owner_user_id,
            principal_id=machine.id,
            credential_id="other-key",
            expires_at=machine.expires_at,
        )
    assert exc.value.reason == "invalid_credential"
    repository.rotate_credential.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_principal_management_is_owner_scoped() -> None:
    subject, repository, _, _, _ = service()
    machine = principal(scopes=("mcp:knowledge:read",))
    repository.load_service_principal.return_value = machine

    # Owners may inspect and revoke their principals.
    repository.list_service_principals.return_value = (machine,)
    listed = await subject.list_service_principals(machine.owner_user_id)
    assert listed == (machine,)
    repository.list_service_principals.assert_awaited_once_with(owner_user_id=machine.owner_user_id)

    with pytest.raises(McpAuthorizationError) as foreign:
        await subject.get_service_principal("someone-else", machine.id)
    assert foreign.value.reason == "policy_denied"

    await subject.revoke_service_principal(actor_id=machine.owner_user_id, principal_id=machine.id)
    repository.set_principal_state.assert_awaited_once_with(
        machine.id, "revoked", actor_id=machine.owner_user_id, reason="admin_revoked"
    )


@pytest.mark.asyncio
async def test_authenticate_bearer_builds_human_actor_from_current_grant() -> None:
    subject, repository, _, kb, _ = service()
    registered = client()
    approved = grant(registered)
    token = AccessTokenRecord(
        id=uuid4(),
        token_digest="digest",
        grant_id=approved.id,
        principal_id=None,
        client_id=registered.id,
        canonical_resource=RESOURCE,
        scopes=SCOPES,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        security_stamp="stamp-1",
    )
    repository.load_access_token.return_value = token
    repository.load_grant.return_value = approved

    actor = await subject.authenticate_bearer("raw-access", source_ip="127.0.0.1")

    assert actor.actor_type == "human"
    assert actor.user_id == "user-1"
    # Bearer validation checks token validity only; KB access is per tool call.
    kb.list_knowledge_bases.assert_not_awaited()
    repository.touch_access_token.assert_awaited_once_with(token.id)


@pytest.mark.asyncio
async def test_authenticate_bearer_rejects_expired_grant() -> None:
    subject, repository, _, _, _ = service()
    registered = client()
    stale = grant(registered)
    stale.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    token = AccessTokenRecord(
        id=uuid4(),
        token_digest="digest",
        grant_id=stale.id,
        principal_id=None,
        client_id=registered.id,
        canonical_resource=RESOURCE,
        scopes=SCOPES,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        security_stamp="stamp-1",
    )
    repository.load_access_token.return_value = token
    repository.load_grant.return_value = stale

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.authenticate_bearer("raw-access", source_ip="127.0.0.1")
    assert exc.value.reason == "invalid_token"


@pytest.mark.asyncio
async def test_authorize_tool_enforces_scope_membership_and_role() -> None:
    subject, repository, _, kb, _ = service()
    machine = principal(scopes=("mcp:knowledge:read", "mcp:knowledge:write"))
    repository.load_service_principal.return_value = machine
    actor = McpActor(
        actor_type="service_principal",
        principal_id=str(machine.id),
        scopes=("mcp:knowledge:read", "mcp:knowledge:write"),
        correlationId="corr-1",
    )

    # Scope gate first: kb_ask is never granted to principals.
    with pytest.raises(McpAuthorizationError) as denied:
        await subject.authorize_tool(actor, "kb_ask", target_kb_id="kb-editor")
    assert denied.value.reason == "insufficient_scope"
    assert repository.append_audit.await_args_list[-1].args[1] == "mcp.tool.denied"

    # Unknown tools are audited under a safe name.
    with pytest.raises(McpAuthorizationError):
        await subject.authorize_tool(actor, "attacker-controlled-" * 100)
    assert repository.append_audit.await_args_list[-1].kwargs["metadata"]["tool"] == "unknown"

    # Reads pass on a viewer KB; the owner's membership decides for principals.
    await subject.authorize_tool(actor, "kb_get_note", target_kb_id="kb-viewer")
    kb.list_knowledge_bases.assert_awaited_with(machine.owner_user_id)
    assert repository.append_audit.await_args_list[-1].args[1] == "mcp.tool.allowed"
    assert repository.append_audit.await_args_list[-1].kwargs["metadata"] == {
        "tool": "kb_get_note",
        "kb_id": "kb-viewer",
    }

    # Writes require editor or better: viewer KB denies, editor KB allows.
    with pytest.raises(McpAuthorizationError) as read_only:
        await subject.authorize_tool(actor, "kb_mkdir", target_kb_id="kb-viewer")
    assert read_only.value.reason == "policy_denied"
    await subject.authorize_tool(actor, "kb_mkdir", target_kb_id="kb-editor")
    assert repository.append_audit.await_args_list[-1].args[1] == "mcp.tool.allowed"

    # A KB the owner is not a member of is inaccessible.
    with pytest.raises(McpAuthorizationError) as foreign:
        await subject.authorize_tool(actor, "kb_get_note", target_kb_id="kb-foreign")
    assert foreign.value.reason == "policy_denied"


@pytest.mark.asyncio
async def test_authorize_tool_denies_inactive_principal_owner() -> None:
    subject, repository, _, _, _ = service()
    repository.load_service_principal.return_value = None
    actor = McpActor(
        actor_type="service_principal",
        principal_id=str(uuid4()),
        scopes=("mcp:knowledge:read",),
    )

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.authorize_tool(actor, "kb_get_note", target_kb_id="kb-editor")
    assert exc.value.reason == "policy_denied"


@pytest.mark.asyncio
async def test_authorize_tool_human_uses_own_membership() -> None:
    subject, _, _, kb, _ = service()
    actor = McpActor(
        actor_type="human",
        user_id="user-1",
        scopes=("mcp:knowledge:ask",),
    )

    await subject.authorize_tool(actor, "kb_ask", target_kb_id="kb-viewer")
    kb.list_knowledge_bases.assert_awaited_once_with("user-1")


@pytest.mark.asyncio
async def test_effective_user_id_resolves_principal_to_owner() -> None:
    subject, repository, _, _, _ = service()
    machine = principal()
    repository.load_service_principal.return_value = machine
    actor = McpActor(
        actor_type="service_principal",
        principal_id=str(machine.id),
        scopes=("mcp:knowledge:read",),
    )

    assert await subject.effective_user_id(actor) == "owner-1"

    human = McpActor(actor_type="human", user_id="user-1", scopes=("mcp:knowledge:read",))
    assert await subject.effective_user_id(human) == "user-1"

    repository.load_service_principal.return_value = None
    with pytest.raises(McpAuthorizationError):
        await subject.effective_user_id(actor)


@pytest.mark.asyncio
async def test_concurrency_denial_maps_to_safe_rate_limit_and_release_is_idempotent() -> None:
    subject, repository, _, _, _ = service()
    repository.acquire_concurrency_lease.return_value = None
    actor = McpActor(
        actor_type="human",
        user_id="user-1",
        scopes=("mcp:knowledge-bases:read",),
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


def credential_record(principal_record: ServicePrincipalRecord) -> CredentialRecord:
    return CredentialRecord(
        id=uuid4(),
        principal_id=principal_record.id,
        credential_id="key-1",
        digest="digest",
        secret_prefix="mcpsc_123",
        expires_at=principal_record.expires_at,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_authenticate_bearer_accepts_service_credential_directly() -> None:
    subject, repository, _, _, _ = service()
    machine = principal()
    credential = credential_record(machine)
    repository.load_access_token.return_value = None
    repository.resolve_credential_bearer.return_value = (credential, machine)

    actor = await subject.authenticate_bearer("credential-secret", source_ip="127.0.0.1")

    assert actor.actor_type == "service_principal"
    assert actor.principal_id == str(machine.id)
    assert actor.scopes == machine.scopes
    assert actor.token_id == str(credential.id)
    assert actor.concurrency_limit == machine.concurrency_limit
    repository.resolve_credential_bearer.assert_awaited_once_with(
        "credential-secret", correlation_id=None
    )
    # Principal-level MCP bucket and per-secret tool bucket both apply.
    repository.rate_allowed.assert_any_await(
        "service", "mcp_request", f"{machine.id}:127.0.0.1", limit=machine.rate_limit
    )
    # No access-token row backs a credential, so it is never touched.
    repository.touch_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_bearer_rejects_unknown_credential_secret() -> None:
    subject, repository, _, _, _ = service()
    repository.load_access_token.return_value = None
    repository.resolve_credential_bearer.return_value = None

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.authenticate_bearer("wrong-secret", source_ip="127.0.0.1")

    assert exc.value.reason == "invalid_token"


@pytest.mark.asyncio
async def test_authenticate_bearer_credential_respects_cidr_allowlist() -> None:
    subject, repository, _, _, _ = service()
    machine = principal()
    machine.cidr_allowlist = ("10.0.0.0/8",)
    repository.load_access_token.return_value = None
    repository.resolve_credential_bearer.return_value = (credential_record(machine), machine)

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.authenticate_bearer("credential-secret", source_ip="127.0.0.1")

    assert exc.value.reason == "network_denied"
    audit = repository.append_audit.await_args
    assert audit.args[1] == "mcp.network.denied"
    assert "credential-secret" not in str(audit)


@pytest.mark.asyncio
async def test_authenticate_bearer_credential_is_rate_limited_per_principal() -> None:
    subject, repository, _, _, _ = service()
    machine = principal()
    repository.load_access_token.return_value = None
    repository.resolve_credential_bearer.return_value = (credential_record(machine), machine)
    repository.rate_allowed = AsyncMock(return_value=False)

    with pytest.raises(McpAuthorizationError) as exc:
        await subject.authenticate_bearer("credential-secret", source_ip="127.0.0.1")

    assert exc.value.reason == "rate_limited"
