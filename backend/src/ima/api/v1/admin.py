"""Platform administration endpoints with server-side capability checks."""

# SQL statements are kept as complete reviewable statements.
# ruff: noqa: E501

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text

from ima.api.v1.auth import Current, check_csrf, check_recent_auth, service
from ima.api.v1.identity_contracts import (
    AdminCreateUserResponse,
    AdminUserDetail,
    AdminUserList,
    AuditEvent,
    AuditEventList,
    CreateUserRequest,
    IdentityUser,
    KnowledgeBaseCreateResponse,
    KnowledgeBaseInfo,
    KnowledgeBaseList,
    KnowledgeBaseRequest,
    PlatformSettings,
    SettingPatch,
    UserPatch,
)

router = APIRouter(prefix="/admin", tags=["platform-admin"])


def _encode_cursor(created_at: datetime, item_id: str) -> str:
    payload = json.dumps(
        {"createdAt": created_at.isoformat(), "id": item_id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(value: str | None) -> tuple[datetime, str] | None:
    if not value:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        created_at = datetime.fromisoformat(str(data["createdAt"]))
        item_id = str(data["id"])
        if not item_id or created_at.tzinfo is None:
            raise ValueError
        return created_at, item_id
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid pagination cursor") from None


class AdminPasswordReset(BaseModel):
    password: str = Field(min_length=12, max_length=1024)


async def require(
    request: Request, capability: str, current_session: Current, *, sensitive: bool = True
) -> tuple[dict[str, Any], Any]:
    session, user = current_session
    if sensitive:
        check_recent_auth(request, session)
    if not await service(request).has_capability(user.id, capability):
        raise HTTPException(403, "You do not have permission for this action")
    return session, user


@router.get("/users", response_model=AdminUserList, operation_id="adminListUsers")
async def users(
    request: Request,
    current_session: Current,
    q: str = "",
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    await require(request, "users_manage", current_session, sensitive=False)
    limit = max(1, min(limit, 100))
    decoded_cursor = _decode_cursor(cursor)
    async with service(request).engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        """SELECT u.id,u.email,u.display_name,u.is_active,u.password_reset_required,u.created_at,u.updated_at,COALESCE(array_agg(r.role) FILTER (WHERE r.role IS NOT NULL),'{}') roles FROM ima.users u LEFT JOIN ima.platform_role_assignments r ON r.user_id=u.id WHERE (:q='' OR u.normalized_email LIKE '%'||:q||'%' OR lower(u.display_name) LIKE '%'||:q||'%') AND (CAST(:cursor_at AS timestamptz) IS NULL OR (u.created_at,u.id) < (CAST(:cursor_at AS timestamptz),CAST(:cursor_id AS varchar))) GROUP BY u.id ORDER BY u.created_at DESC,u.id DESC LIMIT :limit"""
                    ),
                    {
                        "q": q.casefold(),
                        "limit": limit + 1,
                        "cursor_at": decoded_cursor[0] if decoded_cursor else None,
                        "cursor_id": decoded_cursor[1] if decoded_cursor else None,
                    },
                )
            )
            .mappings()
            .all()
        )
    next_cursor = (
        _encode_cursor(rows[limit - 1]["created_at"], rows[limit - 1]["id"])
        if len(rows) > limit
        else None
    )
    return {
        "items": [
            IdentityUser(
                id=row["id"],
                email=row["email"],
                display_name=row["display_name"],
                is_active=row["is_active"],
                platform_roles=tuple(row["roles"] or ()),
            )
            for row in rows[:limit]
        ],
        "nextCursor": next_cursor,
    }


@router.post("/users", response_model=AdminCreateUserResponse, operation_id="adminCreateUser")
async def create_user(
    payload: CreateUserRequest, request: Request, current_session: Current
) -> dict[str, Any]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    user, issued = await service(request).create_user(
        str(payload.email),
        payload.display_name,
        payload.temporary_password,
        actor_id=actor.id,
        invite=payload.send_invite,
    )
    return {
        "user": user,
        "inviteSent": payload.send_invite,
        "temporaryPasswordSet": not payload.send_invite,
    }


