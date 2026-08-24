"""Canonical account path aliases kept separate from authentication endpoints."""

# SQL statements are kept as complete reviewable statements.
# ruff: noqa: E501

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import text

from ima.api.v1.auth import Current, check_csrf, check_recent_auth, service
from ima.api.v1.identity_contracts import (
    IdentityUser,
    PasswordChangeRequest,
    ProfilePatch,
    SessionInfo,
    TotpVerifyRequest,
)

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/profile", response_model=IdentityUser)
async def profile(current_session: Current) -> IdentityUser:
    return current_session[1]


@router.patch("/profile", response_model=IdentityUser)
async def update_profile(
    payload: ProfilePatch, request: Request, current_session: Current
) -> IdentityUser:
    session, user = current_session
    check_csrf(request, session)
    return await service(request).update_profile(user.id, payload.display_name, payload.image_url)


@router.post("/password/change")
async def password_change(
    payload: PasswordChangeRequest, request: Request, current_session: Current
) -> dict[str, bool]:
    session, user = current_session
    check_csrf(request, session)
    check_recent_auth(request, session)
    await service(request).change_password(user.id, payload.current_password, payload.password)
    return {"changed": True}


@router.get("/sessions", response_model=list[SessionInfo])
async def sessions(request: Request, current_session: Current) -> list[SessionInfo]:
    session, user = current_session
    async with service(request).engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT id,created_at,last_activity_at,absolute_expires_at,user_agent FROM ima.sessions WHERE user_id=:id AND revoked_at IS NULL ORDER BY last_activity_at DESC"
                    ),
                    {"id": user.id},
                )
            )
            .mappings()
            .all()
        )
    return [
        SessionInfo(
            id=row["id"],
            createdAt=row["created_at"],
            lastActivityAt=row["last_activity_at"],
            expiresAt=row["absolute_expires_at"],
            current=row["id"] == session["id"],
            userAgent=row["user_agent"],
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}")
async def revoke(session_id: UUID, request: Request, current_session: Current) -> dict[str, bool]:
    session, user = current_session
    check_csrf(request, session)
    await service(request).revoke_session(session_id, user.id)
    return {"revoked": True}


@router.delete("/sessions")
async def revoke_all_sessions(request: Request, current_session: Current) -> dict[str, bool]:
    session, user = current_session
    check_csrf(request, session)
    await service(request).revoke_session(session["id"], user.id, all_sessions=True)
    return {"revoked": True}


@router.post("/totp/start")
async def totp_start(request: Request, current_session: Current) -> dict[str, str]:
    session, user = current_session
    check_csrf(request, session)
    check_recent_auth(request, session)
    return {"otpauthUri": await service(request).start_totp(user.id)}


@router.post("/totp/confirm")
async def totp_confirm(
    payload: TotpVerifyRequest, request: Request, current_session: Current
) -> dict[str, list[str]]:
    session, user = current_session
    check_csrf(request, session)
    check_recent_auth(request, session)
    return {"recoveryCodes": await service(request).confirm_totp(user.id, payload.code)}


@router.delete("/totp")
async def totp_disable(request: Request, current_session: Current) -> dict[str, bool]:
    session, user = current_session
    check_csrf(request, session)
    check_recent_auth(request, session)
    await service(request).disable_totp(user.id)
    return {"disabled": True}
