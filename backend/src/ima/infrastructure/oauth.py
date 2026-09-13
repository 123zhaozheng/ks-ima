"""Persistent OAuth/service-principal repositories.

Every secret-bearing lookup uses the same HMAC/pepper digest as the identity
service.  Rows are stored digest-only; raw codes, tokens, verifiers, and
service-secret values never touch the database.  Mutations that must be atomic
(authorization-code consumption, refresh rotation/replay, credential rotation
and lifecycle changes) each run inside a single locked transaction together
with their audit write.

This module never imports FastAPI or API DTO modules.  It owns the durable
OAuth/MCP state; the application service layer owns authorization policy and
correct transport error translation.
"""

# SQL statements remain readable as complete statements for security review.
# ruff: noqa: E501

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncEngine

from ima.application.mcp_contracts import redact_value
from ima.config import Settings
from ima.domain.oauth import (
    AccessTokenRecord,
    AuthorizationCodeRecord,
    AuthorizationTokenBundle,
    ClientRecord,
    CredentialRecord,
    GrantRecord,
    RefreshAccessTokenBundle,
    RefreshTokenRecord,
    ServicePrincipalRecord,
    normalize_cidr_allowlist,
)
from ima.infrastructure.auth.security import digest
from ima.infrastructure.observability.logging import redact


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_oauth_value() -> str:
    """High-entropy opaque OAuth/credential value (base64url, no padding)."""
    return secrets.token_urlsafe(32)


def secret_prefix() -> str:
    """Distinguishable nonsecret credential prefix."""
    return "mcpsc_" + secrets.token_urlsafe(8)


def credential_id() -> str:
    """Nonsecret key ID for service credentials."""
    return secrets.token_urlsafe(12)