@router.get("/users/{user_id}", response_model=AdminUserDetail, operation_id="adminGetUser")
async def get_user(user_id: str, request: Request, current_session: Current) -> AdminUserDetail:
    await require(request, "users_manage", current_session)
    async with service(request).engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT u.id,u.email,u.display_name,u.image_url,u.is_active,u.password_reset_required,u.disabled_at,u.created_at,u.updated_at,COALESCE(array_agg(r.role) FILTER (WHERE r.role IS NOT NULL),'{}') roles FROM ima.users u LEFT JOIN ima.platform_role_assignments r ON r.user_id=u.id WHERE u.id=:id GROUP BY u.id"
                    ),
                    {"id": user_id},
                )
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(404, "User not found")
    return AdminUserDetail(
        id=row["id"],
        email=row["email"],
        displayName=row["display_name"],
        imageUrl=row["image_url"],
        isActive=row["is_active"],
        passwordResetRequired=row["password_reset_required"],
        disabledAt=row["disabled_at"],
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
        platformRoles=tuple(row["roles"] or ()),
    )


@router.patch("/users/{user_id}", response_model=AdminUserDetail, operation_id="adminUpdateUser")
async def update_user(
    user_id: str, payload: UserPatch, request: Request, current_session: Current
) -> AdminUserDetail:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    async with service(request).engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ima.users SET display_name=COALESCE(:name,display_name),email=COALESCE(:email,email),normalized_email=COALESCE(:normalized,normalized_email),updated_at=now() WHERE id=:id"
            ),
            {
                "name": payload.display_name,
                "email": str(payload.email) if payload.email else None,
                "normalized": str(payload.email).casefold() if payload.email else None,
                "id": user_id,
            },
        )
        await service(request)._audit(
            conn, actor.id, "user.updated", "success", target_type="user", target_id=str(user_id)
        )
    return await get_user(user_id, request, current_session)


@router.post("/users/{user_id}/disable", operation_id="adminDisableUser")
async def disable_user(user_id: str, request: Request, current_session: Current) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    if user_id == actor.id and await service(request).has_capability(actor.id, "users_manage"):
        raise HTTPException(400, "An administrator cannot disable the current account")
    async with service(request).engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ima:last-super-admin'))"))
        final_super = await conn.scalar(
            text(
                """SELECT count(*)=1 FROM ima.platform_role_assignments r JOIN ima.users u ON u.id=r.user_id WHERE r.role='super_admin' AND u.is_active AND r.user_id=:id"""
            ),
            {"id": user_id},
        )
        if final_super:
            raise HTTPException(409, "The final super administrator cannot be disabled")
        await conn.execute(
            text(
                "UPDATE ima.users SET is_active=false,disabled_at=now(),disabled_by=:actor,security_stamp=:stamp,updated_at=now() WHERE id=:id"
            ),
            {"actor": actor.id, "stamp": uuid4().hex, "id": user_id},
        )
        await conn.execute(
            text(
                "UPDATE ima.sessions SET revoked_at=now(),revoke_reason='disabled' WHERE user_id=:id AND revoked_at IS NULL"
            ),
            {"id": user_id},
        )
        await service(request)._audit(
            conn, actor.id, "user.disabled", "success", target_type="user", target_id=str(user_id)
        )
    return {"disabled": True}


@router.post("/users/{user_id}/restore", operation_id="adminRestoreUser")
async def restore_user(user_id: str, request: Request, current_session: Current) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    async with service(request).engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ima.users SET is_active=true,disabled_at=NULL,disabled_by=NULL,updated_at=now() WHERE id=:id"
            ),
            {"id": user_id},
        )
        await service(request)._audit(
            conn, actor.id, "user.restored", "success", target_type="user", target_id=str(user_id)
        )
    return {"restored": True}


