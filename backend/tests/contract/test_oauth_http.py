"""ASGI contracts for OAuth discovery, protocol errors, and MCP challenge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from ima.api.app import create_app
from ima.api.oauth import redirect_with
from ima.application.mcp import AuthenticatedMcpApp, McpRuntime
from ima.application.mcp_contracts import McpActor
from ima.application.oauth import (
    AuthorizationCodeResult,
    McpAuthorizationError,
    TokenResult,
)
from ima.config import Settings

ORIGIN = "https://ima.example.test"
RESOURCE = f"{ORIGIN}/mcp"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def app_client(*, legacy_alias: bool = False) -> tuple[TestClient, object]:
    app = create_app(
        Settings(
            environment="test",
            public_origin=ORIGIN,
            mcp_legacy_alias_enabled=legacy_alias,
        )
    )
    oauth = SimpleNamespace(
        begin_authorization=AsyncMock(),
        issue_authorization_code=AsyncMock(),
        exchange_authorization_code=AsyncMock(),
        refresh_access_token=AsyncMock(),
        exchange_service_credential=AsyncMock(),
        authenticate_bearer=AsyncMock(),
        list_service_principals=AsyncMock(),
        get_service_principal=AsyncMock(),
        create_service_principal=AsyncMock(),
        rotate_service_credential=AsyncMock(),
        revoke_service_credential=AsyncMock(),
        revoke_service_principal=AsyncMock(),
        repository=SimpleNamespace(append_audit=AsyncMock(), find_client_by_public_id=AsyncMock()),
    )
    app.state.mcp_authorization_service = oauth
    app.state.mcp_runtime_box["value"] = McpRuntime(
        authorization=oauth,
        workspace=SimpleNamespace(),
        knowledge=SimpleNamespace(),
        storage=SimpleNamespace(),
        search=SimpleNamespace(),
    )
    app.state.mcp_runtime_box["value"] = SimpleNamespace(authorization=oauth)
    app.state.identity_service = SimpleNamespace(current_session=AsyncMock(return_value=None))
    return TestClient(app, base_url=ORIGIN), oauth


def test_discovery_is_canonical_and_does_not_advertise_registration() -> None:
    client, _ = app_client()
    protected = client.get("/.well-known/oauth-protected-resource/mcp")
    assert protected.status_code == 200
    assert protected.json() == {
        "resource": RESOURCE,
        "authorization_servers": [ORIGIN],
        "scopes_supported": [
            "mcp:workspaces:read",
            "mcp:knowledge:read",
            "mcp:knowledge:search",
            "mcp:knowledge:ask",
            "mcp:knowledge:write",
        ],
        "bearer_methods_supported": ["header"],
    }
    authorization = client.get("/.well-known/oauth-authorization-server")
    assert authorization.status_code == 200
    payload = authorization.json()
    assert payload["issuer"] == ORIGIN
    assert payload["authorization_endpoint"] == f"{ORIGIN}/oauth/authorize"
    assert payload["grant_types_supported"] == ["authorization_code", "refresh_token"]
    assert payload["code_challenge_methods_supported"] == ["S256"]
    assert payload["token_endpoint_auth_methods_supported"] == ["none"]
    assert payload["revocation_endpoint_auth_methods_supported"] == ["none"]
    assert payload["authorization_response_iss_parameter_supported"] is True
    assert "registration_endpoint" not in payload


def test_mcp_missing_or_query_bearer_returns_resource_metadata_challenge() -> None:
    client, _ = app_client()
    response = client.get("/mcp")
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith(
        f'Bearer resource_metadata="{ORIGIN}/.well-known/oauth-protected-resource/mcp", scope="'
    )
    query = client.get("/mcp?access_token=must-not-be-used")
    assert query.status_code == 401
    assert 'error="invalid_token"' in query.headers["www-authenticate"]
    assert "must-not-be-used" not in query.text
    mixed_case = client.get("/mcp?Authorization=must-not-be-used")
    assert mixed_case.status_code == 401
    assert "must-not-be-used" not in mixed_case.text


def test_legacy_alias_is_controlled_but_uses_canonical_challenge() -> None:
    disabled, _ = app_client()
    assert disabled.get("/api/mcp").status_code == 404
    enabled, _ = app_client(legacy_alias=True)
    response = enabled.get("/api/mcp")
    assert response.status_code == 401
    assert (
        f"{ORIGIN}/.well-known/oauth-protected-resource/mcp" in response.headers["www-authenticate"]
    )


def test_authenticated_python_alias_emits_safe_deprecation_audit() -> None:
    client, oauth = app_client(legacy_alias=True)
    oauth.authenticate_bearer.return_value = McpActor(
        actor_type="service_principal",
        principal_id="principal-1",
        workspace_id="workspace-1",
        scopes=("mcp:knowledge:read",),
    )

    authenticated = next(
        route.app
        for route in client.app.routes
        if isinstance(getattr(route, "app", None), AuthenticatedMcpApp)
    )

    async def downstream(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    authenticated.app = downstream
    response = client.get("/api/mcp", headers={"Authorization": "Bearer opaque-secret"})
    assert response.status_code == 204

    audit = oauth.repository.append_audit.await_args
    assert audit.args == (None, "legacy.mcp.alias_used", "success")
    assert audit.kwargs == {
        "target_type": "service_principal",
        "target_id": "principal-1",
        "metadata": {"canonicalResource": "/mcp"},
        "correlation_id": None,
    }
    assert "opaque-secret" not in str(audit)


def test_authenticated_mcp_policy_and_rate_failures_keep_distinct_status() -> None:
    client, oauth = app_client()
    oauth.authenticate_bearer.side_effect = McpAuthorizationError("policy_denied", "Policy denied")
    denied = client.get("/mcp", headers={"Authorization": "Bearer opaque"})
    assert denied.status_code == 403
    assert 'error="insufficient_scope"' in denied.headers["www-authenticate"]
    oauth.authenticate_bearer.side_effect = McpAuthorizationError("rate_limited", "Rate exceeded")
    limited = client.get("/mcp", headers={"Authorization": "Bearer opaque"})
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"


def test_token_uses_form_semantics_and_no_store_headers() -> None:
    client, oauth = app_client()
    oauth.exchange_authorization_code.return_value = TokenResult(
        access_token="access-value",
        refresh_token="refresh-value",
        expires_in=600,
        scope="mcp:knowledge:read",
    )
    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "opaque-code",
            "client_id": "desktop",
            "redirect_uri": "http://localhost:8765/callback",
            "resource": RESOURCE,
            "code_verifier": "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk",
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["token_type"] == "Bearer"
    assert response.json()["access_token"] == "access-value"
    oauth.exchange_authorization_code.assert_awaited_once()


def test_token_error_is_oauth_json_and_does_not_echo_secret() -> None:
    client, oauth = app_client()
    oauth.exchange_authorization_code.side_effect = McpAuthorizationError(
        "verifier_mismatch", "Invalid PKCE verifier"
    )
    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "opaque-code",
            "client_id": "desktop",
            "redirect_uri": "http://localhost:8765/callback",
            "resource": RESOURCE,
            "code_verifier": "secret-verifier-value-that-must-not-echo-123456789",
        },
    )
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["error"] == "invalid_grant"
    assert "secret-verifier" not in response.text


def test_token_rejects_non_form_duplicate_and_query_parameters() -> None:
    client, oauth = app_client()
    json_response = client.post("/oauth/token", json={"grant_type": "refresh_token"})
    assert json_response.status_code == 400
    assert json_response.json()["error"] == "invalid_request"
    duplicate = client.post(
        "/oauth/token",
        content="grant_type=refresh_token&grant_type=authorization_code",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert duplicate.status_code == 400
    query = client.post(
        "/oauth/token?code=must-not-echo",
        data={"grant_type": "authorization_code"},
    )
    assert query.status_code == 400
    assert "must-not-echo" not in query.text
    oauth.exchange_authorization_code.assert_not_awaited()


def test_untrusted_forwarded_source_is_not_used_for_service_network_policy() -> None:
    client, oauth = app_client()
    oauth.exchange_service_credential.return_value = TokenResult(
        access_token="access", expires_in=600, scope="mcp:knowledge:read"
    )
    response = client.post(
        "/oauth/token",
        headers={"X-Forwarded-For": "10.9.8.7"},
        data={
            "grant_type": "urn:ima:params:oauth:grant-type:service-credential",
            "credential_id": "key-1",
            "credential": "secret",
        },
    )
    assert response.status_code == 200
    assert oauth.exchange_service_credential.await_args.kwargs["source_ip"] != "10.9.8.7"


def test_problem_details_never_echo_oauth_query_secrets() -> None:
    client, _ = app_client()
    response = client.get(
        "/oauth/authorize",
        params={"state": "secret-state", "code_challenge": "secret-challenge"},
    )
    assert response.status_code == 401
    assert response.json()["instance"] == "/oauth/authorize"
    assert "secret-state" not in response.text
    assert "secret-challenge" not in response.text


def test_redirect_replaces_reserved_parameters_and_rejects_fragments() -> None:
    target = redirect_with(
        "http://localhost:8765/callback?existing=1&code=stale&state=stale",
        code="fresh",
        state="fresh-state",
    )
    assert target == "http://localhost:8765/callback?existing=1&code=fresh&state=fresh-state"
    with pytest.raises(ValueError):
        redirect_with("http://localhost:8765/callback#fragment", code="fresh")


def test_consent_preview_and_submit_keep_exact_redirect_state_and_issuer() -> None:
    client, oauth = app_client()
    app = client.app
    session = {
        "csrf_digest": "csrf-digest",
        "recent_auth_at": datetime.now(UTC),
    }
    identity = SimpleNamespace(
        current_session=AsyncMock(return_value=(session, SimpleNamespace(id="user-1"))),
        _session_digest=Mock(return_value="csrf-digest"),
    )
    app.state.identity_service = identity
    expires = datetime.now(UTC) + timedelta(days=1)
    context = SimpleNamespace(
        client=SimpleNamespace(client_id="desktop", client_name="Desktop"),
        redirect_uri="http://localhost:8765/callback?existing=1",
        resource=RESOURCE,
        workspace_id="workspace-1",
        folder_root_id=None,
        scopes=("mcp:knowledge:read",),
        grant_expires_at=expires,
        consent_required=True,
        state="state-1",
    )
    oauth.begin_authorization.return_value = context
    oauth.issue_authorization_code.return_value = AuthorizationCodeResult(
        code="one-time-code", state="state-1", issuer=ORIGIN
    )
    query = {
        "response_type": "code",
        "client_id": "desktop",
        "redirect_uri": context.redirect_uri,
        "resource": RESOURCE,
        "workspace_id": "workspace-1",
        "scope": "mcp:knowledge:read",
        "state": "state-1",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
        "expires_at": expires.isoformat(),
    }
    preview = client.get("/oauth/authorize", params=query)
    assert preview.status_code == 200
    assert preview.json()["consentRequired"] is True

    client.cookies.set("ima_csrf", "csrf-value")
    response = client.post(
        "/oauth/authorize",
        headers={"Origin": ORIGIN, "X-CSRF-Token": "csrf-value"},
        json={
            "approved": True,
            "clientId": "desktop",
            "redirectUri": context.redirect_uri,
            "resource": RESOURCE,
            "workspaceId": "workspace-1",
            "folderRootId": None,
            "scope": "mcp:knowledge:read",
            "state": "state-1",
            "codeChallenge": CHALLENGE,
            "codeChallengeMethod": "S256",
            "expiresAt": expires.isoformat(),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["location"] == (
        "http://localhost:8765/callback?existing=1&code=one-time-code"
        f"&state=state-1&iss={ORIGIN.replace(':', '%3A').replace('/', '%2F')}"
    )


def test_form_decision_returns_to_local_consent_when_recent_auth_is_required() -> None:
    client, oauth = app_client()
    session = {"csrf_digest": "csrf-digest"}
    client.app.state.identity_service = SimpleNamespace(
        current_session=AsyncMock(return_value=(session, SimpleNamespace(id="user-1"))),
        _session_digest=Mock(return_value="csrf-digest"),
    )
    expires = datetime.now(UTC) + timedelta(days=1)
    client.cookies.set("ima_csrf", "csrf-value")

    response = client.post(
        "/oauth/authorize/decision",
        headers={"Origin": ORIGIN},
        data={
            "approved": "true",
            "client_id": "desktop",
            "redirect_uri": "http://localhost:8765/callback",
            "resource": RESOURCE,
            "workspace_id": "workspace-1",
            "folder_root_id": "",
            "scope": "mcp:knowledge:read",
            "state": "state-1",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "expires_at": expires.isoformat(),
            "csrf_token": "csrf-value",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/oauth/consent?")
    assert "ui_error=recent_auth" in response.headers["location"]
    assert "attacker.example" not in response.headers["location"]
    oauth.issue_authorization_code.assert_not_awaited()


def test_consent_denial_does_not_require_recent_authentication() -> None:
    client, oauth = app_client()
    session = {"csrf_digest": "csrf-digest"}
    client.app.state.identity_service = SimpleNamespace(
        current_session=AsyncMock(return_value=(session, SimpleNamespace(id="user-1"))),
        _session_digest=Mock(return_value="csrf-digest"),
    )
    context = SimpleNamespace(
        client=SimpleNamespace(client_id="desktop"),
        redirect_uri="http://localhost:8765/callback",
        state="state-1",
    )
    oauth.begin_authorization.return_value = context
    client.cookies.set("ima_csrf", "csrf-value")

    response = client.post(
        "/oauth/authorize/decision",
        headers={"Origin": ORIGIN},
        data={
            "approved": "false",
            "client_id": "desktop",
            "redirect_uri": context.redirect_uri,
            "resource": RESOURCE,
            "workspace_id": "workspace-1",
            "scope": "mcp:knowledge:read",
            "state": context.state,
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "csrf_token": "csrf-value",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith(
        "http://localhost:8765/callback?error=access_denied"
    )
    oauth.issue_authorization_code.assert_not_awaited()


def test_authorize_error_redirects_only_to_an_exact_registered_uri() -> None:
    client, oauth = app_client()
    client.app.state.identity_service = SimpleNamespace(
        current_session=AsyncMock(return_value=({}, SimpleNamespace(id="user-1")))
    )
    registered = SimpleNamespace(
        is_enabled=True,
        redirect_uris=("http://localhost:8765/callback",),
    )
    oauth.repository.find_client_by_public_id.return_value = registered
    oauth.begin_authorization.side_effect = McpAuthorizationError(
        "invalid_scope", "Unsupported scope"
    )
    common = {
        "response_type": "code",
        "client_id": "desktop",
        "resource": RESOURCE,
        "workspace_id": "workspace-1",
        "scope": "bad:scope",
        "state": "state-1",
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    safe = client.get(
        "/oauth/authorize",
        params={**common, "redirect_uri": registered.redirect_uris[0]},
        follow_redirects=False,
    )
    assert safe.status_code == 303
    assert safe.headers["location"].startswith(
        "http://localhost:8765/callback?error=invalid_scope&iss="
    )
    assert "state=state-1" in safe.headers["location"]

    unsafe = client.get(
        "/oauth/authorize",
        params={**common, "redirect_uri": "https://attacker.example/callback"},
        follow_redirects=False,
    )
    assert unsafe.status_code == 400
    assert "location" not in unsafe.headers


def test_openapi_has_stable_public_and_admin_operations() -> None:
    client, _ = app_client()
    schema = client.app.openapi()
    assert schema["paths"]["/oauth/token"]["post"]["operationId"] == "oauthToken"
    assert (
        "application/x-www-form-urlencoded"
        in schema["paths"]["/oauth/token"]["post"]["requestBody"]["content"]
    )
    assert (
        schema["paths"]["/api/v1/workspaces/{workspace_id}/service-principals"]["post"][
            "operationId"
        ]
        == "createServicePrincipal"
    )
    assert "/mcp" not in schema["paths"]
    assert (
        schema["paths"]["/api/v1/oauth/grants"]["get"]["operationId"] == "listConnectedOAuthGrants"
    )
    detail = schema["components"]["schemas"]["ServicePrincipalDetailResponse"]
    assert "credentials" in detail["properties"]
    assert "digest" not in str(detail).lower()


def test_one_time_service_secret_response_is_no_store_and_digest_free() -> None:
    client, oauth = app_client()
    session = {"csrf_digest": "csrf-digest", "recent_auth_at": datetime.now(UTC)}
    client.app.state.identity_service = SimpleNamespace(
        current_session=AsyncMock(return_value=(session, SimpleNamespace(id="admin-1"))),
        _session_digest=Mock(return_value="csrf-digest"),
    )
    expires = datetime.now(UTC) + timedelta(days=1)
    principal_id = "11111111-1111-1111-1111-111111111111"
    credential_id = "22222222-2222-2222-2222-222222222222"
    oauth.create_service_principal.return_value = SimpleNamespace(
        secret="one-time-secret",
        credential=SimpleNamespace(
            id=credential_id,
            principal_id=principal_id,
            credential_id="key-1",
            secret_prefix="mcpsc_123",
            expires_at=expires,
            created_at=datetime.now(UTC),
            revoked_at=None,
            last_used_at=None,
        ),
        principal=SimpleNamespace(
            id=principal_id,
            workspace_id="workspace-1",
            folder_root_id=None,
            display_name="CI",
            purpose="Ingestion",
            owner_user_id="owner-1",
            scopes=("mcp:knowledge:read",),
            state="active",
            expires_at=expires,
            rate_limit=10,
            concurrency_limit=2,
            cidr_allowlist=(),
        ),
    )
    client.cookies.set("ima_csrf", "csrf-value")
    response = client.post(
        "/api/v1/workspaces/workspace-1/service-principals",
        headers={"Origin": ORIGIN, "X-CSRF-Token": "csrf-value"},
        json={
            "displayName": "CI",
            "purpose": "Ingestion",
            "ownerUserId": "owner-1",
            "scopes": ["mcp:knowledge:read"],
            "expiresAt": expires.isoformat(),
            "rateLimit": 10,
            "concurrencyLimit": 2,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["secret"] == "one-time-secret"
    assert "digest" not in response.text.casefold()


def test_auth_capabilities_reflects_registration_flag_without_auth() -> None:
    client, _ = app_client()
    client.app.state.identity_service = SimpleNamespace(
        current_session=AsyncMock(return_value=None),
        registration_enabled=AsyncMock(return_value=True),
    )
    enabled = client.get("/api/v1/auth/capabilities")
    assert enabled.status_code == 200
    assert enabled.json() == {"registration": True}

    client.app.state.identity_service = SimpleNamespace(
        current_session=AsyncMock(return_value=None),
        registration_enabled=AsyncMock(return_value=False),
    )
    disabled = client.get("/api/v1/auth/capabilities")
    assert disabled.status_code == 200
    assert disabled.json() == {"registration": False}


def test_auth_capabilities_is_advertised_with_stable_operation_id() -> None:
    client, _ = app_client()
    schema = client.app.openapi()
    operation = schema["paths"]["/api/v1/auth/capabilities"]["get"]
    assert operation["operationId"] == "authCapabilities"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"][
        "$ref"
    ].endswith("/AuthCapabilities")