class McpRepositoryError(Exception):
    """Stable transport-neutral repository failure with a reason code."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


class McpOauthRepository:
    """Digest-only OAuth + service-principal repository over the `ima` schema.

    The class is used with an ``AsyncEngine``.  Callers that need a single shared
    transaction pass an ``AsyncConnection``; methods opening their own transaction
    use ``self.engine.begin()``.  Every public mutation writes a safe audit event
    in the same transaction as the state change.
    """

    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings

    # ------------------------------------------------------------------
    # Digest primitives (identical construction to IdentityService).
    # ------------------------------------------------------------------

    def _token_digest(self, value: str) -> str:
        return digest(value, self.settings.token_pepper.get_secret_value())

    # ------------------------------------------------------------------
    # Audit helper (append-only ima.audit_events safe metadata).
    # ------------------------------------------------------------------

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
                """INSERT INTO ima.audit_events(actor_id,action,target_type,target_id,result,reason_code,metadata,correlation_id,created_at)
                   VALUES (:actor,:action,:tt,:tid,:result,:reason,CAST(:metadata AS jsonb),:correlation,:created)"""
            ),
            {
                "actor": actor_id,
                "action": action,
                "tt": target_type,
                "tid": target_id,
                "result": result,
                "reason": reason,
                "metadata": json.dumps(redact(redact_value(metadata or {}))),
                "correlation": correlation_id,
                "created": utcnow(),
            },
        )

    async def append_audit(
        self,
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
        """Public audit append used by the authorization service for policy denials."""
        async with self.engine.begin() as conn:
            await self._audit(
                conn,
                actor_id,
                action,
                result,
                target_type=target_type,
                target_id=target_id,
                reason=reason,
                metadata=metadata,
                correlation_id=correlation_id,
            )

    # ------------------------------------------------------------------
    # Clients and redirects
    # ------------------------------------------------------------------

    async def find_client_by_public_id(
        self, client_id: str, *, include_disabled: bool = False
    ) -> ClientRecord | None:
        """Find an enabled pre-registered client by its public client ID."""
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.id,c.client_id,c.client_name,c.client_type,c.token_endpoint_auth_method,
                                      c.client_secret_digest,c.application_type,c.canonical_resource,c.is_enabled
                               FROM ima.mcp_clients c
                               WHERE c.client_id=:id AND (:include_disabled OR c.is_enabled)"""
                        ),
                        {"id": client_id, "include_disabled": include_disabled},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            redirects = await conn.execute(
                text(
                    "SELECT redirect_uri FROM ima.mcp_client_redirects WHERE client_id=:cid ORDER BY redirect_uri"
                ),
                {"cid": row["id"]},
            )
            return ClientRecord(
                id=UUID(str(row["id"])),
                client_id=str(row["client_id"]),
                client_name=str(row["client_name"]),
                client_type=row["client_type"],
                token_endpoint_auth_method=row["token_endpoint_auth_method"],
                client_secret_digest=row["client_secret_digest"],
                application_type=row["application_type"],
                canonical_resource=str(row["canonical_resource"]),
                is_enabled=bool(row["is_enabled"]),
                redirect_uris=tuple(str(r[0]) for r in redirects),
            )

    async def register_client(
        self,
        *,
        client_id: str,
        client_name: str,
        client_type: str,
        token_endpoint_auth_method: str,
        application_type: str,
        canonical_resource: str,
        redirect_uris: tuple[str, ...],
        created_by: str | None = None,
        client_secret: str | None = None,
    ) -> UUID:
        """Persist a pre-registered client and its exact redirect URIs.

        Used by the administrative seeding path.  The optional client secret is
        stored only as a pepper digest.  The whole client + redirect set commits
        atomically.
        """
        client_uuid = uuid4()
        async with self.engine.begin() as conn:
            if created_by is None:
                raise PermissionError("OAuth client registration requires an operator")
            authorized = await conn.scalar(
                text(
                    """SELECT operator.id FROM ima.platform_role_assignments role
                       JOIN ima.users operator ON operator.id=role.user_id
                       WHERE role.user_id=:operator AND role.role='super_admin'
                         AND operator.is_active=true AND operator.disabled_at IS NULL
                       FOR UPDATE OF operator,role"""
                ),
                {"operator": created_by},
            )
            if not authorized:
                raise PermissionError("OAuth client registration requires an active super-admin")
            await conn.execute(
                text(
                    """INSERT INTO ima.mcp_clients(id,client_id,client_name,client_type,token_endpoint_auth_method,
                       client_secret_digest,application_type,canonical_resource,is_enabled,created_by,created_at,updated_at)
                       VALUES (:id,:cid,:name,:ctype,:auth,:cdigest,:apptype,:resource,true,:created_by,:now,:now)"""
                ),
                {
                    "id": client_uuid,
                    "cid": client_id,
                    "name": client_name,
                    "ctype": client_type,
                    "auth": token_endpoint_auth_method,
                    "cdigest": self._token_digest(client_secret) if client_secret else None,
                    "apptype": application_type,
                    "resource": canonical_resource,
                    "created_by": created_by,
                    "now": utcnow(),
                },
            )
            for redirect_uri in redirect_uris:
                await conn.execute(
                    text(
                        "INSERT INTO ima.mcp_client_redirects(client_id,redirect_uri,created_at) VALUES (:cid,:uri,:now)"
                    ),
                    {"cid": client_uuid, "uri": redirect_uri, "now": utcnow()},
                )
            await self._audit(
                conn,
                created_by,
                "oauth.client.registered",
                "success",
                target_type="oauth_client",
                target_id=str(client_uuid),
                metadata={"client_id": client_id, "redirects": list(redirect_uris)},
            )
        return client_uuid

    # ------------------------------------------------------------------
    # Human grants
    # ------------------------------------------------------------------

    async def find_active_grant(
        self,
        user_id: str,
        client_id: UUID,
        canonical_resource: str,
    ) -> GrantRecord | None:
        """Return the active user-level grant for a client, if any."""
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT id FROM ima.mcp_grants
                               WHERE user_id=:uid AND client_id=:cid AND canonical_resource=:resource
                                 AND state='active' AND expires_at>:now
                               ORDER BY created_at DESC LIMIT 1"""
                        ),
                        {
                            "uid": user_id,
                            "cid": client_id,
                            "resource": canonical_resource,
                            "now": utcnow(),
                        },
                    )
                )
                .mappings()
                .first()
            )
            return await self._grant_record(conn, row["id"]) if row else None

    async def _grant_record(self, conn: Any, grant_id: Any) -> GrantRecord | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT id,user_id,client_id,canonical_resource,scopes,state,expires_at
                           FROM ima.mcp_grants WHERE id=:id"""
                    ),
                    {"id": grant_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return GrantRecord(
            id=UUID(str(row["id"])),
            user_id=str(row["user_id"]),
            client_id=UUID(str(row["client_id"])),
            canonical_resource=str(row["canonical_resource"]),
            scopes=tuple(row["scopes"]),
            state=row["state"],
            expires_at=row["expires_at"],
        )

    async def load_grant(self, grant_id: UUID) -> GrantRecord | None:
        """Load a grant for application-service lifecycle validation."""
        async with self.engine.connect() as conn:
            return await self._grant_record(conn, grant_id)

    async def list_grants_for_user(self, user_id: str) -> tuple[tuple[GrantRecord, str], ...]:
        """List safe connected-client grants without token or code material."""
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    """SELECT g.id,c.client_name FROM ima.mcp_grants g
                       JOIN ima.mcp_clients c ON c.id=g.client_id
                       WHERE g.user_id=:user AND g.state='active' AND g.expires_at>:now
                       ORDER BY g.updated_at DESC,g.id"""
                ),
                {"user": user_id, "now": utcnow()},
            )
            values: list[tuple[GrantRecord, str]] = []
            for row in rows:
                grant = await self._grant_record(conn, row[0])
                if grant is not None:
                    values.append((grant, str(row[1])))
            return tuple(values)

    async def upsert_grant(
        self,
        *,
        user_id: str,
        client_id: UUID,
        canonical_resource: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        consent_granted_by: str,
        correlation_id: str | None = None,
    ) -> GrantRecord:
        """Create or explicitly re-consent a user-level human grant."""
        grant_id = uuid4()
        now = utcnow()
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:boundary))"),
                {
                    "boundary": ":".join(
                        (
                            "mcp-grant",
                            user_id,
                            str(client_id),
                            canonical_resource,
                        )
                    )
                },
            )
            parameters = {
                "uid": user_id,
                "cid": client_id,
                "resource": canonical_resource,
            }
            existing = await conn.scalar(
                text(
                    """SELECT id FROM ima.mcp_grants
                       WHERE user_id=:uid AND client_id=:cid AND canonical_resource=:resource
                         AND state='active' FOR UPDATE"""
                ),
                parameters,
            )
            if existing:
                grant_id = UUID(str(existing))
                await conn.execute(
                    text(
                        """UPDATE ima.mcp_grants SET scopes=:scopes,expires_at=:expires,
                           consent_granted_by=:actor,updated_at=:now WHERE id=:id"""
                    ),
                    {
                        "id": grant_id,
                        "scopes": list(scopes),
                        "expires": expires_at,
                        "actor": consent_granted_by,
                        "now": now,
                    },
                )
            else:
                await conn.execute(
                    text(
                        """INSERT INTO ima.mcp_grants(id,user_id,client_id,canonical_resource,
                           scopes,state,revocation_epoch,expires_at,created_at,updated_at,consent_granted_by)
                           VALUES (:id,:uid,:cid,:resource,:scopes,'active',0,:expires,:now,:now,:actor)"""
                    ),
                    {
                        "id": grant_id,
                        **parameters,
                        "scopes": list(scopes),
                        "expires": expires_at,
                        "now": now,
                        "actor": consent_granted_by,
                    },
                )
            await self._audit(
                conn,
                consent_granted_by,
                "oauth.grant.approved",
                "success",
                target_type="oauth_grant",
                target_id=str(grant_id),
                metadata={"scopes": list(scopes)},
                correlation_id=correlation_id,
            )
        async with self.engine.connect() as conn:
            grant = await self._grant_record(conn, grant_id)
        assert grant is not None
        return grant

    async def revoke_grant(
        self,
        grant_id: UUID,
        *,
        actor_id: str | None,
        reason: str,
        correlation_id: str | None = None,
    ) -> None:
        """Revoke a grant; all subordinate codes/tokens/families are denied next lookup."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.mcp_grants SET state='revoked',revoked_at=:now,revoke_reason=:reason,"
                    "revocation_epoch=revocation_epoch+1,updated_at=:now WHERE id=:id AND state='active'"
                ),
                {"id": grant_id, "now": utcnow(), "reason": reason},
            )
            await self._audit(
                conn,
                actor_id,
                "oauth.grant.revoked",
                "success",
                target_type="oauth_grant",
                target_id=str(grant_id),
                reason=reason,
                correlation_id=correlation_id,
            )

    async def revoke_grants_for_user(
        self,
        user_id: str,
        *,
        actor_id: str | None,
        reason: str,
        correlation_id: str | None = None,
    ) -> None:
        """Revoke every active grant for a user (disablement/password change path)."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.mcp_grants SET state='revoked',revoked_at=:now,revoke_reason=:reason,"
                    "revocation_epoch=revocation_epoch+1,updated_at=:now WHERE user_id=:uid AND state='active'"
                ),
                {"uid": user_id, "now": utcnow(), "reason": reason},
            )
            await self._audit(
                conn,
                actor_id,
                "oauth.grant.revoked_all",
                "success",
                target_type="user",
                target_id=user_id,
                reason=reason,
                metadata={"scope": "user"},
                correlation_id=correlation_id,
            )

    # ------------------------------------------------------------------
    # Authorization codes
    # ------------------------------------------------------------------

    async def create_authorization_code(
        self,
        *,
        grant_id: UUID,
        user_id: str,
        client_id: UUID,
        redirect_uri: str,
        canonical_resource: str,
        scopes: tuple[str, ...],
        code_challenge: str,
        security_stamp: str,
        state: str,
        expires_at: datetime,
        correlation_id: str | None = None,
    ) -> tuple[str, AuthorizationCodeRecord]:
        """Create a one-time authorization code.

        The raw code is returned exactly once and only the pepper digest is
        stored.  Creation is atomic with an audit ``oauth.code.issued`` row.
        """
        raw_code = new_oauth_value()
        code_uuid = uuid4()
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """INSERT INTO ima.mcp_authorization_codes(id,code_digest,grant_id,user_id,client_id,redirect_uri,
                       canonical_resource,scopes,code_challenge,code_challenge_method,
                       security_stamp,state,expires_at,created_at)
                       VALUES (:id,:digest,:grant,:uid,:cid,:redirect,:resource,:scopes,:challenge,'S256',
                               :stamp,:state,:expires,:now)"""
                ),
                {
                    "id": code_uuid,
                    "digest": self._token_digest(raw_code),
                    "grant": grant_id,
                    "uid": user_id,
                    "cid": client_id,
                    "redirect": redirect_uri,
                    "resource": canonical_resource,
                    "scopes": list(scopes),
                    "challenge": code_challenge,
                    "stamp": security_stamp,
                    "state": state,
                    "expires": expires_at,
                    "now": utcnow(),
                },
            )
            await self._audit(
                conn,
                user_id,
                "oauth.code.issued",
                "success",
                target_type="oauth_grant",
                target_id=str(grant_id),
                metadata={"client_id": str(client_id)},
                correlation_id=correlation_id,
            )
        async with self.engine.connect() as conn:
            record = await self._authorization_code_record(conn, code_uuid)
        assert record is not None
        return raw_code, record

    async def _authorization_code_record(
        self, conn: Any, code_id: Any
    ) -> AuthorizationCodeRecord | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT id,grant_id,user_id,client_id,redirect_uri,canonical_resource,
                                  scopes,code_challenge,state,expires_at
                           FROM ima.mcp_authorization_codes WHERE id=:id"""
                    ),
                    {"id": code_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return AuthorizationCodeRecord(
            id=UUID(str(row["id"])),
            grant_id=UUID(str(row["grant_id"])),
            user_id=str(row["user_id"]),
            client_id=UUID(str(row["client_id"])),
            redirect_uri=str(row["redirect_uri"]),
            canonical_resource=str(row["canonical_resource"]),
            scopes=tuple(row["scopes"]),
            code_challenge=str(row["code_challenge"]),
            expires_at=row["expires_at"],
            state=str(row["state"]),
        )

    async def consume_authorization_code(
        self,
        raw_code: str,
        *,
        expected_client_id: UUID,
        expected_redirect_uri: str,
        expected_resource: str,
        expected_code_challenge: str,
        correlation_id: str | None = None,
    ) -> AuthorizationCodeRecord:
        """Atomically consume a one-time authorization code.

        Runs in a single locked transaction with a row lock on the code row.
        A second exchange (replay) fails with ``used_code`` and revokes the
        grant as the reuse of an authorization code is a strong signal of an
        attacker.  Verification of client/redirect/resource binding happens in
        the same transaction before the code is marked used.
        """
        now = utcnow()
        deferred_error: McpRepositoryError | None = None
        record: AuthorizationCodeRecord | None = None
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.*,g.state AS grant_state,g.user_id AS grant_user,
                                      g.client_id AS grant_client,g.canonical_resource AS grant_resource,
                                      g.scopes AS grant_scopes,g.expires_at AS grant_expires,
                                      client.is_enabled AS client_enabled,
                                      client.canonical_resource AS client_resource,
                                      u.is_active AS user_active,u.security_stamp AS current_security_stamp,
                                      EXISTS (
                                        SELECT 1 FROM ima.mcp_client_redirects redirect
                                        WHERE redirect.client_id=c.client_id
                                          AND redirect.redirect_uri=c.redirect_uri
                                      ) AS redirect_registered
                               FROM ima.mcp_authorization_codes c
                               JOIN ima.mcp_grants g ON g.id=c.grant_id
                               JOIN ima.mcp_clients client ON client.id=c.client_id
                               JOIN ima.users u ON u.id=c.user_id
                               WHERE c.code_digest=:digest FOR UPDATE"""
                        ),
                        {"digest": self._token_digest(raw_code)},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    reason="invalid_code",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError("invalid_code", "authorization code not found")
            elif row["used_at"] is not None:
                # Reuse of a code: revoke the whole grant and deny.
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_grants SET state='revoked',revoked_at=:now,revoke_reason='code_reuse',"
                        "revocation_epoch=revocation_epoch+1,updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["grant_id"], "now": now},
                )
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    target_type="oauth_code",
                    target_id=str(row["id"]),
                    reason="used_code",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "used_code", "authorization code was already used"
                )
            elif row["expires_at"] <= now:
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    target_type="oauth_code",
                    target_id=str(row["id"]),
                    reason="expired_code",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "expired_code", "authorization code has expired"
                )
            elif row["grant_state"] != "active" or row["grant_expires"] <= now:
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    target_type="oauth_code",
                    target_id=str(row["id"]),
                    reason="inactive_grant",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "invalid_grant", "the underlying grant is not active"
                )
            elif (
                UUID(str(row["client_id"])) != expected_client_id
                or UUID(str(row["grant_client"])) != expected_client_id
                or not row["client_enabled"]
            ):
                deferred_error = McpRepositoryError(
                    "invalid_client", "authorization code client mismatch"
                )
            elif (
                str(row["redirect_uri"]) != expected_redirect_uri or not row["redirect_registered"]
            ):
                deferred_error = McpRepositoryError(
                    "invalid_redirect", "authorization code redirect mismatch"
                )
            elif (
                str(row["canonical_resource"]) != expected_resource
                or str(row["grant_resource"]) != expected_resource
                or str(row["client_resource"]) != expected_resource
            ):
                deferred_error = McpRepositoryError(
                    "invalid_resource", "authorization code resource mismatch"
                )
            elif str(row["user_id"]) != str(row["grant_user"]):
                deferred_error = McpRepositoryError(
                    "invalid_grant", "authorization code user mismatch"
                )
            elif not row["user_active"] or not secrets.compare_digest(
                str(row["security_stamp"]), str(row["current_security_stamp"])
            ):
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    target_type="oauth_code",
                    target_id=str(row["id"]),
                    reason="security_state_changed",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "invalid_grant", "authorization code security state changed"
                )
            elif not set(row["scopes"]).issubset(set(row["grant_scopes"])):
                deferred_error = McpRepositoryError(
                    "invalid_grant", "authorization code grant binding mismatch"
                )
            elif not secrets.compare_digest(str(row["code_challenge"]), expected_code_challenge):
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    target_type="oauth_code",
                    target_id=str(row["id"]),
                    reason="verifier_mismatch",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "verifier_mismatch", "authorization code verifier mismatch"
                )
            else:
                await conn.execute(
                    text("UPDATE ima.mcp_authorization_codes SET used_at=:now WHERE id=:id"),
                    {"id": row["id"], "now": now},
                )
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_grants SET last_used_at=:now,updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["grant_id"], "now": now},
                )
                await self._audit(
                    conn,
                    row["grant_user"],
                    "oauth.code.exchanged",
                    "success",
                    target_type="oauth_grant",
                    target_id=str(row["grant_id"]),
                    correlation_id=correlation_id,
                )
                record = AuthorizationCodeRecord(
                    id=UUID(str(row["id"])),
                    grant_id=UUID(str(row["grant_id"])),
                    user_id=str(row["grant_user"]),
                    client_id=UUID(str(row["client_id"])),
                    redirect_uri=str(row["redirect_uri"]),
                    canonical_resource=str(row["canonical_resource"]),
                    scopes=tuple(row["scopes"]),
                    code_challenge=str(row["code_challenge"]),
                    expires_at=row["expires_at"],
                    state=str(row["state"]),
                )
        if deferred_error is not None:
            raise deferred_error
        assert record is not None
        return record

    async def exchange_authorization_code_bundle(
        self,
        raw_code: str,
        *,
        expected_client_id: UUID,
        expected_redirect_uri: str,
        expected_resource: str,
        expected_code_challenge: str,
        correlation_id: str | None = None,
    ) -> AuthorizationTokenBundle:
        """Consume a code and issue its complete token bundle in one transaction."""
        now = utcnow()
        deferred_error: McpRepositoryError | None = None
        bundle: AuthorizationTokenBundle | None = None
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.*,g.state AS grant_state,g.user_id AS grant_user,
                                      g.client_id AS grant_client,g.canonical_resource AS grant_resource,
                                      g.scopes AS grant_scopes,g.expires_at AS grant_expires,
                                      client.is_enabled AS client_enabled,
                                      client.canonical_resource AS client_resource,
                                      u.is_active AS user_active,u.security_stamp AS current_security_stamp,
                                      EXISTS (SELECT 1 FROM ima.mcp_client_redirects redirect
                                        WHERE redirect.client_id=c.client_id AND redirect.redirect_uri=c.redirect_uri) AS redirect_registered
                               FROM ima.mcp_authorization_codes c
                               JOIN ima.mcp_grants g ON g.id=c.grant_id
                               JOIN ima.mcp_clients client ON client.id=c.client_id
                               JOIN ima.users u ON u.id=c.user_id
                               WHERE c.code_digest=:digest FOR UPDATE OF c,g"""
                        ),
                        {"digest": self._token_digest(raw_code)},
                    )
                )
                .mappings()
                .first()
            )
            reason: str | None = None
            if not row:
                reason = "invalid_code"
            elif row["used_at"] is not None:
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_grants SET state='revoked',revoked_at=:now,revoke_reason='code_reuse',revocation_epoch=revocation_epoch+1,updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["grant_id"], "now": now},
                )
                reason = "used_code"
            elif row["expires_at"] <= now:
                reason = "expired_code"
            elif (
                row["grant_state"] != "active"
                or row["grant_expires"] <= now
                or not row["user_active"]
                or not row["client_enabled"]
            ):
                reason = "invalid_grant"
            elif (
                UUID(str(row["client_id"])) != expected_client_id
                or UUID(str(row["grant_client"])) != expected_client_id
            ):
                reason = "invalid_client"
            elif (
                str(row["redirect_uri"]) != expected_redirect_uri or not row["redirect_registered"]
            ):
                reason = "invalid_redirect"
            elif (
                str(row["canonical_resource"]) != expected_resource
                or str(row["grant_resource"]) != expected_resource
                or str(row["client_resource"]) != expected_resource
            ):
                reason = "invalid_resource"
            elif str(row["user_id"]) != str(row["grant_user"]) or not secrets.compare_digest(
                str(row["security_stamp"]), str(row["current_security_stamp"])
            ):
                reason = "invalid_grant"
            elif not set(row["scopes"]).issubset(set(row["grant_scopes"])):
                reason = "invalid_grant"
            elif not secrets.compare_digest(str(row["code_challenge"]), expected_code_challenge):
                reason = "verifier_mismatch"
            if reason is not None:
                await self._audit(
                    conn,
                    None,
                    "oauth.code.exchanged",
                    "failure",
                    target_type="oauth_code" if row else None,
                    target_id=str(row["id"]) if row else None,
                    reason=reason,
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(reason, "authorization code exchange failed")
            else:
                assert row is not None
                access_id, family_id, refresh_id = uuid4(), uuid4(), uuid4()
                raw_access, raw_refresh = new_oauth_value(), new_oauth_value()
                access_expiry = min(
                    row["grant_expires"],
                    now + timedelta(seconds=self.settings.oauth_access_token_seconds),
                )
                absolute_expiry = min(
                    row["grant_expires"],
                    now + timedelta(seconds=self.settings.oauth_refresh_absolute_seconds),
                )
                refresh_expiry = min(
                    absolute_expiry,
                    now + timedelta(seconds=self.settings.oauth_refresh_rolling_seconds),
                )
                await conn.execute(
                    text("UPDATE ima.mcp_authorization_codes SET used_at=:now WHERE id=:id"),
                    {"id": row["id"], "now": now},
                )
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_grants SET last_used_at=:now,updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["grant_id"], "now": now},
                )
                await conn.execute(
                    text("""INSERT INTO ima.mcp_access_tokens(id,token_digest,grant_id,principal_id,client_id,canonical_resource,scopes,security_stamp,expires_at,created_at)
                    VALUES (:id,:digest,:grant,NULL,:client,:resource,:scopes,:stamp,:expires,:now)"""),
                    {
                        "id": access_id,
                        "digest": self._token_digest(raw_access),
                        "grant": row["grant_id"],
                        "client": row["client_id"],
                        "resource": expected_resource,
                        "scopes": list(row["scopes"]),
                        "stamp": row["current_security_stamp"],
                        "expires": access_expiry,
                        "now": now,
                    },
                )
                await conn.execute(
                    text(
                        "INSERT INTO ima.mcp_refresh_families(id,grant_id,rotated_generation,absolute_expires_at,security_stamp,created_at) VALUES (:id,:grant,0,:expires,:stamp,:now)"
                    ),
                    {
                        "id": family_id,
                        "grant": row["grant_id"],
                        "expires": absolute_expiry,
                        "stamp": row["current_security_stamp"],
                        "now": now,
                    },
                )
                await conn.execute(
                    text("""INSERT INTO ima.mcp_refresh_tokens(id,token_digest,family_id,grant_id,client_id,canonical_resource,scopes,issued_at,expires_at)
                    VALUES (:id,:digest,:family,:grant,:client,:resource,:scopes,:now,:expires)"""),
                    {
                        "id": refresh_id,
                        "digest": self._token_digest(raw_refresh),
                        "family": family_id,
                        "grant": row["grant_id"],
                        "client": row["client_id"],
                        "resource": expected_resource,
                        "scopes": list(row["scopes"]),
                        "now": now,
                        "expires": refresh_expiry,
                    },
                )
                await self._audit(
                    conn,
                    row["grant_user"],
                    "oauth.code.exchanged",
                    "success",
                    target_type="oauth_grant",
                    target_id=str(row["grant_id"]),
                    correlation_id=correlation_id,
                )
                await self._audit(
                    conn,
                    row["grant_user"],
                    "oauth.access_token.issued",
                    "success",
                    target_type="oauth_grant",
                    target_id=str(row["grant_id"]),
                    metadata={"scopes": list(row["scopes"])},
                    correlation_id=correlation_id,
                )
                await self._audit(
                    conn,
                    row["grant_user"],
                    "oauth.refresh_token.issued",
                    "success",
                    target_type="oauth_grant",
                    target_id=str(row["grant_id"]),
                    correlation_id=correlation_id,
                )
                code_record = AuthorizationCodeRecord(
                    id=UUID(str(row["id"])),
                    grant_id=UUID(str(row["grant_id"])),
                    user_id=str(row["grant_user"]),
                    client_id=UUID(str(row["client_id"])),
                    redirect_uri=str(row["redirect_uri"]),
                    canonical_resource=str(row["canonical_resource"]),
                    scopes=tuple(row["scopes"]),
                    code_challenge=str(row["code_challenge"]),
                    expires_at=row["expires_at"],
                    state=str(row["state"]),
                )
                access_record = AccessTokenRecord(
                    id=access_id,
                    token_digest=self._token_digest(raw_access),
                    grant_id=UUID(str(row["grant_id"])),
                    principal_id=None,
                    client_id=expected_client_id,
                    canonical_resource=expected_resource,
                    scopes=tuple(row["scopes"]),
                    expires_at=access_expiry,
                    security_stamp=str(row["current_security_stamp"]),
                )
                refresh_record = RefreshTokenRecord(
                    id=refresh_id,
                    family_id=family_id,
                    grant_id=UUID(str(row["grant_id"])),
                    client_id=expected_client_id,
                    canonical_resource=expected_resource,
                    scopes=tuple(row["scopes"]),
                    token_digest=self._token_digest(raw_refresh),
                    expires_at=refresh_expiry,
                )
                bundle = AuthorizationTokenBundle(
                    raw_access, raw_refresh, access_record, refresh_record, code_record
                )
        if deferred_error is not None:
            raise deferred_error
        assert bundle is not None
        return bundle

    # ------------------------------------------------------------------
    # Access tokens
    # ------------------------------------------------------------------

    async def create_access_token(
        self,
        *,
        grant_id: UUID | None,
        principal_id: UUID | None,
        client_id: UUID | None,
        canonical_resource: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        security_stamp: str | None = None,
        correlation_id: str | None = None,
    ) -> tuple[str, AccessTokenRecord]:
        """Issue a short-lived opaque access token for `/mcp`.

        Exactly one of ``grant_id`` (human) or ``principal_id`` (service
        principal) must be set.  The raw token is returned once and only its
        pepper digest is stored.  Issuance is atomic with an audit row.
        """
        if (grant_id is None) == (principal_id is None):
            raise ValueError("exactly one of grant_id or principal_id must be set")
        now = utcnow()
        if expires_at <= now or expires_at > now + timedelta(
            seconds=self.settings.oauth_access_token_seconds
        ):
            raise McpRepositoryError(
                "invalid_expiry", "access token expiry exceeds the configured lifetime"
            )
        raw_token = new_oauth_value()
        token_uuid = uuid4()
        actor: str | None = None
        async with self.engine.begin() as conn:
            if grant_id is not None:
                binding = (
                    (
                        await conn.execute(
                            text(
                                """SELECT g.user_id,g.client_id,g.canonical_resource,
                                          g.scopes,g.expires_at,u.security_stamp,
                                          u.is_active,c.is_enabled,c.canonical_resource AS client_resource
                                   FROM ima.mcp_grants g
                                   JOIN ima.users u ON u.id=g.user_id
                                   JOIN ima.mcp_clients c ON c.id=g.client_id
                                   WHERE g.id=:id AND g.state='active' AND g.expires_at>:now
                                   FOR UPDATE OF g"""
                            ),
                            {"id": grant_id, "now": now},
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    not binding
                    or client_id != UUID(str(binding["client_id"]))
                    or canonical_resource != binding["canonical_resource"]
                    or canonical_resource != binding["client_resource"]
                    or not set(scopes).issubset(set(binding["scopes"]))
                    or not binding["is_active"]
                    or not binding["is_enabled"]
                    or security_stamp is None
                    or not secrets.compare_digest(security_stamp, str(binding["security_stamp"]))
                    or expires_at > binding["expires_at"]
                ):
                    raise McpRepositoryError(
                        "invalid_grant", "access token grant binding is not active"
                    )
                actor = str(binding["user_id"])
            else:
                binding = (
                    (
                        await conn.execute(
                            text(
                                """SELECT p.scopes,p.expires_at
                                   FROM ima.mcp_service_principals p
                                   WHERE p.id=:id AND p.state='active' AND p.expires_at>:now
                                   FOR UPDATE OF p"""
                            ),
                            {"id": principal_id, "now": now},
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    not binding
                    or client_id is not None
                    or security_stamp is not None
                    or canonical_resource != self.settings.mcp_resource_url
                    or not set(scopes).issubset(set(binding["scopes"]))
                    or expires_at > binding["expires_at"]
                ):
                    raise McpRepositoryError(
                        "invalid_principal", "access token principal binding is not active"
                    )
            await conn.execute(
                text(
                    """INSERT INTO ima.mcp_access_tokens(id,token_digest,grant_id,principal_id,client_id,
                       canonical_resource,scopes,security_stamp,expires_at,created_at)
                       VALUES (:id,:digest,:grant,:principal,:cid,:resource,:scopes,:stamp,:expires,:now)"""
                ),
                {
                    "id": token_uuid,
                    "digest": self._token_digest(raw_token),
                    "grant": grant_id,
                    "principal": principal_id,
                    "cid": client_id,
                    "resource": canonical_resource,
                    "scopes": list(scopes),
                    "stamp": security_stamp,
                    "expires": expires_at,
                    "now": now,
                },
            )
            await self._audit(
                conn,
                actor,
                "oauth.access_token.issued",
                "success",
                target_type="oauth_grant" if grant_id else "service_principal",
                target_id=str(grant_id or principal_id),
                metadata={"scopes": list(scopes)},
                correlation_id=correlation_id,
            )
        async with self.engine.connect() as conn:
            record = await self._access_token_record(conn, token_uuid)
        assert record is not None
        return raw_token, record

    async def _access_token_record(self, conn: Any, token_id: Any) -> AccessTokenRecord | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT id,token_digest,grant_id,principal_id,client_id,canonical_resource,
                                  scopes,security_stamp,expires_at,revoked_at
                           FROM ima.mcp_access_tokens WHERE id=:id"""
                    ),
                    {"id": token_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return AccessTokenRecord(
            id=UUID(str(row["id"])),
            token_digest=str(row["token_digest"]),
            grant_id=UUID(str(row["grant_id"])) if row["grant_id"] else None,
            principal_id=UUID(str(row["principal_id"])) if row["principal_id"] else None,
            client_id=UUID(str(row["client_id"])) if row["client_id"] else None,
            canonical_resource=str(row["canonical_resource"]),
            scopes=tuple(row["scopes"]),
            expires_at=row["expires_at"],
            security_stamp=row["security_stamp"],
        )

    async def load_access_token(
        self,
        raw_token: str,
        *,
        expected_resource: str,
        correlation_id: str | None = None,
    ) -> AccessTokenRecord | None:
        """Resolve an opaque access token by digest.

        Returns ``None`` for missing/expired/revoked/wrong-resource tokens;
        the caller decides whether to emit a ``401`` challenge.  Constant-time
        digest lookup never compares raw values.
        """
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT at.id,at.token_digest,at.grant_id,at.principal_id,at.client_id,
                                      at.canonical_resource,at.scopes,
                                      at.security_stamp,at.expires_at,at.revoked_at
                               FROM ima.mcp_access_tokens at
                               LEFT JOIN ima.mcp_grants g ON g.id=at.grant_id
                               LEFT JOIN ima.mcp_clients c ON c.id=g.client_id
                               LEFT JOIN ima.users u ON u.id=g.user_id
                               LEFT JOIN ima.mcp_service_principals p ON p.id=at.principal_id
                               LEFT JOIN ima.users po ON po.id=p.owner_user_id
                               WHERE at.token_digest=:digest AND at.revoked_at IS NULL
                                 AND at.canonical_resource=:resource AND at.expires_at>:now
                                 AND (
                                   (at.grant_id IS NOT NULL
                                    AND g.state='active' AND g.expires_at>:now
                                    AND g.client_id=at.client_id
                                    AND g.canonical_resource=at.canonical_resource
                                    AND at.scopes <@ g.scopes
                                    AND c.is_enabled AND c.canonical_resource=at.canonical_resource
                                    AND u.is_active AND u.security_stamp=at.security_stamp)
                                   OR
                                   (at.principal_id IS NOT NULL
                                    AND p.state='active' AND p.expires_at>:now
                                    AND po.is_active
                                    AND at.scopes <@ p.scopes)
                                 )"""
                        ),
                        {
                            "digest": self._token_digest(raw_token),
                            "resource": expected_resource,
                            "now": utcnow(),
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            return AccessTokenRecord(
                id=UUID(str(row["id"])),
                token_digest=str(row["token_digest"]),
                grant_id=UUID(str(row["grant_id"])) if row["grant_id"] else None,
                principal_id=UUID(str(row["principal_id"])) if row["principal_id"] else None,
                client_id=UUID(str(row["client_id"])) if row["client_id"] else None,
                canonical_resource=str(row["canonical_resource"]),
                scopes=tuple(row["scopes"]),
                expires_at=row["expires_at"],
                security_stamp=row["security_stamp"],
            )

    async def revoke_access_token(self, raw_token: str, *, reason: str) -> None:
        """Immediately revoke an access token (idempotent)."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.mcp_access_tokens SET revoked_at=:now,revoke_reason=:reason WHERE token_digest=:digest"
                ),
                {"now": utcnow(), "reason": reason, "digest": self._token_digest(raw_token)},
            )

    async def touch_access_token(self, token_id: UUID) -> None:
        """Update ``last_used_at`` for a resolved access token."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text("UPDATE ima.mcp_access_tokens SET last_used_at=:now WHERE id=:id"),
                {"id": token_id, "now": utcnow()},
            )

    # ------------------------------------------------------------------
    # Refresh families and rotating refresh tokens
    # ------------------------------------------------------------------

    async def _refresh_token_record(self, conn: Any, token_id: Any) -> RefreshTokenRecord | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT id,family_id,grant_id,client_id,canonical_resource,
                                  scopes,token_digest,expires_at,replaced_at,replaced_by,revoked_at
                           FROM ima.mcp_refresh_tokens WHERE id=:id"""
                    ),
                    {"id": token_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return RefreshTokenRecord(
            id=UUID(str(row["id"])),
            family_id=UUID(str(row["family_id"])),
            grant_id=UUID(str(row["grant_id"])),
            client_id=UUID(str(row["client_id"])),
            canonical_resource=str(row["canonical_resource"]),
            scopes=tuple(row["scopes"]),
            token_digest=str(row["token_digest"]),
            expires_at=row["expires_at"],
            replaced_at=row["replaced_at"],
            replaced_by=UUID(str(row["replaced_by"])) if row["replaced_by"] else None,
        )

    async def exchange_refresh_token_bundle(
        self,
        raw_refresh: str,
        *,
        expected_client_id: UUID,
        expected_resource: str,
        requested_scopes: tuple[str, ...] | None,
        correlation_id: str | None = None,
    ) -> RefreshAccessTokenBundle:
        """Rotate a refresh token and issue its access token atomically.

        In one locked transaction this method:
        - resolves the presented refresh token by digest with a row lock;
        - rejects expired/revoked/wrong-resource tokens;
        - if the token was already replaced (replay), revokes the whole family
          and the grant, then raises ``refresh_reuse``;
        - verifies the grant is still active and not expired;
        - marks the presented token replaced, creates the next token in the
          family, issues the bound access token, updates family/grant usage, and
          audits all writes.

        ``requested_scopes`` may only be a subset of the grant scope set;
        widening is rejected before any write.
        """
        now = utcnow()
        deferred_error: McpRepositoryError | None = None
        result: RefreshAccessTokenBundle | None = None
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT rt.*,f.absolute_expires_at AS family_absolute,f.security_stamp AS family_stamp,
                                      f.revoked_at AS family_revoked,f.rotated_generation AS family_generation,
                                      g.state AS grant_state,g.scopes AS grant_scopes,g.expires_at AS grant_expires,
                                      f.grant_id AS family_grant,g.user_id AS grant_user,
                                      g.client_id AS grant_client,
                                      g.canonical_resource AS grant_resource,u.is_active AS user_active,
                                      u.security_stamp AS current_security_stamp,c.is_enabled AS client_enabled,
                                      c.canonical_resource AS client_resource
                               FROM ima.mcp_refresh_tokens rt
                               JOIN ima.mcp_refresh_families f ON f.id=rt.family_id
                               JOIN ima.mcp_grants g ON g.id=rt.grant_id
                               JOIN ima.users u ON u.id=g.user_id
                               JOIN ima.mcp_clients c ON c.id=g.client_id
                               WHERE rt.token_digest=:digest
                               FOR UPDATE OF rt,f,g,u,c"""
                        ),
                        {"digest": self._token_digest(raw_refresh)},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                await self._audit(
                    conn,
                    None,
                    "oauth.refresh_token.rotated",
                    "failure",
                    reason="invalid_refresh",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError("invalid_grant", "refresh token not found")
            elif row["family_revoked"] is not None or row["revoked_at"] is not None:
                await self._audit(
                    conn,
                    None,
                    "oauth.refresh_token.rotated",
                    "failure",
                    reason="revoked_refresh",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "invalid_grant", "refresh token has been revoked"
                )
            elif row["replaced_at"] is not None or row["replaced_by"] is not None:
                # A recognized rotated secret is replay even if the client,
                # user, or target boundary changed after its original use.
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_refresh_families SET revoked_at=:now,revoke_reason='refresh_reuse',"
                        "replay_detected_at=:now WHERE id=:id"
                    ),
                    {"id": row["family_id"], "now": now},
                )
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_grants SET state='revoked',revoked_at=:now,revoke_reason='refresh_reuse',"
                        "revocation_epoch=revocation_epoch+1,updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["grant_id"], "now": now},
                )
                await self._audit(
                    conn,
                    None,
                    "oauth.refresh_token.replay",
                    "failure",
                    target_type="oauth_grant",
                    target_id=str(row["grant_id"]),
                    reason="refresh_reuse",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "refresh_reuse", "refresh token reuse detected; family revoked"
                )
            elif (
                row["expires_at"] <= now
                or row["family_absolute"] <= now
                or row["grant_expires"] <= now
            ):
                await self._audit(
                    conn,
                    None,
                    "oauth.refresh_token.rotated",
                    "failure",
                    reason="expired_refresh",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError("invalid_grant", "refresh token has expired")
            elif row["grant_state"] != "active":
                await self._audit(
                    conn,
                    None,
                    "oauth.refresh_token.rotated",
                    "failure",
                    reason="inactive_grant",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "invalid_grant", "the underlying grant is not active"
                )
            elif (
                UUID(str(row["client_id"])) != expected_client_id
                or UUID(str(row["grant_client"])) != expected_client_id
                or UUID(str(row["family_grant"])) != UUID(str(row["grant_id"]))
                or not row["client_enabled"]
                or str(row["canonical_resource"]) != expected_resource
                or str(row["grant_resource"]) != expected_resource
                or str(row["client_resource"]) != expected_resource
                or not set(row["scopes"]).issubset(set(row["grant_scopes"]))
                or not row["user_active"]
                or not secrets.compare_digest(
                    str(row["family_stamp"]), str(row["current_security_stamp"])
                )
            ):
                await self._audit(
                    conn,
                    None,
                    "oauth.refresh_token.rotated",
                    "failure",
                    reason="binding_mismatch",
                    correlation_id=correlation_id,
                )
                deferred_error = McpRepositoryError(
                    "invalid_grant", "refresh token binding is no longer valid"
                )
            else:
                grant_scopes = tuple(row["grant_scopes"])
                token_scopes = tuple(row["scopes"])
                if requested_scopes is not None:
                    if not set(requested_scopes).issubset(set(token_scopes)):
                        await self._audit(
                            conn,
                            None,
                            "oauth.refresh_token.rotated",
                            "failure",
                            target_type="oauth_grant",
                            target_id=str(row["grant_id"]),
                            reason="scope_widening",
                            correlation_id=correlation_id,
                        )
                        deferred_error = McpRepositoryError(
                            "invalid_scope", "refresh cannot widen the grant scope"
                        )
                    else:
                        new_scopes = requested_scopes
                else:
                    new_scopes = token_scopes

                if deferred_error is None:
                    if not set(new_scopes).issubset(set(grant_scopes)):
                        deferred_error = McpRepositoryError(
                            "invalid_scope", "refresh scope exceeds the underlying grant"
                        )
                if deferred_error is None:
                    old_id = UUID(str(row["id"]))
                    family_id = UUID(str(row["family_id"]))
                    new_token_id = uuid4()
                    new_raw = new_oauth_value()
                    access_token_id = uuid4()
                    raw_access = new_oauth_value()
                    refresh_expiry = min(
                        now + timedelta(seconds=self.settings.oauth_refresh_rolling_seconds),
                        row["family_absolute"],
                        row["grant_expires"],
                    )
                    access_expiry = min(
                        now + timedelta(seconds=self.settings.oauth_access_token_seconds),
                        row["family_absolute"],
                        row["grant_expires"],
                    )
                    await conn.execute(
                        text(
                            "UPDATE ima.mcp_refresh_tokens SET replaced_at=:now,replaced_by=:next WHERE id=:id"
                        ),
                        {"id": old_id, "now": now, "next": new_token_id},
                    )
                    await conn.execute(
                        text(
                            """INSERT INTO ima.mcp_refresh_tokens(id,token_digest,family_id,grant_id,client_id,
                           canonical_resource,scopes,issued_at,expires_at,replaced_at,replaced_by)
                           VALUES (:id,:digest,:family,:grant,:cid,:resource,:scopes,:now,:expires,NULL,NULL)"""
                        ),
                        {
                            "id": new_token_id,
                            "digest": self._token_digest(new_raw),
                            "family": family_id,
                            "grant": row["grant_id"],
                            "cid": row["client_id"],
                            "resource": expected_resource,
                            "scopes": list(new_scopes),
                            "now": now,
                            "expires": refresh_expiry,
                        },
                    )
                    await conn.execute(
                        text(
                            """INSERT INTO ima.mcp_access_tokens(id,token_digest,grant_id,principal_id,client_id,
                               canonical_resource,scopes,security_stamp,expires_at,created_at)
                               VALUES (:id,:digest,:grant,NULL,:client,:resource,:scopes,:stamp,:expires,:now)"""
                        ),
                        {
                            "id": access_token_id,
                            "digest": self._token_digest(raw_access),
                            "grant": row["grant_id"],
                            "client": row["client_id"],
                            "resource": expected_resource,
                            "scopes": list(new_scopes),
                            "stamp": row["current_security_stamp"],
                            "expires": access_expiry,
                            "now": now,
                        },
                    )
                    await conn.execute(
                        text(
                            "UPDATE ima.mcp_refresh_families SET rotated_generation=rotated_generation+1 WHERE id=:id"
                        ),
                        {"id": family_id},
                    )
                    await conn.execute(
                        text(
                            "UPDATE ima.mcp_grants SET last_used_at=:now,updated_at=:now WHERE id=:id"
                        ),
                        {"id": row["grant_id"], "now": now},
                    )
                    await self._audit(
                        conn,
                        str(row["grant_user"]),
                        "oauth.refresh_token.rotated",
                        "success",
                        target_type="oauth_grant",
                        target_id=str(row["grant_id"]),
                        metadata={"scopes": list(new_scopes)},
                        correlation_id=correlation_id,
                    )
                    await self._audit(
                        conn,
                        str(row["grant_user"]),
                        "oauth.access_token.issued",
                        "success",
                        target_type="oauth_grant",
                        target_id=str(row["grant_id"]),
                        metadata={"scopes": list(new_scopes)},
                        correlation_id=correlation_id,
                    )
                    grant = await self._grant_record(conn, row["grant_id"])
                    assert grant is not None
                    new_record = await self._refresh_token_record(conn, new_token_id)
                    assert new_record is not None
                    access_record = await self._access_token_record(conn, access_token_id)
                    assert access_record is not None
                    result = RefreshAccessTokenBundle(
                        raw_access,
                        new_raw,
                        access_record,
                        new_record,
                        grant,
                    )
        if deferred_error is not None:
            raise deferred_error
        assert result is not None
        return result

    async def revoke_refresh_token(self, raw_refresh: str, *, reason: str) -> None:
        """Idempotently revoke a refresh token and its complete family."""
        now = utcnow()
        async with self.engine.begin() as conn:
            family_id = await conn.scalar(
                text("SELECT family_id FROM ima.mcp_refresh_tokens WHERE token_digest=:digest"),
                {"digest": self._token_digest(raw_refresh)},
            )
            if family_id is None:
                return
            await conn.execute(
                text(
                    "UPDATE ima.mcp_refresh_tokens SET revoked_at=COALESCE(revoked_at,:now),revoke_reason=COALESCE(revoke_reason,:reason) WHERE family_id=:family"
                ),
                {"now": now, "reason": reason, "family": family_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.mcp_refresh_families SET revoked_at=COALESCE(revoked_at,:now),revoke_reason=COALESCE(revoke_reason,:reason) WHERE id=:family"
                ),
                {"now": now, "reason": reason, "family": family_id},
            )

    async def _service_principal_record(
        self, conn: Any, principal_id: Any
    ) -> ServicePrincipalRecord | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT id,display_name,purpose,owner_user_id,scopes,state,
                                  expires_at,cidr_allowlist,rate_limit,concurrency_limit
                           FROM ima.mcp_service_principals WHERE id=:id"""
                    ),
                    {"id": principal_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return ServicePrincipalRecord(
            id=UUID(str(row["id"])),
            display_name=str(row["display_name"]),
            purpose=str(row["purpose"]),
            owner_user_id=str(row["owner_user_id"]),
            scopes=tuple(row["scopes"]),
            state=row["state"],
            expires_at=row["expires_at"],
            rate_limit=int(row["rate_limit"]),
            concurrency_limit=int(row["concurrency_limit"]),
            cidr_allowlist=tuple(row["cidr_allowlist"] or ()),
        )

    async def load_service_principal(
        self, principal_id: UUID, *, include_inactive: bool = False
    ) -> ServicePrincipalRecord | None:
        """Load a service principal, optionally including disabled/revoked rows."""
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT id,display_name,purpose,owner_user_id,scopes,state,
                                      expires_at,cidr_allowlist,rate_limit,concurrency_limit
                               FROM ima.mcp_service_principals
                               WHERE id=:id AND (:include_inactive OR (state='active' AND expires_at>:now))"""
                        ),
                        {"id": principal_id, "include_inactive": include_inactive, "now": utcnow()},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            return ServicePrincipalRecord(
                id=UUID(str(row["id"])),
                display_name=str(row["display_name"]),
                purpose=str(row["purpose"]),
                owner_user_id=str(row["owner_user_id"]),
                scopes=tuple(row["scopes"]),
                state=row["state"],
                expires_at=row["expires_at"],
                rate_limit=int(row["rate_limit"]),
                concurrency_limit=int(row["concurrency_limit"]),
                cidr_allowlist=tuple(row["cidr_allowlist"] or ()),
            )

    async def set_principal_state(
        self,
        principal_id: UUID,
        state: str,
        *,
        actor_id: str | None,
        reason: str,
        correlation_id: str | None = None,
    ) -> None:
        """Disable or revoke a service principal immediately."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.mcp_service_principals SET state=CAST(:state AS varchar(16)),revoked_at=CASE WHEN CAST(:state AS varchar(16))='revoked' THEN :now ELSE revoked_at END,"
                    "revoke_reason=:reason,updated_at=:now WHERE id=:id"
                ),
                {"id": principal_id, "state": state, "now": utcnow(), "reason": reason},
            )
            await self._audit(
                conn,
                actor_id,
                f"mcp.service_principal.{state}",
                "success",
                target_type="service_principal",
                target_id=str(principal_id),
                reason=reason,
                correlation_id=correlation_id,
            )

    async def create_credential(
        self,
        *,
        principal_id: UUID,
        created_by: str | None,
        expires_at: datetime,
        overlap_expires_at: datetime | None = None,
        correlation_id: str | None = None,
    ) -> tuple[str, CredentialRecord]:
        """Issue a service credential; returns ``(raw_secret, record)`` once.

        The raw secret is returned exactly once and only its pepper digest is
        stored.  ``expires_at`` is required and must be within the configured
        maximum.  A finite overlap expiry may be set for unattended rotation and
        never exceeds the configured overlap cap.  Issue commits atomically with
        an audit row.
        """
        now = utcnow()
        if expires_at <= now:
            raise McpRepositoryError("invalid_expiry", "credential expiry must be in the future")
        if expires_at - now > timedelta(seconds=self.settings.service_credential_max_seconds):
            raise McpRepositoryError(
                "expiry_too_long",
                "credential expiry exceeds the configured maximum",
            )
        if overlap_expires_at is not None:
            if overlap_expires_at <= now:
                raise McpRepositoryError(
                    "invalid_overlap", "credential overlap expiry must be in the future"
                )
            if overlap_expires_at > expires_at:
                raise McpRepositoryError(
                    "invalid_overlap", "credential overlap cannot extend beyond expiry"
                )
            if overlap_expires_at - now > timedelta(
                seconds=self.settings.credential_rotation_overlap_seconds
            ):
                raise McpRepositoryError(
                    "invalid_overlap", "credential overlap exceeds the configured maximum"
                )
        credential_uuid = uuid4()
        async with self.engine.begin() as conn:
            principal = (
                (
                    await conn.execute(
                        text(
                            """SELECT expires_at FROM ima.mcp_service_principals
                               WHERE id=:id AND state='active' AND expires_at>:now
                               FOR UPDATE"""
                        ),
                        {"id": principal_id, "now": now},
                    )
                )
                .mappings()
                .first()
            )
            if not principal:
                raise McpRepositoryError("invalid_principal", "active principal not found")
            if expires_at > principal["expires_at"]:
                raise McpRepositoryError(
                    "invalid_expiry", "credential cannot outlive its service principal"
                )
            raw_secret = new_oauth_value()
            await conn.execute(
                text(
                    """INSERT INTO ima.mcp_credentials(id,principal_id,credential_id,digest,secret_prefix,created_at,
                       created_by,expires_at,overlap_expires_at)
                       VALUES (:id,:principal,:cid,:digest,:prefix,:now,:created_by,:expires,:overlap)"""
                ),
                {
                    "id": credential_uuid,
                    "principal": principal_id,
                    "cid": credential_id(),
                    "digest": self._token_digest(raw_secret),
                    "prefix": secret_prefix(),
                    "now": now,
                    "created_by": created_by,
                    "expires": expires_at,
                    "overlap": overlap_expires_at,
                },
            )
            await self._audit(
                conn,
                created_by,
                "mcp.credential.issued",
                "success",
                target_type="service_principal",
                target_id=str(principal_id),
                metadata={"credential_id": str(credential_uuid)},
                correlation_id=correlation_id,
            )
        async with self.engine.connect() as conn:
            record = await self._credential_record(conn, credential_uuid)
        assert record is not None
        return raw_secret, record

    async def _credential_record(self, conn: Any, credential_uuid: Any) -> CredentialRecord | None:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT id,principal_id,credential_id,digest,secret_prefix,expires_at,created_at,revoked_at,
                                  revoke_reason,last_used_at,replaced_by
                           FROM ima.mcp_credentials WHERE id=:id"""
                    ),
                    {"id": credential_uuid},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            return None
        return CredentialRecord(
            id=UUID(str(row["id"])),
            principal_id=UUID(str(row["principal_id"])),
            credential_id=str(row["credential_id"]),
            digest=str(row["digest"]),
            secret_prefix=str(row["secret_prefix"]),
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            revoked_at=row["revoked_at"],
            revoke_reason=row["revoke_reason"],
            last_used_at=row["last_used_at"],
            replaced_by=UUID(str(row["replaced_by"])) if row["replaced_by"] else None,
        )

    async def find_credential_by_id(self, credential_id: str) -> CredentialRecord | None:
        """Look up a credential by its nonsecret key ID (with its principal state)."""
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.id FROM ima.mcp_credentials c
                               JOIN ima.mcp_service_principals p ON p.id=c.principal_id
                               WHERE c.credential_id=:cid AND p.state='active' AND p.expires_at>:now
                                  AND c.revoked_at IS NULL AND c.expires_at>:now
                                  AND (c.overlap_expires_at IS NULL OR c.overlap_expires_at>:now)"""
                        ),
                        {"cid": credential_id, "now": utcnow()},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            return await self._credential_record(conn, row["id"])

    async def exchange_credential(
        self,
        credential_id: str,
        raw_secret: str,
        *,
        correlation_id: str | None = None,
    ) -> tuple[CredentialRecord, ServicePrincipalRecord] | None:
        """Validate a service credential without exposing its stored digest."""
        now = utcnow()
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.id,c.principal_id FROM ima.mcp_credentials c
                               JOIN ima.mcp_service_principals p ON p.id=c.principal_id
                               JOIN ima.users owner ON owner.id=p.owner_user_id AND owner.is_active
                               WHERE c.credential_id=:cid AND c.digest=:digest
                                 AND c.revoked_at IS NULL AND c.expires_at>:now
                                 AND (c.replaced_by IS NULL OR c.overlap_expires_at>:now)
                                 AND p.state='active' AND p.expires_at>:now
                               FOR UPDATE OF c"""
                        ),
                        {
                            "cid": credential_id,
                            "digest": self._token_digest(raw_secret),
                            "now": now,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                await self._audit(
                    conn,
                    None,
                    "mcp.credential.exchanged",
                    "failure",
                    reason="invalid_credential",
                    correlation_id=correlation_id,
                )
                return None
            await conn.execute(
                text("UPDATE ima.mcp_credentials SET last_used_at=:now WHERE id=:id"),
                {"id": row["id"], "now": now},
            )
            await self._audit(
                conn,
                None,
                "mcp.credential.exchanged",
                "success",
                target_type="service_principal",
                target_id=str(row["principal_id"]),
                correlation_id=correlation_id,
            )
            credential = await self._credential_record(conn, row["id"])
            principal = await self._service_principal_record(conn, row["principal_id"])
            assert credential is not None and principal is not None
            return credential, principal

    async def resolve_credential_bearer(
        self, raw_secret: str, *, correlation_id: str | None = None
    ) -> tuple[CredentialRecord, ServicePrincipalRecord] | None:
        """Validate a service credential presented directly as an MCP bearer.

        Digest lookup with the same pepper and the same lifecycle checks as
        the /oauth/token exchange: revocation, expiry, rotation overlap,
        active principal and owner.  ``last_used_at`` and the safe
        ``mcp.credential.direct_auth`` audit row commit in the same
        transaction; the raw secret is never stored or audited.
        """
        now = utcnow()
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.id,c.principal_id FROM ima.mcp_credentials c
                               JOIN ima.mcp_service_principals p ON p.id=c.principal_id
                               JOIN ima.users owner ON owner.id=p.owner_user_id AND owner.is_active
                               WHERE c.digest=:digest
                                 AND c.revoked_at IS NULL AND c.expires_at>:now
                                 AND (c.replaced_by IS NULL OR c.overlap_expires_at>:now)
                                 AND p.state='active' AND p.expires_at>:now
                               FOR UPDATE OF c"""
                        ),
                        {
                            "digest": self._token_digest(raw_secret),
                            "now": now,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                await self._audit(
                    conn,
                    None,
                    "mcp.credential.direct_auth",
                    "failure",
                    reason="invalid_credential",
                    correlation_id=correlation_id,
                )
                return None
            await conn.execute(
                text("UPDATE ima.mcp_credentials SET last_used_at=:now WHERE id=:id"),
                {"id": row["id"], "now": now},
            )
            await self._audit(
                conn,
                None,
                "mcp.credential.direct_auth",
                "success",
                target_type="service_principal",
                target_id=str(row["principal_id"]),
                metadata={"credential_id": str(row["id"])},
                correlation_id=correlation_id,
            )
            credential = await self._credential_record(conn, row["id"])
            principal = await self._service_principal_record(conn, row["principal_id"])
            assert credential is not None and principal is not None
            return credential, principal

    async def list_service_principals(
        self, *, owner_user_id: str
    ) -> tuple[ServicePrincipalRecord, ...]:
        """Return safe service-principal projections owned by one user."""
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id FROM ima.mcp_service_principals WHERE owner_user_id=:id ORDER BY created_at DESC,id"
                ),
                {"id": owner_user_id},
            )
            records = [await self._service_principal_record(conn, row[0]) for row in rows]
        return tuple(record for record in records if record is not None)

    async def list_credentials_for_principal(
        self, principal_id: UUID
    ) -> tuple[CredentialRecord, ...]:
        """Load credential rows for conversion to safe application projections."""
        async with self.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT id FROM ima.mcp_credentials WHERE principal_id=:id ORDER BY created_at DESC,id"
                ),
                {"id": principal_id},
            )
            records = [await self._credential_record(conn, row[0]) for row in rows]
        return tuple(record for record in records if record is not None)

    async def revoke_credential(
        self,
        credential_id: str,
        *,
        actor_id: str | None,
        reason: str,
        correlation_id: str | None = None,
    ) -> None:
        """Revoke a credential immediately; the raw secret is invalid on next use."""
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.mcp_credentials SET revoked_at=:now,revoke_reason=:reason WHERE credential_id=:cid"
                ),
                {"cid": credential_id, "now": utcnow(), "reason": reason},
            )
            await self._audit(
                conn,
                actor_id,
                "mcp.credential.revoked",
                "success",
                target_type="credential",
                target_id=credential_id,
                reason=reason,
                correlation_id=correlation_id,
            )

    async def rotate_credential(
        self,
        old_credential_id: str,
        *,
        created_by: str | None,
        expires_at: datetime,
        overlap_expires_at: datetime | None = None,
        correlation_id: str | None = None,
    ) -> tuple[str, CredentialRecord, CredentialRecord]:
        """Rotate a credential atomically.

        Revokes the old credential by default and issues a replacement in the
        same transaction.  When an overlap expiry is provided, the old
        credential keeps an explicit overlap window and is then hard-revoked.
        Returns ``(raw_secret, new_record, old_record)``.
        """
        async with self.engine.begin() as conn:
            old_row = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.id,c.principal_id,p.expires_at AS principal_expires,p.state AS principal_state
                               FROM ima.mcp_credentials c
                               JOIN ima.mcp_service_principals p ON p.id=c.principal_id
                               WHERE c.credential_id=:cid AND c.revoked_at IS NULL AND c.expires_at>:now
                               FOR UPDATE OF c"""
                        ),
                        {"cid": old_credential_id, "now": utcnow()},
                    )
                )
                .mappings()
                .first()
            )
            if not old_row:
                raise McpRepositoryError("invalid_credential", "active credential not found")
            old_id = UUID(str(old_row["id"]))
            principal_id = UUID(str(old_row["principal_id"]))
            principal_expires = old_row["principal_expires"]
            now = utcnow()
            if old_row["principal_state"] != "active" or principal_expires <= now:
                raise McpRepositoryError("invalid_principal", "active principal not found")
            if expires_at <= now:
                raise McpRepositoryError(
                    "invalid_expiry", "replacement credential expiry must be in the future"
                )
            if expires_at - now > timedelta(seconds=self.settings.service_credential_max_seconds):
                raise McpRepositoryError(
                    "expiry_too_long", "replacement credential expiry exceeds the maximum"
                )
            if expires_at > principal_expires:
                raise McpRepositoryError(
                    "invalid_expiry", "replacement credential cannot outlive its principal"
                )
            raw_secret = new_oauth_value()
            new_id = uuid4()
            if overlap_expires_at is not None:
                if overlap_expires_at <= now:
                    raise McpRepositoryError(
                        "invalid_overlap", "credential overlap expiry must be in the future"
                    )
                if overlap_expires_at > expires_at:
                    raise McpRepositoryError(
                        "invalid_overlap", "credential overlap cannot extend beyond expiry"
                    )
                if overlap_expires_at - now > timedelta(
                    seconds=self.settings.credential_rotation_overlap_seconds
                ):
                    raise McpRepositoryError(
                        "invalid_overlap", "credential overlap exceeds the configured maximum"
                    )
            if overlap_expires_at is not None:
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_credentials SET overlap_expires_at=:overlap,replaced_by=:next WHERE id=:id"
                    ),
                    {"id": old_id, "overlap": overlap_expires_at, "next": new_id},
                )
            else:
                await conn.execute(
                    text(
                        "UPDATE ima.mcp_credentials SET revoked_at=:now,revoke_reason='rotated',replaced_by=:next WHERE id=:id"
                    ),
                    {"id": old_id, "now": now, "next": new_id},
                )
            await conn.execute(
                text(
                    """INSERT INTO ima.mcp_credentials(id,principal_id,credential_id,digest,secret_prefix,created_at,
                       created_by,expires_at,overlap_expires_at,replaced_by)
                       VALUES (:id,:principal,:cid,:digest,:prefix,:now,:created_by,:expires,:overlap,NULL)"""
                ),
                {
                    "id": new_id,
                    "principal": principal_id,
                    "cid": credential_id(),
                    "digest": self._token_digest(raw_secret),
                    "prefix": secret_prefix(),
                    "now": now,
                    "created_by": created_by,
                    "expires": expires_at,
                    "overlap": None,
                },
            )
            await self._audit(
                conn,
                created_by,
                "mcp.credential.rotated",
                "success",
                target_type="service_principal",
                target_id=str(principal_id),
                metadata={
                    "old_credential": old_credential_id,
                    "overlap": overlap_expires_at is not None,
                },
                correlation_id=correlation_id,
            )
            new_record = await self._credential_record(conn, new_id)
            old_record = await self._credential_record(conn, old_id)
            assert new_record is not None and old_record is not None
            return raw_secret, new_record, old_record

    async def fails_overlap_expired(self, credential_id: str, now: datetime) -> bool:
        """Whether an overlapped credential has passed its overlap boundary."""
        async with self.engine.connect() as conn:
            result = await conn.scalar(
                text(
                    "SELECT (overlap_expires_at IS NOT NULL AND overlap_expires_at <= :now) FROM ima.mcp_credentials WHERE credential_id=:cid"
                ),
                {"cid": credential_id, "now": now},
            )
        return bool(result)

    # ------------------------------------------------------------------
    # Rate buckets (per principal/credential/source, pepper-hashed)
    # ------------------------------------------------------------------

    async def rate_allowed(
        self,
        bucket_kind: str,
        action: str,
        bucket: str,
        *,
        limit: int,
        window_seconds: int = 300,
    ) -> bool:
        """Rate-limit a bucketed action using the safe pepper bucket pattern.

        Returns ``False`` when the bucket is currently blocked or the attempt
        would exceed ``limit`` within the window.  Mirrors the identity service
        ``auth_rate_limits`` shape but is scoped to OAuth/MCP buckets.
        """
        if limit < 1 or window_seconds < 1:
            raise ValueError("rate limit and window must be positive")
        now = utcnow()
        window_epoch = int(now.timestamp()) // window_seconds * window_seconds
        window = datetime.fromtimestamp(window_epoch, UTC)
        key = self._token_digest(f"{bucket_kind}:{action}:{bucket}")
        async with self.engine.begin() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            """INSERT INTO ima.mcp_rate_buckets(
                                 bucket_digest,bucket_kind,action,window_start,attempts,blocked_until
                               ) VALUES (:bucket,:kind,:action,:window,1,NULL)
                               ON CONFLICT(bucket_digest,bucket_kind,action,window_start)
                               DO UPDATE SET
                                 attempts=ima.mcp_rate_buckets.attempts+1,
                                 blocked_until=CASE
                                   WHEN ima.mcp_rate_buckets.blocked_until>:now
                                     THEN ima.mcp_rate_buckets.blocked_until
                                   WHEN ima.mcp_rate_buckets.attempts+1>:limit THEN :blocked
                                   ELSE NULL
                                 END
                               RETURNING attempts,blocked_until"""
                        ),
                        {
                            "bucket": key,
                            "kind": bucket_kind,
                            "action": action,
                            "window": window,
                            "now": now,
                            "limit": limit,
                            "blocked": now + timedelta(seconds=window_seconds),
                        },
                    )
                )
                .mappings()
                .one()
            )
            return int(row["attempts"]) <= limit and not (
                row["blocked_until"] and row["blocked_until"] > now
            )

    async def acquire_concurrency_lease(
        self,
        *,
        token_id: UUID,
        principal_id: UUID | None,
        source: str,
        request_id: str,
        limit: int,
        ttl_seconds: int = 60,
        correlation_id: str | None = None,
    ) -> UUID | None:
        """Atomically acquire a bounded cross-replica MCP concurrency lease."""
        if limit < 1 or ttl_seconds < 1 or ttl_seconds > 300:
            raise ValueError("invalid concurrency lease policy")
        lease_id = uuid4()
        async with self.engine.begin() as conn:
            database_now = await conn.scalar(text("SELECT clock_timestamp()"))
            if not isinstance(database_now, datetime):
                raise RuntimeError("database did not return a concurrency lease timestamp")
            now = database_now
            token = (
                (
                    await conn.execute(
                        text(
                            """SELECT principal_id FROM ima.mcp_access_tokens
                               WHERE id=:token AND revoked_at IS NULL AND expires_at>:now"""
                        ),
                        {"token": token_id, "now": now},
                    )
                )
                .mappings()
                .first()
            )
            if token is None:
                # Credential-direct bearers lease against one durable anchor
                # row (id equal to the credential id) because the lease table
                # keeps a NOT NULL foreign key into mcp_access_tokens.  The
                # row is written once per credential, never per request.  Its
                # canonical_resource is a sentinel no real resource equals, so
                # load_access_token can never resolve the synthetic digest as
                # a bearer, and a live credential repairs a revoked anchor.
                credential = (
                    (
                        await conn.execute(
                            text(
                                """SELECT c.id,c.principal_id,p.scopes,p.expires_at FROM ima.mcp_credentials c
                                   JOIN ima.mcp_service_principals p ON p.id=c.principal_id
                                   WHERE c.id=:token AND c.revoked_at IS NULL AND c.expires_at>:now
                                     AND p.state='active' AND p.expires_at>:now"""
                            ),
                            {"token": token_id, "now": now},
                        )
                    )
                    .mappings()
                    .first()
                )
                if credential is not None:
                    await conn.execute(
                        text(
                            """INSERT INTO ima.mcp_access_tokens(id,token_digest,grant_id,principal_id,client_id,
                               canonical_resource,scopes,security_stamp,expires_at,created_at)
                               VALUES (:id,:digest,NULL,:principal,NULL,:resource,:scopes,NULL,:expires,:now)
                               ON CONFLICT (id) DO UPDATE SET revoked_at=NULL,revoke_reason=NULL
                               WHERE ima.mcp_access_tokens.revoked_at IS NOT NULL"""
                        ),
                        {
                            "id": token_id,
                            "digest": self._token_digest(f"mcp-credential-lease:{token_id}"),
                            "principal": credential["principal_id"],
                            "resource": "mcp-credential-lease",
                            "scopes": list(credential["scopes"]),
                            "expires": credential["expires_at"],
                            "now": now,
                        },
                    )
                    token = cast("RowMapping", {"principal_id": credential["principal_id"]})
            if token is None:
                await self._audit(
                    conn,
                    None,
                    "mcp.concurrency.denied",
                    "failure",
                    target_type="access_token",
                    target_id=str(token_id),
                    reason="invalid_token_context",
                    correlation_id=correlation_id,
                )
                return None
            stored_principal = (
                UUID(str(token["principal_id"])) if token["principal_id"] is not None else None
            )
            if stored_principal != principal_id:
                await self._audit(
                    conn,
                    None,
                    "mcp.concurrency.denied",
                    "failure",
                    target_type="access_token",
                    target_id=str(token_id),
                    reason="invalid_token_context",
                    correlation_id=correlation_id,
                )
                return None
            if principal_id is not None:
                policy_limit = await conn.scalar(
                    text(
                        """SELECT concurrency_limit FROM ima.mcp_service_principals
                           WHERE id=:principal AND state='active' AND expires_at>:now"""
                    ),
                    {"principal": principal_id, "now": now},
                )
                if policy_limit is None:
                    await self._audit(
                        conn,
                        None,
                        "mcp.concurrency.denied",
                        "failure",
                        target_type="service_principal",
                        target_id=str(principal_id),
                        reason="policy_inactive",
                        correlation_id=correlation_id,
                    )
                    return None
                limit = min(limit, int(policy_limit))
                boundary = f"principal:{principal_id}"
            else:
                limit = min(limit, self.settings.mcp_default_concurrency)
                boundary = f"token:{token_id}"
            bucket = self._token_digest(f"concurrency:{boundary}")
            source_digest = self._token_digest(f"source:{boundary}:{source}")
            request_digest = self._token_digest(f"request:{boundary}:{source_digest}:{request_id}")
            for lock_key in sorted((bucket, source_digest)):
                await conn.execute(
                    text("SELECT pg_advisory_xact_lock(hashtextextended(:bucket, 0))"),
                    {"bucket": lock_key},
                )
            await conn.execute(
                text(
                    """DELETE FROM ima.mcp_concurrency_leases
                       WHERE expires_at<=:now
                         AND (bucket_digest=:bucket OR source_digest=:source)"""
                ),
                {"now": now, "bucket": bucket, "source": source_digest},
            )
            existing = await conn.scalar(
                text("SELECT id FROM ima.mcp_concurrency_leases WHERE request_digest=:request"),
                {"request": request_digest},
            )
            if existing:
                return UUID(str(existing))
            active = int(
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.mcp_concurrency_leases WHERE bucket_digest=:bucket AND expires_at>:now"
                    ),
                    {"bucket": bucket, "now": now},
                )
                or 0
            )
            source_active = int(
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.mcp_concurrency_leases WHERE source_digest=:source AND expires_at>:now"
                    ),
                    {"source": source_digest, "now": now},
                )
                or 0
            )
            if active >= limit or source_active >= limit:
                await self._audit(
                    conn,
                    None,
                    "mcp.concurrency.denied",
                    "failure",
                    target_type="service_principal" if principal_id else "access_token",
                    target_id=str(principal_id or token_id),
                    reason="concurrency_limited",
                    metadata={"limit": limit},
                    correlation_id=correlation_id,
                )
                return None
            await conn.execute(
                text("""INSERT INTO ima.mcp_concurrency_leases(id,bucket_digest,request_digest,token_id,principal_id,source_digest,created_at,expires_at)
                VALUES (:id,:bucket,:request,:token,:principal,:source,:now,:expires)"""),
                {
                    "id": lease_id,
                    "bucket": bucket,
                    "request": request_digest,
                    "token": token_id,
                    "principal": principal_id,
                    "source": source_digest,
                    "now": now,
                    "expires": now + timedelta(seconds=ttl_seconds),
                },
            )
        return lease_id

    async def release_concurrency_lease(self, lease_id: UUID) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM ima.mcp_concurrency_leases WHERE id=:id"), {"id": lease_id}
            )

    # ------------------------------------------------------------------
    # Service principals and credentials
    # ------------------------------------------------------------------

    async def create_service_principal(
        self,
        *,
        display_name: str,
        purpose: str,
        owner_user_id: str,
        scopes: tuple[str, ...],
        expires_at: datetime,
        rate_limit: int,
        concurrency_limit: int,
        cidr_allowlist: tuple[str, ...] = (),
        created_by: str | None = None,
        correlation_id: str | None = None,
    ) -> ServicePrincipalRecord:
        """Create a user-owned service principal (finite expiry)."""
        principal_id = uuid4()
        now = utcnow()
        if expires_at <= now:
            raise McpRepositoryError(
                "invalid_expiry", "service principal expiry must be in the future"
            )
        if expires_at - now > timedelta(seconds=self.settings.service_credential_max_seconds):
            raise McpRepositoryError(
                "expiry_too_long",
                "service principal expiry exceeds the configured maximum",
            )
        normalized_cidr = normalize_cidr_allowlist(cidr_allowlist)
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    """INSERT INTO ima.mcp_service_principals(id,display_name,purpose,
                       owner_user_id,scopes,state,created_by,expires_at,cidr_allowlist,rate_limit,concurrency_limit,
                       created_at,updated_at)
                       VALUES (:id,:name,:purpose,:owner,:scopes,'active',:created_by,:expires,
                               :cidr,:rate,:concurrency,:now,:now)"""
                ),
                {
                    "id": principal_id,
                    "name": display_name,
                    "purpose": purpose,
                    "owner": owner_user_id,
                    "scopes": list(scopes),
                    "created_by": created_by,
                    "expires": expires_at,
                    "cidr": list(normalized_cidr) if normalized_cidr else None,
                    "rate": rate_limit,
                    "concurrency": concurrency_limit,
                    "now": now,
                },
            )
            await self._audit(
                conn,
                created_by or owner_user_id,
                "mcp.service_principal.created",
                "success",
                target_type="service_principal",
                target_id=str(principal_id),
                metadata={"owner_user_id": owner_user_id, "scopes": list(scopes)},
                correlation_id=correlation_id,
            )
        async with self.engine.connect() as conn:
            record = await self._service_principal_record(conn, principal_id)
        assert record is not None
        return record