@router.post("/users/{user_id}/reset-password", operation_id="adminResetUserPassword")
async def reset_user_password(
    user_id: str,
    payload: AdminPasswordReset,
    request: Request,
    current_session: Current,
) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    await service(request).admin_set_password(user_id, payload.password, actor.id)
    return {"reset": True}


@router.post("/users/{user_id}/revoke-sessions", operation_id="adminRevokeUserSessions")
async def revoke_user_sessions(
    user_id: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    async with service(request).engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE ima.sessions SET revoked_at=now(),revoke_reason='admin_request' WHERE user_id=:id AND revoked_at IS NULL"
            ),
            {"id": user_id},
        )
        await service(request)._audit(
            conn,
            actor.id,
            "user.sessions_revoked",
            "success",
            target_type="user",
            target_id=user_id,
        )
    return {"revoked": True}


@router.post("/users/{user_id}/reset-totp", operation_id="adminResetUserTotp")
async def reset_user_totp(
    user_id: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    await service(request).reset_totp(user_id, actor.id)
    return {"reset": True}


@router.delete("/users/{user_id}", operation_id="adminDeleteUser")
async def delete_user(user_id: str, request: Request, current_session: Current) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    async with service(request).engine.begin() as conn:
        await conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('ima:last-super-admin'))"))
        final_super = await conn.scalar(
            text(
                """SELECT count(*)=1 FROM ima.platform_role_assignments r JOIN ima.users u ON u.id=r.user_id WHERE r.role='super_admin' AND u.is_active AND r.user_id=:id"""
            ),
            {"id": user_id},
        )
        if final_super:
            raise HTTPException(409, "The final super administrator cannot be deleted")
        await conn.execute(text("DELETE FROM ima.users WHERE id=:id"), {"id": user_id})
        await service(request)._audit(
            conn, actor.id, "user.deleted", "success", target_type="user", target_id=user_id
        )
    return {"deleted": True}


@router.put("/users/{user_id}/roles/{role}", operation_id="adminGrantRole")
async def grant_role(
    user_id: str, role: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    await service(request).mutate_platform_role(actor.id, user_id, role, grant=True)
    return {"granted": True}


@router.delete("/users/{user_id}/roles/{role}", operation_id="adminRevokeRole")
async def revoke_role(
    user_id: str, role: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "users_manage", current_session)
    check_csrf(request, session)
    if role not in {"super_admin", "platform_admin", "security_auditor"}:
        raise HTTPException(400, "Unknown platform role")
    await service(request).mutate_platform_role(actor.id, user_id, role, grant=False)
    return {"revoked": True}


@router.get(
    "/knowledge-bases", response_model=KnowledgeBaseList, operation_id="adminListKnowledgeBases"
)
async def knowledge_bases(
    request: Request,
    current_session: Current,
    q: str = "",
    limit: int = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    await require(request, "knowledge_bases_read", current_session, sensitive=False)
    limit = max(1, min(limit, 100))
    decoded_cursor = _decode_cursor(cursor)
    async with service(request).engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT id,name,is_active,archived_at,created_at,updated_at FROM ima.knowledge_bases WHERE (:q='' OR lower(name) LIKE '%'||:q||'%') AND (CAST(:cursor_at AS timestamptz) IS NULL OR (created_at,id) < (CAST(:cursor_at AS timestamptz),CAST(:cursor_id AS varchar))) ORDER BY created_at DESC,id DESC LIMIT :limit"
                    ),
                    {
                        "q": q.casefold(),
                        "limit": limit + 1,
                        "cursor_at": decoded_cursor[0] if decoded_cursor else None,
                        "cursor_id": decoded_cursor[1] if decoded_cursor else None,
                    },
                )
            )
            .mappings()
            .all()
        )
    return {
        "items": [KnowledgeBaseInfo(**dict(row)) for row in rows[:limit]],
        "nextCursor": (
            _encode_cursor(rows[limit - 1]["created_at"], rows[limit - 1]["id"])
            if len(rows) > limit
            else None
        ),
    }


