"""Local identity application service.

The service intentionally owns the complete session lifecycle. HTTP adapters
must not access identity tables directly, which keeps the Bun bridge and Vue
API on the same security rules.
"""

# SQL statements are kept readable as complete statements; formatting them
# into concatenated fragments makes security review harder.
# ruff: noqa: E501

from __future__ import annotations

import json
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID, uuid4

import pyotp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ima.application.contracts import IdentityUser
from ima.config import Settings
from ima.infrastructure.auth.security import (
    PASSWORD_PARAMETER_VERSION,
    decrypt_secret,
    digest,
    encrypt_secret,
    generate_recovery_code,
    hash_password,
    new_secret,
    normalize_email,
    password_needs_rehash,
    safe_code,
    verify_password,
)
from ima.infrastructure.mail import MailService

logger = logging.getLogger(__name__)
ROLES = ("super_admin", "platform_admin", "security_auditor")
LEGACY_ID_ALPHABET = "-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz"


def new_legacy_id() -> str:
    return "".join(secrets.choice(LEGACY_ID_ALPHABET) for _ in range(16))


def utcnow() -> datetime:
    return datetime.now(UTC)


class IdentityError(Exception):
    """Transport-neutral application error mapped by the HTTP adapter."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class RequestLike(Protocol):
    @property
    def headers(self) -> Any: ...

    @property
    def cookies(self) -> Any: ...

    @property
    def client(self) -> Any: ...


class ResponseLike(Protocol):
    def set_cookie(self, *args: Any, **kwargs: Any) -> Any: ...


HTTPException = IdentityError


class IdentityService:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self.mail = MailService(settings)

    def _token_digest(self, token: str) -> str:
        return digest(token, self.settings.token_pepper.get_secret_value())

    def _session_digest(self, token: str) -> str:
        return digest(token, self.settings.session_pepper.get_secret_value())

    async def rate_allowed(self, action: str, bucket: str) -> bool:
        now = utcnow()
        window = now.replace(second=0, microsecond=0)
        key = digest(f"{action}:{bucket}", self.settings.token_pepper.get_secret_value())
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT attempts,blocked_until FROM ima.auth_rate_limits WHERE bucket_digest=:bucket AND action=:action AND window_start=:window FOR UPDATE"
                        ),
                        {"bucket": key, "action": action, "window": window},
                    )
                )
                .mappings()
                .first()
            )
            if row and row["blocked_until"] and row["blocked_until"] > now:
                return False
            attempts = int(row["attempts"]) + 1 if row else 1
            blocked = (
                now + timedelta(seconds=self.settings.login_window_seconds)
                if attempts > self.settings.login_max_attempts
                else None
            )
            await conn.execute(
                text(
                    """INSERT INTO ima.auth_rate_limits(bucket_digest,action,window_start,attempts,blocked_until) VALUES (:bucket,:action,:window,:attempts,:blocked) ON CONFLICT(bucket_digest,action,window_start) DO UPDATE SET attempts=EXCLUDED.attempts,blocked_until=EXCLUDED.blocked_until"""
                ),
                {
                    "bucket": key,
                    "action": action,
                    "window": window,
                    "attempts": attempts,
                    "blocked": blocked,
                },
            )
            return blocked is None

    async def _audit(
        self,
        conn: Any,
        actor_id: str | None,
        action: str,
        result: str,
        *,
        target_type: str | None = None,
        target_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> None:
        await conn.execute(
            text(
                """INSERT INTO ima.audit_events(actor_id, action, target_type, target_id, result, reason_code, metadata, correlation_id, created_at) VALUES (:actor, :action, :tt, :tid, :result, :reason, CAST(:metadata AS jsonb), :correlation, :created)"""
            ),
            {
                "actor": actor_id,
                "action": action,
                "tt": target_type,
                "tid": target_id,
                "result": result,
                "reason": reason,
                "metadata": json.dumps(metadata or {}),
                "correlation": correlation_id,
                "created": utcnow(),
            },
        )

    async def _user(self, conn: Any, user_id: str) -> IdentityUser | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT u.id,u.email,u.display_name,u.image_url,u.is_active, COALESCE(array_agg(r.role) FILTER (WHERE r.role IS NOT NULL), '{}') roles FROM ima.users u LEFT JOIN ima.platform_role_assignments r ON r.user_id=u.id WHERE u.id=:id GROUP BY u.id"""
                    ),
                    {"id": user_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return IdentityUser(
            id=row["id"],
            email=row["email"],
            display_name=row["display_name"],
            image_url=row["image_url"],
            platform_roles=tuple(row["roles"] or ()),
            is_active=row["is_active"],
        )

    async def get_user_by_email(self, email: str) -> tuple[dict[str, Any], str | None] | None:
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT u.*, p.phc_hash, p.parameter_version FROM ima.users u LEFT JOIN ima.password_credentials p ON p.user_id=u.id WHERE u.normalized_email=:email"""
                        ),
                        {"email": normalize_email(email)},
                    )
                )
                .mappings()
                .first()
            )
            return (dict(row), row["phc_hash"]) if row else None

    async def registration_enabled(self) -> bool:
        async with self.engine.connect() as conn:
            value = await conn.scalar(
                text("SELECT allow_registration FROM ima.system_settings WHERE id=true")
            )
        return bool(value)

    async def _roles(self, conn: Any, user_id: str) -> tuple[str, ...]:
        rows = await conn.execute(
            text("SELECT role FROM ima.platform_role_assignments WHERE user_id=:id"),
            {"id": user_id},
        )
        return tuple(str(row[0]) for row in rows)

    async def has_capability(self, user_id: str, capability: str) -> bool:
        async with self.engine.connect() as conn:
            roles = await self._roles(conn, user_id)
        if "super_admin" in roles:
            return True
        if capability == "audit_read":
            return "security_auditor" in roles or "platform_admin" in roles
        if capability == "workspaces_read":
            return "security_auditor" in roles or "platform_admin" in roles
        if capability in {"users_manage", "workspaces_manage", "settings_manage"}:
            return "platform_admin" in roles
        return False

    async def is_super_admin(self, user_id: str) -> bool:
        async with self.engine.connect() as conn:
            return bool(
                await conn.scalar(
                    text(
                        "SELECT 1 FROM ima.platform_role_assignments WHERE user_id=:id AND role='super_admin'"
                    ),
                    {"id": user_id},
                )
            )

    async def mutate_platform_role(
        self, actor_id: str, user_id: str, role: str, *, grant: bool
    ) -> None:
        """Authorize and mutate a role while all relevant rows are locked."""
        if role not in ROLES:
            raise HTTPException(400, "Unknown platform role")
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('ima:last-super-admin'))")
            )
            actor = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,is_active FROM ima.users WHERE id IN (:actor,:target) FOR UPDATE"
                        ),
                        {"actor": actor_id, "target": user_id},
                    )
                )
                .mappings()
                .all()
            )
            actor_row = next((row for row in actor if row["id"] == actor_id), None)
            target_row = next((row for row in actor if row["id"] == user_id), None)
            if not actor_row or not actor_row["is_active"]:
                raise HTTPException(403, "Only an active super administrator can manage roles")
            if not target_row:
                raise HTTPException(404, "User not found")
            is_super = await conn.scalar(
                text(
                    "SELECT 1 FROM ima.platform_role_assignments WHERE user_id=:id AND role='super_admin' FOR UPDATE"
                ),
                {"id": actor_id},
            )
            if not is_super:
                raise HTTPException(403, "Only a super administrator can manage platform roles")
            if not grant and role == "super_admin":
                count = await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.platform_role_assignments r JOIN ima.users u ON u.id=r.user_id WHERE r.role='super_admin' AND u.is_active"
                    )
                )
                if count <= 1:
                    raise HTTPException(409, "The final super administrator cannot be removed")
            if grant:
                await conn.execute(
                    text(
                        "INSERT INTO ima.platform_role_assignments(user_id,role,grantor_id,created_at) VALUES (:uid,:role,:actor,now()) ON CONFLICT DO NOTHING"
                    ),
                    {"uid": user_id, "role": role, "actor": actor_id},
                )
            else:
                await conn.execute(
                    text(
                        "DELETE FROM ima.platform_role_assignments WHERE user_id=:uid AND role=:role"
                    ),
                    {"uid": user_id, "role": role},
                )
            await self._audit(
                conn,
                actor_id,
                "role.granted" if grant else "role.revoked",
                "success",
                target_type="user",
                target_id=user_id,
                metadata={"role": role},
            )

    async def create_user(
        self,
        email: str,
        display_name: str,
        password: str | None = None,
        *,
        actor_id: str | None = None,
        invite: bool = False,
        correlation_id: str | None = None,
    ) -> tuple[IdentityUser, str | None]:
        if invite and not self.mail.enabled:
            raise HTTPException(
                503, "Invitation delivery is unavailable because SMTP is not configured"
            )
        now = utcnow()
        user_id = new_legacy_id()
        temporary = password or new_secret(18)
        async with self.engine.begin() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM ima.users WHERE normalized_email=:email"),
                {"email": normalize_email(email)},
            )
            if exists:
                raise HTTPException(409, "An account with this email already exists")
            await conn.execute(
                text(
                    """INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (:id,:email,:normalized,:name,true,:reset,:stamp,:now,:now)"""
                ),
                {
                    "id": user_id,
                    "email": email.strip(),
                    "normalized": normalize_email(email),
                    "name": display_name.strip(),
                    "reset": invite,
                    "stamp": new_secret(32),
                    "now": now,
                },
            )
            if not invite:
                await conn.execute(
                    text(
                        "INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (:id,:hash,:version,:now)"
                    ),
                    {
                        "id": user_id,
                        "hash": hash_password(temporary),
                        "version": PASSWORD_PARAMETER_VERSION,
                        "now": now,
                    },
                )
            else:
                raw = new_secret(32)
                await conn.execute(
                    text(
                        "INSERT INTO ima.auth_tokens(id,user_id,email,purpose,token_digest,expires_at,created_at) VALUES (:id,:uid,:email,'invite',:digest,:expires,:now)"
                    ),
                    {
                        "id": uuid4(),
                        "uid": user_id,
                        "email": email,
                        "digest": self._token_digest(raw),
                        "expires": now + timedelta(days=2),
                        "now": now,
                    },
                )
            legacy_user_table = await conn.scalar(text("SELECT to_regclass('public.user')"))
            if legacy_user_table:
                await conn.execute(
                    text(
                        """INSERT INTO ima.legacy_identity_projection(user_id,status,updated_at) VALUES (:id,'pending',:now) ON CONFLICT(user_id) DO UPDATE SET status='pending',updated_at=:now"""
                    ),
                    {"id": user_id, "now": now},
                )
                await conn.execute(
                    text(
                        """INSERT INTO public."user"(id,name,email,image,created_at,updated_at) VALUES (:id,:name,:email,:image,:now,:now) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,email=EXCLUDED.email,image=EXCLUDED.image,updated_at=EXCLUDED.updated_at"""
                    ),
                    {
                        "id": user_id,
                        "name": display_name.strip(),
                        "email": email.strip(),
                        "image": None,
                        "now": now,
                    },
                )
                await conn.execute(
                    text(
                        """INSERT INTO public."userData"(id,perfs,data) VALUES (:id,'{}'::jsonb,'{}'::jsonb) ON CONFLICT(id) DO NOTHING"""
                    ),
                    {"id": user_id},
                )
                await conn.execute(
                    text(
                        "UPDATE ima.legacy_identity_projection SET status='complete',migrated_at=:now,updated_at=:now WHERE user_id=:id"
                    ),
                    {"id": user_id, "now": now},
                )
            await self._audit(
                conn,
                actor_id,
                "user.created",
                "success",
                target_type="user",
                target_id=str(user_id),
                metadata={"invite": invite},
                correlation_id=correlation_id,
            )
            user = await self._user(conn, user_id)
        if user is None:
            raise RuntimeError("created user disappeared")
        issued = raw if invite else temporary
        if invite:
            try:
                await self.mail.send_invitation(email, issued)
            except Exception as exc:
                async with self.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE ima.auth_tokens SET used_at=:now WHERE token_digest=:digest AND used_at IS NULL"
                        ),
                        {"now": utcnow(), "digest": self._token_digest(issued)},
                    )
                    await self._audit(
                        conn,
                        actor_id,
                        "auth.invite_delivery",
                        "failed",
                        reason="smtp_delivery_failed",
                        metadata={"email": normalize_email(email)},
                    )
                raise HTTPException(503, "Invitation delivery failed") from exc
        return user, issued

    async def accept_invite(
        self, token: str, password: str, display_name: str | None = None
    ) -> IdentityUser:
        if not await self.rate_allowed("invite_accept", token):
            async with self.engine.begin() as conn:
                await self._audit(
                    conn,
                    None,
                    "auth.invite_accepted",
                    "failed",
                    reason="rate_limited",
                )
            raise HTTPException(429, "Too many invitation attempts; try again later")
        now = utcnow()
        invalid = False
        user: IdentityUser | None = None
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.auth_tokens WHERE token_digest=:digest AND purpose='invite' AND used_at IS NULL AND expires_at>:now FOR UPDATE"
                        ),
                        {"digest": self._token_digest(token), "now": now},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                invalid = True
                await self._audit(
                    conn,
                    None,
                    "auth.invite_accepted",
                    "failed",
                    reason="invalid_or_expired",
                )
            else:
                await conn.execute(
                    text("UPDATE ima.auth_tokens SET used_at=:now WHERE id=:id"),
                    {"now": now, "id": row["id"]},
                )
                await conn.execute(
                    text(
                        "UPDATE ima.users SET password_reset_required=false,display_name=COALESCE(:name,display_name),updated_at=:now WHERE id=:id"
                    ),
                    {"name": display_name, "now": now, "id": row["user_id"]},
                )
                await conn.execute(
                    text(
                        "INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (:id,:hash,:version,:now) ON CONFLICT(user_id) DO UPDATE SET phc_hash=EXCLUDED.phc_hash,parameter_version=EXCLUDED.parameter_version,changed_at=EXCLUDED.changed_at"
                    ),
                    {
                        "id": row["user_id"],
                        "hash": hash_password(password),
                        "version": PASSWORD_PARAMETER_VERSION,
                        "now": now,
                    },
                )
                await self._audit(
                    conn,
                    row["user_id"],
                    "auth.invite_accepted",
                    "success",
                    target_type="user",
                    target_id=str(row["user_id"]),
                )
                user = await self._user(conn, row["user_id"])
        if invalid:
            raise HTTPException(400, "This invitation is invalid or expired")
        if user is None:
            raise HTTPException(404, "Account not found")
        return user

    async def authenticate_password(
        self, email: str, password: str, request: RequestLike, response: ResponseLike
    ) -> tuple[str, IdentityUser | None, str | None]:
        source = request.client.host if request.client else "unknown"
        if not await self.rate_allowed("sign_in", f"{normalize_email(email)}:{source}"):
            raise HTTPException(429, "Too many attempts; try again later")
        found = await self.get_user_by_email(email)
        if (
            not found
            or not found[1]
            or not verify_password(found[1], password)
            or not found[0]["is_active"]
        ):
            raise HTTPException(401, "Email or password is incorrect")
        row, phc = found
        if phc is None:
            raise HTTPException(401, "Email or password is incorrect")
        user_id = row["id"]
        now = utcnow()
        async with self.engine.begin() as conn:
            if password_needs_rehash(phc):
                await conn.execute(
                    text(
                        "UPDATE ima.password_credentials SET phc_hash=:hash,parameter_version=:version,changed_at=:now WHERE user_id=:id"
                    ),
                    {
                        "hash": hash_password(password),
                        "version": PASSWORD_PARAMETER_VERSION,
                        "now": now,
                        "id": user_id,
                    },
                )
            totp = await conn.scalar(
                text("SELECT confirmed_at IS NOT NULL FROM ima.totp_credentials WHERE user_id=:id"),
                {"id": user_id},
            )
            if totp:
                challenge = new_secret(32)
                await conn.execute(
                    text(
                        "INSERT INTO ima.auth_tokens(id,user_id,email,purpose,token_digest,expires_at,created_at) VALUES (:id,:uid,:email,'signin_challenge',:digest,:expires,:now)"
                    ),
                    {
                        "id": uuid4(),
                        "uid": user_id,
                        "email": row["email"],
                        "digest": self._token_digest(challenge),
                        "expires": now + timedelta(minutes=5),
                        "now": now,
                    },
                )
                await self._audit(
                    conn,
                    user_id,
                    "auth.password_verified",
                    "challenge",
                    target_type="user",
                    target_id=str(user_id),
                    metadata={"source": source},
                )
                return "totp_required", None, challenge
            token, csrf = await self._create_session(conn, user_id, request, recent_auth=now)
            self._set_cookies(response, token, csrf)
            await self._audit(
                conn,
                user_id,
                "auth.sign_in",
                "success",
                target_type="user",
                target_id=str(user_id),
                metadata={"source": source},
            )
            user = await self._user(conn, user_id)
            return "authenticated", user, None

    async def verify_challenge(
        self,
        challenge: str,
        code: str,
        request: RequestLike,
        response: ResponseLike,
        recovery: bool = False,
    ) -> IdentityUser:
        if not await self.rate_allowed("totp_verify", challenge):
            raise HTTPException(429, "Too many verification attempts; try again later")
        now = utcnow()
        purpose = "signin_challenge"
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.auth_tokens WHERE token_digest=:digest AND purpose=:purpose AND used_at IS NULL AND expires_at>:now FOR UPDATE"
                        ),
                        {"digest": self._token_digest(challenge), "purpose": purpose, "now": now},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(401, "The authentication challenge is invalid or expired")
            secret_row = (
                await conn.execute(
                    text(
                        "SELECT t.encrypted_secret FROM ima.totp_credentials t JOIN ima.users u ON u.id=t.user_id WHERE t.user_id=:id AND t.confirmed_at IS NOT NULL AND u.is_active"
                    ),
                    {"id": row["user_id"]},
                )
            ).first()
            valid = False
            if recovery:
                code_digest = self._token_digest(safe_code(code))
                used = await conn.scalar(
                    text(
                        "SELECT id FROM ima.recovery_codes WHERE user_id=:uid AND code_digest=:digest AND used_at IS NULL FOR UPDATE"
                    ),
                    {"uid": row["user_id"], "digest": code_digest},
                )
                if used:
                    await conn.execute(
                        text(
                            "UPDATE ima.recovery_codes SET used_at=:now WHERE id=:id AND used_at IS NULL"
                        ),
                        {"now": now, "id": used},
                    )
                    valid = True
            elif secret_row:
                try:
                    valid = pyotp.TOTP(
                        decrypt_secret(
                            secret_row[0],
                            self.settings.totp_encryption_key.get_secret_value(),
                            str(row["user_id"]),
                        )
                    ).verify(code, valid_window=1)
                except Exception:
                    valid = False
            if not valid:
                raise HTTPException(401, "The verification code is incorrect")
            await conn.execute(
                text("UPDATE ima.auth_tokens SET used_at=:now WHERE id=:id"),
                {"now": now, "id": row["id"]},
            )
            token, csrf = await self._create_session(conn, row["user_id"], request, recent_auth=now)
            self._set_cookies(response, token, csrf)
            user = await self._user(conn, row["user_id"])
            await self._audit(
                conn,
                row["user_id"],
                "auth.sign_in",
                "success",
                target_type="user",
                target_id=str(row["user_id"]),
                metadata={"method": "recovery" if recovery else "totp"},
            )
        if user is None:
            raise HTTPException(404, "Account not found")
        return user

    async def _create_session(
        self, conn: Any, user_id: str, request: RequestLike, *, recent_auth: datetime
    ) -> tuple[str, str]:
        token, csrf = new_secret(32), new_secret(32)
        now = utcnow()
        stamp = await conn.scalar(
            text("SELECT security_stamp FROM ima.users WHERE id=:id"), {"id": user_id}
        )
        await conn.execute(
            text(
                "INSERT INTO ima.sessions(id,user_id,token_digest,csrf_digest,security_stamp,created_at,last_activity_at,idle_expires_at,absolute_expires_at,recent_auth_at,user_agent,source_ip) VALUES (:id,:uid,:token,:csrf,:stamp,:now,:now,:idle,:absolute,:recent,:agent,:ip)"
            ),
            {
                "id": uuid4(),
                "uid": user_id,
                "token": self._session_digest(token),
                "csrf": self._session_digest(csrf),
                "stamp": stamp,
                "now": now,
                "idle": now + timedelta(seconds=self.settings.session_idle_seconds),
                "absolute": now + timedelta(seconds=self.settings.session_absolute_seconds),
                "recent": recent_auth,
                "agent": request.headers.get("user-agent", "")[:512],
                "ip": request.client.host if request.client else None,
            },
        )
        return token, csrf

    def _set_cookies(self, response: ResponseLike, token: str, csrf: str) -> None:
        secure = self.settings.environment == "production"
        response.set_cookie(
            self.settings.session_cookie_name,
            token,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            self.settings.csrf_cookie_name,
            csrf,
            httponly=False,
            secure=secure,
            samesite="lax",
            path="/",
        )

    async def current_session(
        self, request: RequestLike
    ) -> tuple[dict[str, Any], IdentityUser] | None:
        raw = request.cookies.get(self.settings.session_cookie_name)
        if not raw:
            return None
        now = utcnow()
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT s.*,s.security_stamp AS session_security_stamp,u.security_stamp AS user_security_stamp,u.is_active FROM ima.sessions s JOIN ima.users u ON u.id=s.user_id WHERE s.token_digest=:digest AND s.revoked_at IS NULL FOR UPDATE"""
                        ),
                        {"digest": self._session_digest(raw)},
                    )
                )
                .mappings()
                .first()
            )
            if (
                not row
                or not row["is_active"]
                or row["session_security_stamp"] != row["user_security_stamp"]
                or row["idle_expires_at"] <= now
                or row["absolute_expires_at"] <= now
            ):
                if row:
                    await conn.execute(
                        text(
                            "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='expired_or_security_stamp' WHERE id=:id"
                        ),
                        {"now": now, "id": row["id"]},
                    )
                return None
            if row["last_activity_at"] <= now - timedelta(seconds=30):
                await conn.execute(
                    text(
                        "UPDATE ima.sessions SET last_activity_at=:now,idle_expires_at=:idle WHERE id=:id"
                    ),
                    {
                        "now": now,
                        "idle": now + timedelta(seconds=self.settings.session_idle_seconds),
                        "id": row["id"],
                    },
                )
            user = await self._user(conn, row["user_id"])
            return (dict(row), user) if user else None

    async def revoke_session(
        self,
        session_id: UUID,
        actor_id: str,
        *,
        all_sessions: bool = False,
        reason: str = "user_request",
    ) -> None:
        async with self.engine.begin() as conn:
            if all_sessions:
                await conn.execute(
                    text(
                        "UPDATE ima.sessions SET revoked_at=:now,revoke_reason=:reason WHERE user_id=:uid AND revoked_at IS NULL"
                    ),
                    {"now": utcnow(), "reason": reason, "uid": actor_id},
                )
            else:
                await conn.execute(
                    text(
                        "UPDATE ima.sessions SET revoked_at=:now,revoke_reason=:reason WHERE id=:id AND user_id=:uid"
                    ),
                    {"now": utcnow(), "reason": reason, "id": session_id, "uid": actor_id},
                )
            await self._audit(
                conn,
                actor_id,
                "auth.session_revoked",
                "success",
                target_type="session",
                target_id=str(session_id),
                metadata={"all": all_sessions},
            )

    async def change_password(self, user_id: str, current: str, password: str) -> None:
        async with self.engine.begin() as conn:
            phc = await conn.scalar(
                text("SELECT phc_hash FROM ima.password_credentials WHERE user_id=:id"),
                {"id": user_id},
            )
            if not phc or not verify_password(phc, current):
                raise HTTPException(400, "Current password is incorrect")
            now = utcnow()
            await conn.execute(
                text(
                    "UPDATE ima.password_credentials SET phc_hash=:hash,parameter_version=:version,changed_at=:now WHERE user_id=:id"
                ),
                {
                    "hash": hash_password(password),
                    "version": PASSWORD_PARAMETER_VERSION,
                    "now": now,
                    "id": user_id,
                },
            )
            await conn.execute(
                text("UPDATE ima.users SET security_stamp=:stamp,updated_at=:now WHERE id=:id"),
                {"stamp": new_secret(32), "now": now, "id": user_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='password_changed' WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"now": now, "id": user_id},
            )
            await self._audit(
                conn,
                user_id,
                "auth.password_changed",
                "success",
                target_type="user",
                target_id=str(user_id),
            )

    async def start_totp(self, user_id: str) -> str:
        secret = pyotp.random_base32()
        now = utcnow()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """INSERT INTO ima.totp_credentials(user_id,encrypted_secret,key_version,created_at) VALUES (:id,:secret,1,:now) ON CONFLICT(user_id) DO UPDATE SET encrypted_secret=EXCLUDED.encrypted_secret,confirmed_at=NULL,created_at=EXCLUDED.created_at"""
                ),
                {
                    "id": user_id,
                    "secret": encrypt_secret(
                        secret, self.settings.totp_encryption_key.get_secret_value(), str(user_id)
                    ),
                    "now": now,
                },
            )
        return pyotp.TOTP(secret).provisioning_uri(name="ima", issuer_name="Intranet IMA")

    async def confirm_totp(self, user_id: str, code: str) -> list[str]:
        now = utcnow()
        raw_codes = [generate_recovery_code() for _ in range(10)]
        async with self.engine.begin() as conn:
            secret_row = (
                await conn.execute(
                    text("SELECT encrypted_secret FROM ima.totp_credentials WHERE user_id=:id"),
                    {"id": user_id},
                )
            ).first()
            if not secret_row:
                raise HTTPException(400, "TOTP enrollment has not been started")
            try:
                valid = pyotp.TOTP(
                    decrypt_secret(
                        secret_row[0],
                        self.settings.totp_encryption_key.get_secret_value(),
                        str(user_id),
                    )
                ).verify(code, valid_window=1)
            except Exception:
                valid = False
            if not valid:
                raise HTTPException(400, "The verification code is incorrect")
            await conn.execute(
                text("UPDATE ima.totp_credentials SET confirmed_at=:now WHERE user_id=:id"),
                {"now": now, "id": user_id},
            )
            await conn.execute(
                text("DELETE FROM ima.recovery_codes WHERE user_id=:id"), {"id": user_id}
            )
            for value in raw_codes:
                await conn.execute(
                    text(
                        "INSERT INTO ima.recovery_codes(id,user_id,code_digest,created_at) VALUES (:id,:uid,:digest,:now)"
                    ),
                    {
                        "id": uuid4(),
                        "uid": user_id,
                        "digest": self._token_digest(safe_code(value)),
                        "now": now,
                    },
                )
            await conn.execute(
                text("UPDATE ima.users SET security_stamp=:stamp,updated_at=:now WHERE id=:id"),
                {"stamp": new_secret(32), "now": now, "id": user_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='totp_changed' WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"now": now, "id": user_id},
            )
            await self._audit(
                conn,
                user_id,
                "auth.totp_enabled",
                "success",
                target_type="user",
                target_id=str(user_id),
            )
        return raw_codes

    async def disable_totp(self, user_id: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM ima.totp_credentials WHERE user_id=:id"), {"id": user_id}
            )
            await conn.execute(
                text("DELETE FROM ima.recovery_codes WHERE user_id=:id"), {"id": user_id}
            )
            await conn.execute(
                text("UPDATE ima.users SET security_stamp=:stamp,updated_at=:now WHERE id=:id"),
                {"stamp": new_secret(32), "now": utcnow(), "id": user_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='totp_changed' WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"now": utcnow(), "id": user_id},
            )
            await self._audit(
                conn,
                user_id,
                "auth.totp_disabled",
                "success",
                target_type="user",
                target_id=str(user_id),
            )

    async def reset_totp(self, user_id: str, actor_id: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM ima.totp_credentials WHERE user_id=:id"), {"id": user_id}
            )
            await conn.execute(
                text("DELETE FROM ima.recovery_codes WHERE user_id=:id"), {"id": user_id}
            )
            await conn.execute(
                text("UPDATE ima.users SET security_stamp=:stamp,updated_at=:now WHERE id=:id"),
                {"stamp": new_secret(32), "now": utcnow(), "id": user_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='admin_totp_reset' WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"now": utcnow(), "id": user_id},
            )
            await self._audit(
                conn, actor_id, "user.totp_reset", "success", target_type="user", target_id=user_id
            )

    async def update_profile(
        self, user_id: str, display_name: str | None, image_url: str | None
    ) -> IdentityUser:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.users SET display_name=COALESCE(:name,display_name),image_url=COALESCE(:image,image_url),updated_at=:now WHERE id=:id"
                ),
                {"name": display_name, "image": image_url, "now": utcnow(), "id": user_id},
            )
            await self._audit(
                conn,
                user_id,
                "auth.profile_updated",
                "success",
                target_type="user",
                target_id=str(user_id),
            )
            user = await self._user(conn, user_id)
        if user is None:
            raise HTTPException(404, "Account not found")
        return user

    async def create_password_token(self, email: str, purpose: str) -> str | None:
        now = utcnow()
        async with self.engine.begin() as conn:
            user = (
                await conn.execute(
                    text("SELECT id FROM ima.users WHERE normalized_email=:email AND is_active"),
                    {"email": normalize_email(email)},
                )
            ).first()
            if not user:
                return None
            raw = new_secret(32)
            await conn.execute(
                text(
                    "UPDATE ima.auth_tokens SET used_at=:now WHERE user_id=:uid AND purpose=:purpose AND used_at IS NULL"
                ),
                {"now": now, "uid": user[0], "purpose": purpose},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.auth_tokens(id,user_id,email,purpose,token_digest,expires_at,created_at) VALUES (:id,:uid,:email,:purpose,:digest,:expires,:now)"
                ),
                {
                    "id": uuid4(),
                    "uid": user[0],
                    "email": email,
                    "purpose": purpose,
                    "digest": self._token_digest(raw),
                    "expires": now + timedelta(hours=1),
                    "now": now,
                },
            )
            return raw

    async def request_password_reset(self, email: str) -> bool:
        if not await self.rate_allowed("password_reset", normalize_email(email)):
            return False
        token = await self.create_password_token(email, "password_reset")
        if token is None:
            return False
        if not self.mail.enabled:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE ima.auth_tokens SET used_at=:now WHERE token_digest=:digest AND used_at IS NULL"
                    ),
                    {"now": utcnow(), "digest": self._token_digest(token)},
                )
            return False
        try:
            await self.mail.send_password_reset(email, token)
        except Exception:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE ima.auth_tokens SET used_at=:now WHERE token_digest=:digest AND used_at IS NULL"
                    ),
                    {"now": utcnow(), "digest": self._token_digest(token)},
                )
                await self._audit(
                    conn,
                    None,
                    "auth.password_reset_delivery",
                    "failed",
                    reason="smtp_delivery_failed",
                    metadata={"email": normalize_email(email)},
                )
            return False
        return True

    async def reset_password(self, token: str, password: str) -> None:
        if not await self.rate_allowed("password_reset_apply", token):
            raise HTTPException(429, "Too many reset attempts; try again later")
        now = utcnow()
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.auth_tokens WHERE token_digest=:digest AND purpose IN ('password_reset','invite') AND used_at IS NULL AND expires_at>:now FOR UPDATE"
                        ),
                        {"digest": self._token_digest(token), "now": now},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise HTTPException(400, "This reset link is invalid or expired")
            await conn.execute(
                text("UPDATE ima.auth_tokens SET used_at=:now WHERE id=:id"),
                {"now": now, "id": row["id"]},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (:id,:hash,:version,:now) ON CONFLICT(user_id) DO UPDATE SET phc_hash=EXCLUDED.phc_hash,parameter_version=EXCLUDED.parameter_version,changed_at=EXCLUDED.changed_at"
                ),
                {
                    "id": row["user_id"],
                    "hash": hash_password(password),
                    "version": PASSWORD_PARAMETER_VERSION,
                    "now": now,
                },
            )
            await conn.execute(
                text(
                    "UPDATE ima.users SET password_reset_required=false,security_stamp=:stamp,updated_at=:now WHERE id=:id"
                ),
                {"stamp": new_secret(32), "now": now, "id": row["user_id"]},
            )
            await conn.execute(
                text(
                    "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='password_reset' WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"now": now, "id": row["user_id"]},
            )
            await self._audit(
                conn,
                row["user_id"],
                "auth.password_reset",
                "success",
                target_type="user",
                target_id=str(row["user_id"]),
            )

    async def admin_set_password(self, user_id: str, password: str, actor_id: str) -> None:
        now = utcnow()
        async with self.engine.begin() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM ima.users WHERE id=:id"), {"id": user_id}
            )
            if not exists:
                raise HTTPException(404, "User not found")
            await conn.execute(
                text(
                    """INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (:id,:hash,:version,:now) ON CONFLICT(user_id) DO UPDATE SET phc_hash=EXCLUDED.phc_hash,parameter_version=EXCLUDED.parameter_version,changed_at=EXCLUDED.changed_at"""
                ),
                {
                    "id": user_id,
                    "hash": hash_password(password),
                    "version": PASSWORD_PARAMETER_VERSION,
                    "now": now,
                },
            )
            await conn.execute(
                text(
                    "UPDATE ima.users SET password_reset_required=false,security_stamp=:stamp,updated_at=:now WHERE id=:id"
                ),
                {"stamp": new_secret(32), "now": now, "id": user_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.sessions SET revoked_at=:now,revoke_reason='admin_password_reset' WHERE user_id=:id AND revoked_at IS NULL"
                ),
                {"now": now, "id": user_id},
            )
            await self._audit(
                conn,
                actor_id,
                "user.password_reset",
                "success",
                target_type="user",
                target_id=user_id,
            )

    async def sync_legacy_projection(
        self, user_id: str, email: str, display_name: str, image_url: str | None
    ) -> None:
        """Upsert the compatibility user projection without workspace side effects."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """INSERT INTO ima.legacy_identity_projection(user_id,status,updated_at) VALUES (:id,'pending',now()) ON CONFLICT(user_id) DO UPDATE SET status='pending',updated_at=now()"""
                ),
                {"id": user_id},
            )
            try:
                await conn.execute(
                    text(
                        """INSERT INTO public."user"(id,name,email,image) VALUES (:id,:name,:email,:image) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,email=EXCLUDED.email,image=EXCLUDED.image"""
                    ),
                    {"id": user_id, "name": display_name, "email": email, "image": image_url},
                )
                await conn.execute(
                    text(
                        """INSERT INTO public."userData"(id,perfs,data) VALUES (:id,'{}'::jsonb,'{}'::jsonb) ON CONFLICT(id) DO NOTHING"""
                    ),
                    {"id": user_id},
                )
            except Exception as exc:
                await conn.execute(
                    text(
                        "UPDATE ima.legacy_identity_projection SET status='failed',last_error=:error,updated_at=now() WHERE user_id=:id"
                    ),
                    {"id": user_id, "error": type(exc).__name__},
                )
                raise
            await conn.execute(
                text(
                    "UPDATE ima.legacy_identity_projection SET status='complete',migrated_at=now(),updated_at=now() WHERE user_id=:id"
                ),
                {"id": user_id},
            )
