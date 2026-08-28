"""Public OAuth discovery, protocol endpoints, and service access administration."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from ima.api.oauth_contracts import (
    ConnectedGrantResponse,
    ConsentSubmit,
    ConsentView,
    CredentialIssueResponse,
    CredentialRotate,
    CredentialViewResponse,
    LifecycleResult,
    ServicePrincipalCreate,
    ServicePrincipalDetailResponse,
    ServicePrincipalResponse,
)
from ima.api.v1.auth import Current, check_csrf, check_recent_auth
from ima.application.mcp_contracts import (
    ALL_MCP_SCOPES,
    AuthorizationServerMetadata,
    ProtectedResourceMetadata,
    oauth_metadata_url,
)
from ima.application.oauth import McpAuthorizationError, McpAuthorizationService
from ima.config import Settings

public_router = APIRouter(tags=["oauth"])
admin_router = APIRouter(tags=["service-access"])
NO_STORE_HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
OAUTH_RESPONSE_PARAMETERS = frozenset(
    {"code", "error", "error_description", "error_uri", "state", "iss"}
)


def oauth_service(request: Request) -> McpAuthorizationService:
    return cast(McpAuthorizationService, request.app.state.mcp_authorization_service)


def settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def correlation(request: Request) -> str | None:
    value = request.scope.get("ima.correlation_id")
    return str(value) if value else None


def oauth_error(exc: McpAuthorizationError) -> JSONResponse:
    status = 401 if exc.reason == "invalid_client" else 400
    if exc.reason == "rate_limited":
        status = 429
    return JSONResponse(
        status_code=status,
        content={"error": exc.oauth_code.value, "error_description": exc.detail},
        headers=NO_STORE_HEADERS,
    )


def redirect_with(uri: str, **parameters: str) -> str:
    parsed = urlsplit(uri)
    if parsed.fragment:
        raise ValueError("registered OAuth redirect URI must not contain a fragment")
    query = [
        item
        for item in parse_qsl(parsed.query, keep_blank_values=True)
        if item[0] not in OAUTH_RESPONSE_PARAMETERS
    ]
    query.extend(parameters.items())
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


def set_no_store(response: Response) -> None:
    response.headers.update(NO_STORE_HEADERS)


async def authorization_error_redirect(
    request: Request,
    *,
    client_id: str | None,
    redirect_uri: str | None,
    state: str | None,
    exc: McpAuthorizationError,
) -> RedirectResponse | None:
    if not client_id or not redirect_uri:
        return None
    client = await oauth_service(request).repository.find_client_by_public_id(client_id)
    if (
        client is None
        or not client.is_enabled
        or redirect_uri not in client.redirect_uris
        or not McpAuthorizationService.redirect_is_safe(redirect_uri)
    ):
        return None
    parameters = {
        "error": exc.oauth_code.value,
        "iss": settings(request).public_origin,
    }
    if state and len(state) <= 128:
        parameters["state"] = state
    return RedirectResponse(
        redirect_with(redirect_uri, **parameters), status_code=303, headers=NO_STORE_HEADERS
    )


async def oauth_form(request: Request) -> Any:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded" or request.query_params:
        raise McpAuthorizationError(
            "invalid_request", "OAuth parameters must use form-urlencoded request bodies"
        )
    if request.headers.get("authorization"):
        raise McpAuthorizationError("invalid_client", "Client authentication is not permitted")
    return await request.form()


@public_router.get(
    "/.well-known/oauth-protected-resource",
    response_model=ProtectedResourceMetadata,
    operation_id="oauthProtectedResourceMetadata",
)
@public_router.get(
    "/.well-known/oauth-protected-resource/mcp",
    response_model=ProtectedResourceMetadata,
    operation_id="oauthProtectedResourceMetadataMcp",
)
async def protected_resource_metadata(request: Request) -> ProtectedResourceMetadata:
    configured = settings(request)
    return ProtectedResourceMetadata(
        resource=configured.mcp_resource_url,
        authorization_servers=(configured.public_origin,),
        scopes_supported=tuple(scope.value for scope in ALL_MCP_SCOPES),
        bearer_methods_supported=("header",),
    )


@public_router.get(
    "/.well-known/oauth-authorization-server",
    response_model=AuthorizationServerMetadata,
    operation_id="oauthAuthorizationServerMetadata",
)
async def authorization_server_metadata(request: Request) -> AuthorizationServerMetadata:
    configured = settings(request)
    return AuthorizationServerMetadata(
        issuer=configured.public_origin,
        authorization_endpoint=oauth_metadata_url(configured.public_origin, "/oauth/authorize"),
        token_endpoint=oauth_metadata_url(configured.public_origin, "/oauth/token"),
        revocation_endpoint=oauth_metadata_url(configured.public_origin, "/oauth/revoke"),
        response_types_supported=("code",),
        grant_types_supported=("authorization_code", "refresh_token"),
        code_challenge_methods_supported=("S256",),
        token_endpoint_auth_methods_supported=("none",),
        revocation_endpoint_auth_methods_supported=("none",),
        scopes_supported=tuple(scope.value for scope in ALL_MCP_SCOPES),
    )


async def authorization_context(
    request: Request,
    current: Current,
    *,
    response_type: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    resource: str | None,
    workspace_id: str | None,
    folder_root_id: str | None,
    scope: str | None,
    state: str | None,
    code_challenge: str | None,
    code_challenge_method: str | None,
    expires_at: datetime | None,
) -> Any:
    bounded_values = (
        (client_id, 128),
        (redirect_uri, 512),
        (resource, 512),
        (workspace_id, 32),
        (folder_root_id, 32),
        (scope, 512),
        (state, 128),
        (code_challenge, 128),
        (code_challenge_method, 16),
    )
    if any(value is not None and len(value) > limit for value, limit in bounded_values):
        raise McpAuthorizationError("invalid_request", "Authorization parameter is oversized")
    if response_type is None or not all(
        (client_id, redirect_uri, resource, workspace_id, scope, state, code_challenge)
    ):
        raise McpAuthorizationError("invalid_request", "Incomplete authorization request")
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(
            seconds=settings(request).oauth_refresh_absolute_seconds
        )
    return await oauth_service(request).begin_authorization(
        user_id=current[1].id,
        response_type=response_type,
        client_id=cast(str, client_id),
        redirect_uri=cast(str, redirect_uri),
        resource=cast(str, resource),
        workspace_id=cast(str, workspace_id),
        folder_root_id=folder_root_id,
        scope=cast(str, scope),
        state=cast(str, state),
        code_challenge=cast(str, code_challenge),
        code_challenge_method=code_challenge_method or "",
        grant_expires_at=expires_at,
        source_bucket=source(request),
    )


@public_router.get(
    "/oauth/authorize", response_model=ConsentView, operation_id="oauthAuthorizePreview"
)
async def authorize_preview(
    request: Request,
    response: Response,
    current: Current,
    response_type: Annotated[str | None, Query()] = None,
    client_id: Annotated[str | None, Query()] = None,
    redirect_uri: Annotated[str | None, Query()] = None,
    resource: Annotated[str | None, Query()] = None,
    workspace_id: Annotated[str | None, Query()] = None,
    folder_root_id: Annotated[str | None, Query()] = None,
    scope: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str | None, Query()] = None,
    expires_at: Annotated[datetime | None, Query()] = None,
) -> ConsentView | RedirectResponse | JSONResponse:
    set_no_store(response)
    try:
        context = await authorization_context(
            request,
            current,
            response_type=response_type,
            client_id=client_id,
            redirect_uri=redirect_uri,
            resource=resource,
            workspace_id=workspace_id,
            folder_root_id=folder_root_id,
            scope=scope,
            state=state,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            expires_at=expires_at,
        )
    except McpAuthorizationError as exc:
        redirected = await authorization_error_redirect(
            request,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            exc=exc,
        )
        if redirected is not None:
            return redirected
        return oauth_error(exc)
    if "text/html" in request.headers.get("accept", ""):
        target = "/oauth/consent"
        if request.url.query:
            target += f"?{request.url.query}"
        return RedirectResponse(target, status_code=303, headers=NO_STORE_HEADERS)
    return ConsentView(
        clientId=context.client.client_id,
        clientName=context.client.client_name,
        redirectUri=context.redirect_uri,
        resource=context.resource,
        workspaceId=context.workspace_id,
        folderRootId=context.folder_root_id,
        scopes=context.scopes,
        writeAccess="mcp:knowledge:write" in context.scopes,
        expiresAt=context.grant_expires_at,
        consentRequired=context.consent_required,
    )


@public_router.post("/oauth/authorize", response_model=None, operation_id="oauthAuthorizeSubmit")
async def authorize_submit(
    payload: ConsentSubmit, request: Request, current: Current
) -> RedirectResponse | JSONResponse:
    session, user = current
    check_csrf(request, session)
    if payload.approved:
        check_recent_auth(request, session)
    context: Any | None = None
    try:
        context = await authorization_context(
            request,
            current,
            response_type="code",
            client_id=payload.client_id,
            redirect_uri=payload.redirect_uri,
            resource=payload.resource,
            workspace_id=payload.workspace_id,
            folder_root_id=payload.folder_root_id,
            scope=payload.scope,
            state=payload.state,
            code_challenge=payload.code_challenge,
            code_challenge_method=payload.code_challenge_method,
            expires_at=payload.expires_at,
        )
        if not payload.approved:
            await oauth_service(request).repository.append_audit(
                user.id,
                "oauth.consent.denied",
                "failure",
                target_type="oauth_client",
                target_id=context.client.client_id,
                reason="access_denied",
                correlation_id=correlation(request),
            )
            target = redirect_with(
                context.redirect_uri,
                error="access_denied",
                state=context.state,
                iss=settings(request).public_origin,
            )
            return RedirectResponse(target, status_code=303, headers=NO_STORE_HEADERS)
        issued = await oauth_service(request).issue_authorization_code(
            context, consent_approved=True, correlation_id=correlation(request)
        )
    except McpAuthorizationError as exc:
        if context is not None:
            target = redirect_with(
                context.redirect_uri,
                error=exc.oauth_code.value,
                state=context.state,
                iss=settings(request).public_origin,
            )
            return RedirectResponse(target, status_code=303, headers=NO_STORE_HEADERS)
        redirected = await authorization_error_redirect(
            request,
            client_id=payload.client_id,
            redirect_uri=payload.redirect_uri,
            state=payload.state,
            exc=exc,
        )
        if redirected is not None:
            return redirected
        return oauth_error(exc)
    target = redirect_with(
        context.redirect_uri,
        code=issued.code,
        state=issued.state,
        iss=issued.issuer,
    )
    return RedirectResponse(target, status_code=303, headers=NO_STORE_HEADERS)


@public_router.post(
    "/oauth/authorize/decision",
    response_model=None,
    include_in_schema=False,
)
async def authorize_form_decision(
    request: Request, current: Current
) -> RedirectResponse | JSONResponse:
    try:
        form = await oauth_form(request)
        payload = ConsentSubmit.model_validate(
            {
                "approved": form_string(form, "approved") == "true",
                "clientId": form_string(form, "client_id") or "",
                "redirectUri": form_string(form, "redirect_uri") or "",
                "resource": form_string(form, "resource") or "",
                "workspaceId": form_string(form, "workspace_id") or "",
                "folderRootId": form_string(form, "folder_root_id"),
                "scope": form_string(form, "scope") or "",
                "state": form_string(form, "state") or "",
                "codeChallenge": form_string(form, "code_challenge") or "",
                "codeChallengeMethod": form_string(form, "code_challenge_method") or "S256",
                "expiresAt": form_string(form, "expires_at") or "",
            }
        )
        csrf = form_string(form, "csrf_token") or ""
    except (McpAuthorizationError, ValueError) as exc:
        error = (
            exc
            if isinstance(exc, McpAuthorizationError)
            else McpAuthorizationError("invalid_request", "Invalid authorization decision")
        )
        return oauth_error(error)
    cloned_scope = dict(request.scope)
    headers = [
        (key, value)
        for key, value in request.scope.get("headers", [])
        if key.lower() != b"x-csrf-token"
    ]
    headers.append((b"x-csrf-token", csrf.encode("utf-8")))
    cloned_scope["headers"] = headers
    try:
        return await authorize_submit(payload, Request(cloned_scope, request.receive), current)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        query = urlencode(
            {
                "client_id": payload.client_id,
                "redirect_uri": payload.redirect_uri,
                "resource": payload.resource,
                "workspace_id": payload.workspace_id,
                "folder_root_id": payload.folder_root_id or "",
                "scope": payload.scope,
                "state": payload.state,
                "code_challenge": payload.code_challenge,
                "code_challenge_method": payload.code_challenge_method,
                "expires_at": payload.expires_at.isoformat(),
                "ui_error": "recent_auth",
            }
        )
        return RedirectResponse(
            f"/oauth/consent?{query}", status_code=303, headers=NO_STORE_HEADERS
        )


def form_string(form: Any, name: str) -> str | None:
    if len(form.getlist(name)) > 1:
        raise McpAuthorizationError("invalid_request", f"Duplicate {name} parameter")
    value = form.get(name)
    if isinstance(value, str) and len(value) > 4096:
        raise McpAuthorizationError("invalid_request", f"Oversized {name} parameter")
    return value if isinstance(value, str) and value else None


@public_router.post(
    "/oauth/token",
    response_model=None,
    operation_id="oauthToken",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "required": ["grant_type"],
                        "properties": {
                            "grant_type": {"type": "string"},
                            "code": {"type": "string", "writeOnly": True},
                            "client_id": {"type": "string"},
                            "redirect_uri": {"type": "string", "format": "uri"},
                            "resource": {"type": "string", "format": "uri"},
                            "code_verifier": {"type": "string", "writeOnly": True},
                            "refresh_token": {"type": "string", "writeOnly": True},
                            "credential_id": {"type": "string"},
                            "credential": {"type": "string", "writeOnly": True},
                            "scope": {"type": "string"},
                        },
                    }
                }
            },
        }
    },
)
async def token(request: Request) -> JSONResponse:
    try:
        form = await oauth_form(request)
        grant_type = form_string(form, "grant_type")
        if grant_type == "authorization_code":
            required = {
                key: form_string(form, key)
                for key in ("code", "client_id", "redirect_uri", "resource", "code_verifier")
            }
            if any(value is None for value in required.values()):
                raise McpAuthorizationError("invalid_request", "Incomplete token request")
            result = await oauth_service(request).exchange_authorization_code(
                code=cast(str, required["code"]),
                client_id=cast(str, required["client_id"]),
                redirect_uri=cast(str, required["redirect_uri"]),
                resource=cast(str, required["resource"]),
                code_verifier=cast(str, required["code_verifier"]),
                source_bucket=source(request),
                correlation_id=correlation(request),
            )
        elif grant_type == "refresh_token":
            required = {
                key: form_string(form, key) for key in ("refresh_token", "client_id", "resource")
            }
            if any(value is None for value in required.values()):
                raise McpAuthorizationError("invalid_request", "Incomplete refresh request")
            result = await oauth_service(request).refresh_access_token(
                refresh_token=cast(str, required["refresh_token"]),
                client_id=cast(str, required["client_id"]),
                resource=cast(str, required["resource"]),
                scope=form_string(form, "scope"),
                source_bucket=source(request),
                correlation_id=correlation(request),
            )
        elif grant_type == "urn:ima:params:oauth:grant-type:service-credential":
            credential_id = form_string(form, "credential_id")
            secret = form_string(form, "credential")
            if credential_id is None or secret is None:
                raise McpAuthorizationError("invalid_request", "Incomplete credential request")
            requested_scope = form_string(form, "scope")
            result = await oauth_service(request).exchange_service_credential(
                credential_id=credential_id,
                secret=secret,
                source_ip=source(request),
                requested_scopes=(tuple(requested_scope.split()) if requested_scope else None),
                correlation_id=correlation(request),
            )
        else:
            raise McpAuthorizationError("unsupported_grant_type", "Grant type is unsupported")
    except McpAuthorizationError as exc:
        return oauth_error(exc)
    content: dict[str, object] = {
        "access_token": result.access_token,
        "token_type": result.token_type,
        "expires_in": result.expires_in,
        "scope": result.scope,
    }
    if result.refresh_token is not None:
        content["refresh_token"] = result.refresh_token
    return JSONResponse(
        content=content,
        headers=NO_STORE_HEADERS,
    )


@public_router.post(
    "/oauth/revoke",
    status_code=200,
    operation_id="oauthRevoke",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/x-www-form-urlencoded": {
                    "schema": {
                        "type": "object",
                        "required": ["token", "client_id"],
                        "properties": {
                            "token": {"type": "string", "writeOnly": True},
                            "client_id": {"type": "string"},
                            "token_type_hint": {"type": "string"},
                        },
                    }
                }
            },
        }
    },
)
async def revoke(request: Request) -> Response:
    try:
        form = await oauth_form(request)
        token_value = form_string(form, "token")
        client_id = form_string(form, "client_id")
        if token_value is None or client_id is None:
            raise McpAuthorizationError("invalid_request", "Incomplete revocation request")
    except McpAuthorizationError as exc:
        return oauth_error(exc)
    client = await oauth_service(request).repository.find_client_by_public_id(client_id)
    if client is not None:
        await oauth_service(request).revoke_token(token_value)
    return Response(status_code=200, headers=NO_STORE_HEADERS)


def issue_response(value: Any) -> CredentialIssueResponse:
    return CredentialIssueResponse(
        secret=value.secret,
        credential=CredentialViewResponse.model_validate(value.credential),
        principal=ServicePrincipalResponse.model_validate(value.principal),
    )


@admin_router.get(
    "/oauth/grants",
    response_model=tuple[ConnectedGrantResponse, ...],
    operation_id="listConnectedOAuthGrants",
)
async def list_connected_grants(
    request: Request, response: Response, current: Current
) -> tuple[ConnectedGrantResponse, ...]:
    set_no_store(response)
    values = await oauth_service(request).list_connected_grants(current[1].id)
    return tuple(ConnectedGrantResponse.model_validate(value) for value in values)


@admin_router.delete(
    "/oauth/grants/{grant_id}",
    response_model=LifecycleResult,
    operation_id="revokeConnectedOAuthGrant",
)
async def revoke_connected_grant(
    grant_id: UUID, request: Request, response: Response, current: Current
) -> LifecycleResult:
    set_no_store(response)
    session, user = current
    check_csrf(request, session)
    await oauth_service(request).revoke_connected_grant(user.id, grant_id)
    return LifecycleResult()


@admin_router.get(
    "/workspaces/{workspace_id}/service-principals",
    response_model=tuple[ServicePrincipalResponse, ...],
    operation_id="listServicePrincipals",
)
async def list_service_principals(
    workspace_id: str, request: Request, response: Response, current: Current
) -> tuple[ServicePrincipalResponse, ...]:
    set_no_store(response)
    values = await oauth_service(request).list_service_principals(current[1].id, workspace_id)
    return tuple(ServicePrincipalResponse.model_validate(value) for value in values)


@admin_router.post(
    "/workspaces/{workspace_id}/service-principals",
    response_model=CredentialIssueResponse,
    operation_id="createServicePrincipal",
)
async def create_service_principal(
    workspace_id: str,
    payload: ServicePrincipalCreate,
    request: Request,
    response: Response,
    current: Current,
) -> CredentialIssueResponse:
    set_no_store(response)
    session, actor = current
    check_csrf(request, session)
    check_recent_auth(request, session)
    value = await oauth_service(request).create_service_principal(
        actor_id=actor.id,
        workspace_id=workspace_id,
        folder_root_id=payload.folder_root_id,
        display_name=payload.display_name,
        purpose=payload.purpose,
        owner_user_id=payload.owner_user_id,
        scopes=payload.scopes,
        expires_at=payload.expires_at,
        rate_limit=payload.rate_limit,
        concurrency_limit=payload.concurrency_limit,
        cidr_allowlist=payload.cidr_allowlist,
        correlation_id=correlation(request),
    )
    return issue_response(value)


@admin_router.get(
    "/workspaces/{workspace_id}/service-principals/{principal_id}",
    response_model=ServicePrincipalDetailResponse,
    operation_id="getServicePrincipal",
)
async def get_service_principal(
    workspace_id: str,
    principal_id: UUID,
    request: Request,
    response: Response,
    current: Current,
) -> ServicePrincipalDetailResponse:
    set_no_store(response)
    value = await oauth_service(request).get_service_principal(current[1].id, principal_id)
    if value.workspace_id != workspace_id:
        raise McpAuthorizationError("invalid_principal", "Service principal not found")
    credentials = await oauth_service(request).list_service_credentials(current[1].id, principal_id)
    return ServicePrincipalDetailResponse(
        **ServicePrincipalResponse.model_validate(value).model_dump(),
        credentials=tuple(
            CredentialViewResponse.model_validate(credential) for credential in credentials
        ),
    )


@admin_router.post(
    "/workspaces/{workspace_id}/service-principals/{principal_id}/credentials/{credential_id}/rotate",
    response_model=CredentialIssueResponse,
    operation_id="rotateServiceCredential",
)
async def rotate_service_credential(
    workspace_id: str,
    principal_id: UUID,
    credential_id: str,
    payload: CredentialRotate,
    request: Request,
    response: Response,
    current: Current,
) -> CredentialIssueResponse:
    set_no_store(response)
    session, actor = current
    check_csrf(request, session)
    check_recent_auth(request, session)
    principal = await oauth_service(request).get_service_principal(actor.id, principal_id)
    if principal.workspace_id != workspace_id:
        raise McpAuthorizationError("invalid_principal", "Service principal not found")
    value = await oauth_service(request).rotate_service_credential(
        actor_id=actor.id,
        principal_id=principal_id,
        credential_id=credential_id,
        expires_at=payload.expires_at,
        overlap_expires_at=payload.overlap_expires_at,
        correlation_id=correlation(request),
    )
    return issue_response(value)


@admin_router.delete(
    "/workspaces/{workspace_id}/service-principals/{principal_id}/credentials/{credential_id}",
    response_model=LifecycleResult,
    operation_id="revokeServiceCredential",
)
async def revoke_service_credential(
    workspace_id: str,
    principal_id: UUID,
    credential_id: str,
    request: Request,
    response: Response,
    current: Current,
) -> LifecycleResult:
    set_no_store(response)
    session, actor = current
    check_csrf(request, session)
    check_recent_auth(request, session)
    principal = await oauth_service(request).get_service_principal(actor.id, principal_id)
    if principal.workspace_id != workspace_id:
        raise McpAuthorizationError("invalid_principal", "Service principal not found")
    await oauth_service(request).revoke_service_credential(
        actor_id=actor.id,
        principal_id=principal_id,
        credential_id=credential_id,
        correlation_id=correlation(request),
    )
    return LifecycleResult()


@admin_router.delete(
    "/workspaces/{workspace_id}/service-principals/{principal_id}",
    response_model=LifecycleResult,
    operation_id="revokeServicePrincipal",
)
async def revoke_service_principal(
    workspace_id: str,
    principal_id: UUID,
    request: Request,
    response: Response,
    current: Current,
) -> LifecycleResult:
    set_no_store(response)
    session, actor = current
    check_csrf(request, session)
    check_recent_auth(request, session)
    principal = await oauth_service(request).get_service_principal(actor.id, principal_id)
    if principal.workspace_id != workspace_id:
        raise McpAuthorizationError("invalid_principal", "Service principal not found")
    await oauth_service(request).revoke_service_principal(
        actor_id=actor.id, principal_id=principal_id
    )
    return LifecycleResult()