@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseCreateResponse,
    operation_id="adminCreateKnowledgeBase",
)
async def create_knowledge_base(
    payload: KnowledgeBaseRequest, request: Request, current_session: Current
) -> KnowledgeBaseCreateResponse:
    session, actor = await require(request, "knowledge_bases_manage", current_session)
    check_csrf(request, session)
    knowledge_base = await request.app.state.kb_service.create_knowledge_base(
        payload.initial_owner_user_id, payload.name
    )
    return KnowledgeBaseCreateResponse(
        id=knowledge_base["id"], name=knowledge_base["name"], isActive=True
    )


@router.post("/knowledge-bases/{kb_id}/archive", operation_id="adminArchiveKnowledgeBase")
async def archive_knowledge_base(
    kb_id: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "knowledge_bases_manage", current_session)
    check_csrf(request, session)
    await request.app.state.kb_service.archive_knowledge_base(actor.id, kb_id)
    return {"archived": True}


@router.post("/knowledge-bases/{kb_id}/restore", operation_id="adminRestoreKnowledgeBase")
async def restore_knowledge_base(
    kb_id: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "knowledge_bases_manage", current_session)
    check_csrf(request, session)
    await request.app.state.kb_service.restore_knowledge_base(actor.id, kb_id)
    return {"restored": True}


@router.delete("/knowledge-bases/{kb_id}", operation_id="adminDeleteKnowledgeBase")
async def delete_knowledge_base(
    kb_id: str, request: Request, current_session: Current
) -> dict[str, bool]:
    session, actor = await require(request, "knowledge_bases_manage", current_session)
    check_csrf(request, session)
    await request.app.state.kb_service.delete_archived_knowledge_base(actor.id, kb_id)
    return {"deleted": True}


@router.get("/audit-events", response_model=AuditEventList, operation_id="adminAuditEvents")
async def audit_events(
    request: Request, current_session: Current, limit: int = 100
) -> dict[str, Any]:
    await require(request, "audit_read", current_session)
    limit = max(1, min(limit, 500))
    async with service(request).engine.connect() as conn:
        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT id,actor_id,action,target_type,target_id,result,reason_code,metadata,correlation_id,created_at FROM ima.audit_events ORDER BY id DESC LIMIT :limit"
                    ),
                    {"limit": limit},
                )
            )
            .mappings()
            .all()
        )
    return {"items": [AuditEvent(**dict(row)) for row in rows]}


@router.get("/settings", response_model=PlatformSettings, operation_id="adminGetSettings")
async def settings(request: Request, current_session: Current) -> PlatformSettings:
    await require(request, "settings_manage", current_session)
    async with service(request).engine.connect() as conn:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT allow_registration,smtp_enabled,session_idle_seconds,session_absolute_seconds,recent_auth_seconds,updated_at FROM ima.system_settings WHERE id=true"
                    )
                )
            )
            .mappings()
            .first()
        )
    if not row:
        raise HTTPException(404, "Platform settings are unavailable")
    return PlatformSettings(**dict(row))


@router.patch("/settings", response_model=PlatformSettings, operation_id="adminPatchSettings")
async def patch_settings(
    payload: SettingPatch, request: Request, current_session: Current
) -> PlatformSettings:
    session, actor = await require(request, "settings_manage", current_session)
    check_csrf(request, session)
    values = payload.model_dump(exclude_none=True, by_alias=False)
    if not values:
        return await settings(request, current_session)
    async with service(request).engine.begin() as conn:
        sets = ",".join(f"{key}=:v_{key}" for key in values)
        params = {f"v_{key}": value for key, value in values.items()}
        params["actor"] = actor.id
        await conn.execute(
            text(
                f"UPDATE ima.system_settings SET {sets},updated_by=:actor,updated_at=now() WHERE id=true"
            ),
            params,
        )
        await service(request)._audit(
            conn, actor.id, "settings.updated", "success", metadata={"keys": list(values)}
        )
    return await settings(request, current_session)
