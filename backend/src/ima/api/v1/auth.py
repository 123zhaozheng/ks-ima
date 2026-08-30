"""Browser authentication and account security endpoints."""

# SQL lives in the application service; this file only adapts HTTP contracts.
# ruff: noqa: E501

from __future__ import annotations

import hmac
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ima.api.v1.identity_contracts import (
    AcceptTokenRequest,
    AuthCapabilities,
    IdentityUser,
    PasswordForgotRequest,
    PasswordResetRequest,
    RecoveryVerifyRequest,
    RegisterRequest,
    SignInRequest,
    SignInResponse,
    TotpVerifyRequest,
)
from ima.application.identity import IdentityService
from ima.config import Settings

router = APIRouter(prefix="/auth", tags=["auth"])


def service(request: Request) -> IdentityService:
    return cast(IdentityService, request.app.state.identity_service)


async def current(request: Request) -> tuple[dict[str, Any], IdentityUser]:
    value = await service(request).current_session(request)
    if not value:
        raise HTTPException(401, "Authentication is required")
    return value


Current = Annotated[tuple[dict[str, Any], IdentityUser], Depends(current)]


def check_csrf(request: Request, session: dict[str, Any]) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    settings: Settings = request.app.state.settings
    if not origin or (
        origin.rstrip("/") != settings.public_origin.rstrip("/")
        and origin not in settings.cors_origins
    ):
        raise HTTPException(403, "Request origin is not allowed")
    cookie = request.cookies.get(settings.csrf_cookie_name)
    header = request.headers.get("x-csrf-token")
    if (
        not cookie
        or not header
        or not hmac.compare_digest(cookie, header)
        or service(request)._session_digest(cookie) != session["csrf_digest"]
    ):
        raise HTTPException(403, "CSRF validation failed")


def check_recent_auth(request: Request, session: dict[str, Any]) -> None:
    recent = session.get("recent_auth_at")
    if (
        not recent
        or (datetime.now(UTC) - recent).total_seconds()
        > request.app.state.settings.recent_auth_seconds
    ):
        raise HTTPException(401, "Recent authentication is required")


def check_pre_auth_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    settings: Settings = request.app.state.settings
    if not origin or (
        origin.rstrip("/") != settings.public_origin.rstrip("/")
        and origin not in settings.cors_origins
    ):
        raise HTTPException(403, "Request origin is not allowed")


@router.get("/csrf", operation_id="authCsrf")
async def csrf(request: Request, response: Response) -> dict[str, str]:
    settings: Settings = request.app.state.settings
    raw = request.cookies.get(settings.csrf_cookie_name)
    if not raw:
        import secrets

        raw = secrets.token_urlsafe(32)
        response.set_cookie(
            settings.csrf_cookie_name,
            raw,
            secure=settings.environment == "production",
            samesite="lax",
            path="/",
        )
    return {"csrfToken": raw}


@router.post("/sign-in", response_model=SignInResponse, operation_id="authSignIn")
async def sign_in(payload: SignInRequest, request: Request, response: Response) -> SignInResponse:
    check_pre_auth_origin(request)
    status, user, challenge = await service(request).authenticate_password(
        str(payload.email), payload.password, request, response
    )
    return SignInResponse(
        status=cast(Literal["authenticated", "totp_required"], status),
        challenge=challenge,
        user=user,
    )


@router.post("/totp/verify", response_model=IdentityUser, operation_id="authTotpVerify")
async def totp_verify(
    payload: TotpVerifyRequest, request: Request, response: Response
) -> IdentityUser:
    check_pre_auth_origin(request)
    if not payload.challenge:
        raise HTTPException(400, "Authentication challenge is required")
    return await service(request).verify_challenge(
        payload.challenge, payload.code, request, response
    )


@router.post("/recovery/verify", response_model=IdentityUser, operation_id="authRecoveryVerify")
async def recovery_verify(
    payload: RecoveryVerifyRequest, request: Request, response: Response
) -> IdentityUser:
    check_pre_auth_origin(request)
    return await service(request).verify_challenge(
        payload.challenge, payload.code, request, response, recovery=True
    )


@router.post("/sign-out", operation_id="authSignOut")
async def sign_out(
    request: Request, response: Response, current_session: Current
) -> dict[str, bool]:
    session, user = current_session
    check_csrf(request, session)
    await service(request).revoke_session(session["id"], user.id)
    response.delete_cookie(request.app.state.settings.session_cookie_name, path="/")
    response.delete_cookie(request.app.state.settings.csrf_cookie_name, path="/")
    return {"signedOut": True}


@router.get("/session", response_model=IdentityUser, operation_id="authSession")
async def session(current_session: Current) -> IdentityUser:
    return current_session[1]


@router.get("/capabilities", response_model=AuthCapabilities, operation_id="authCapabilities")
async def capabilities(request: Request) -> AuthCapabilities:
    return AuthCapabilities(registration=await service(request).registration_enabled())


@router.post("/register", response_model=IdentityUser, operation_id="authRegister")
async def register(payload: RegisterRequest, request: Request) -> IdentityUser:
    check_pre_auth_origin(request)
    if not await service(request).registration_enabled():
        raise HTTPException(404, "Registration is not available")
    return (
        await service(request).create_user(
            str(payload.email), payload.display_name, payload.password
        )
    )[0]


@router.post("/invitations/accept", response_model=IdentityUser, operation_id="authAcceptInvite")
async def accept_invite(payload: AcceptTokenRequest, request: Request) -> IdentityUser:
    check_pre_auth_origin(request)
    return await service(request).accept_invite(
        payload.token, payload.password, payload.display_name
    )


@router.post("/password/forgot", operation_id="authPasswordForgot")
async def forgot(payload: PasswordForgotRequest, request: Request) -> dict[str, bool]:
    check_pre_auth_origin(request)
    delivered = await service(request).request_password_reset(str(payload.email))
    return {"accepted": True, "deliveryAvailable": delivered}


@router.post("/password/reset", operation_id="authPasswordReset")
async def reset(payload: PasswordResetRequest, request: Request) -> dict[str, bool]:
    check_pre_auth_origin(request)
    await service(request).reset_password(payload.token, payload.password)
    return {"reset": True}
