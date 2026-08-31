"""Knowledge base authorization application services.

This module is the only mutable owner of knowledge base authorization state.
API routers map its stable errors to HTTP and never implement policy
decisions.  Membership role decides every action; there are no folder ACLs,
user groups, or mail invitations.  Sharing happens through revocable share
links whose tokens are stored only as salted, peppered digests.
"""

# ruff: noqa: E501

from __future__ import annotations

import hmac
import json
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.application.identity import new_legacy_id
from ima.config import Settings
from ima.domain.authorization import (
    KbAction,
    KbRole,
    KbShareRole,
    PolicyReason,
    role_allows,
)
from ima.infrastructure.auth.security import digest
from ima.infrastructure.db.authorization import (
    load_membership,
    membership_active,
)

MAINTENANCE_WRITE_FREEZE = "MAINTENANCE_WRITE_FREEZE"
SHARE_LINK_TOKEN_BYTES = 32
SHARE_LINK_SALT_BYTES = 16


def now() -> datetime:
    return datetime.now(UTC)


def share_token_digest(token: str, salt: str, pepper: str) -> str:
    """Salted, peppered digest; plaintext share tokens are never stored."""
    return digest(f"{salt}:{token}", pepper)


def share_link_url(public_origin: str, token: str) -> str:
    return f"{public_origin.rstrip('/')}/join/{token}"


def share_link_problem(
    *, revoked_at: datetime | None, expires_at: datetime | None, kb_active: bool, at: datetime
) -> str | None:
    """Return the rejection error code, or None when the link admits joiners."""
    if revoked_at is not None:
        return "SHARE_LINK_INVALID"
    if expires_at is not None and expires_at <= at:
        return "SHARE_LINK_EXPIRED"
    if not kb_active:
        return "KB_NOT_FOUND"
    return None


def accepted_member_role(existing_role: str | None, link_role: str) -> str:
    """Accepting a share link never demotes an existing member."""
    return existing_role if existing_role is not None else link_role


def role_change_problem(*, actor_role: str, target_role: str, new_role: str) -> str | None:
    """Only the owner manages members, and only editor<->viewer may change."""
    if actor_role != KbRole.OWNER.value:
        return "MEMBERSHIP_FORBIDDEN"
    if new_role not in {role.value for role in KbShareRole}:
        return "INVALID_ROLE"
    if target_role == KbRole.OWNER.value:
        return "OWNER_PROTECTED"
    return None


class KbError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class KbService:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings

    # ------------------------------------------------------------------ audit

    async def _audit(
        self,
        conn: AsyncConnection,
        actor: str | None,
        action: str,
        result: str,
        *,
        kb: str | None = None,
        target: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await conn.execute(
            text("""INSERT INTO ima.audit_events(actor_id,action,target_type,target_id,result,reason_code,metadata,created_at)
          VALUES (:actor,:action,:target_type,:target,:result,:reason,CAST(:metadata AS jsonb),:created)"""),
            {
                "actor": actor,
                "action": action,
                "target_type": "knowledge_base" if kb else None,
                "target": target or kb,
                "result": result,
                "reason": reason,
                "metadata": json.dumps({"kbId": kb, **(metadata or {})}),
                "created": now(),
            },
        )

    async def _assert_writes_allowed(self, conn: AsyncConnection) -> None:
        """Maintenance write-freeze gate (same setting read as the freeze service)."""
        frozen = await conn.scalar(
            text("SELECT maintenance_write_freeze FROM ima.system_settings WHERE id=true")
        )
        if frozen:
            raise KbError(
                503, MAINTENANCE_WRITE_FREEZE, "Write freeze active during migration maintenance"
            )

    # ------------------------------------------------------------- membership

    async def _require_member(
        self,
        conn: AsyncConnection,
        actor_id: str,
        kb_id: str,
        action: KbAction | None = None,
    ) -> dict[str, Any]:
        member = await load_membership(conn, actor_id, kb_id)
        if member is None:
            await self._audit(
                conn,
                actor_id,
                "kb.authorization.denied",
                "failure",
                kb=kb_id,
                reason=PolicyReason.MISSING_MEMBERSHIP.value,
            )
            raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
        # Membership rows are not sufficient authority by themselves.  Account
        # disablement and knowledge base archival must take effect on the very
        # next decision, including metadata and member reads.
        if not member.account_active:
            await self._audit(
                conn,
                actor_id,
                "kb.authorization.denied",
                "failure",
                kb=kb_id,
                reason=PolicyReason.INACTIVE_ACTOR.value,
            )
            raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
        if not member.kb_active:
            await self._audit(
                conn,
                actor_id,
                "kb.authorization.denied",
                "failure",
                kb=kb_id,
                reason=PolicyReason.INACTIVE_KNOWLEDGE_BASE.value,
            )
            raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
        if action is not None and not role_allows(member.role, action):
            await self._audit(
                conn,
                actor_id,
                "kb.authorization.denied",
                "failure",
                kb=kb_id,
                reason=PolicyReason.INSUFFICIENT_ROLE.value,
            )
            raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
        return {"member": member, "role": member.role.value}

    async def _require_owner(
        self, conn: AsyncConnection, actor_id: str, kb_id: str, *, code: str, detail: str
    ) -> dict[str, Any]:
        info = await self._require_member(conn, actor_id, kb_id)
        if info["role"] != KbRole.OWNER.value:
            raise KbError(403, code, detail)
        return info

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _summary(row: Mapping[Any, Any], user_id: str) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "isActive": row["is_active"],
            "archivedAt": row["archived_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "role": row["role"],
            "owned": row["created_by"] == user_id,
        }

    @staticmethod
    def _folder_row(row: Mapping[Any, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kbId": row["kb_id"],
            "parentId": row["parent_id"],
            "name": row["name"],
            "orderKey": int(row["order_key"]),
            "lifecycle": row["lifecycle"],
            "version": int(row["version"]),
            "isRoot": bool(row["is_root"]),
        }

    async def _kb_summary(self, conn: AsyncConnection, kb_id: str, user_id: str) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text("""SELECT kb.id,kb.name,kb.is_active,kb.archived_at,kb.created_at,kb.updated_at,kb.created_by,m.role
              FROM ima.knowledge_bases kb JOIN ima.kb_members m ON m.kb_id=kb.id AND m.user_id=:u AND m.state='active'
              WHERE kb.id=:kb"""),
                    {"u": user_id, "kb": kb_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
        return self._summary(row, user_id)

    async def require_membership(self, user_id: str, kb_id: str) -> str:
        """Return the caller's active role; reads require viewer or above."""
        async with self.engine.connect() as conn:
            member = await load_membership(conn, user_id, kb_id)
            if member is None or not membership_active(member):
                raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
            return member.role.value

    async def require_write_access(self, user_id: str, kb_id: str) -> str:
        """Return the caller's role when it allows writes (editor or above)."""
        role = await self.require_membership(user_id, kb_id)
        if not role_allows(KbRole(role), KbAction.EDIT):
            raise KbError(403, "KB_EDITOR_REQUIRED", "Editor access is required")
        return role

    # ------------------------------------------------------- knowledge bases

    async def list_knowledge_bases(self, user_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text("""SELECT kb.id,kb.name,kb.is_active,kb.archived_at,kb.created_at,kb.updated_at,kb.created_by,m.role
              FROM ima.knowledge_bases kb JOIN ima.kb_members m ON m.kb_id=kb.id AND m.user_id=:u AND m.state='active'
              JOIN ima.users u ON u.id=m.user_id AND u.is_active WHERE kb.is_active ORDER BY kb.created_at DESC,kb.id DESC"""),
                        {"u": user_id},
                    )
                )
                .mappings()
                .all()
            )
            return [self._summary(row, user_id) for row in rows]

    async def get_knowledge_base(self, actor_id: str, kb_id: str) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, kb_id)
            return await self._kb_summary(conn, kb_id, actor_id)

    async def create_knowledge_base(self, user_id: str, name: str) -> dict[str, Any]:
        if not name.strip():
            raise KbError(400, "INVALID_KB_NAME", "Knowledge base name cannot be blank")
        kb_id = new_legacy_id()
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            exists = await conn.scalar(
                text("SELECT is_active FROM ima.users WHERE id=:id"), {"id": user_id}
            )
            if not exists:
                raise KbError(404, "USER_NOT_FOUND", "User not found")
            ts = now()
            await conn.execute(
                text(
                    "INSERT INTO ima.knowledge_bases(id,name,created_by,created_at,updated_at) VALUES (:id,:name,:actor,:now,:now)"
                ),
                {"id": kb_id, "name": name.strip(), "actor": user_id, "now": ts},
            )
            # Root folder, closure self-row, and the creator's owner membership
            # commit together with the knowledge base row.
            await conn.execute(
                text(
                    "INSERT INTO ima.folders(id,kb_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,created_by,created_at,updated_at) VALUES (:id,:kb,NULL,:name,:normalized,0,'active',1,true,:actor,:now,:now)"
                ),
                {
                    "id": kb_id,
                    "kb": kb_id,
                    "name": name.strip(),
                    "normalized": name.casefold().strip(),
                    "actor": user_id,
                    "now": ts,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth) VALUES (:kb,:id,:id,0)"
                ),
                {"kb": kb_id, "id": kb_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.kb_members(kb_id,user_id,role,state,version,joined_at) VALUES (:kb,:u,'owner','active',1,:now)"
                ),
                {"kb": kb_id, "u": user_id, "now": ts},
            )
            await self._audit(conn, user_id, "kb.created", "success", kb=kb_id)
        return await self.get_knowledge_base(user_id, kb_id)

    async def rename_knowledge_base(self, actor_id: str, kb_id: str, name: str) -> dict[str, Any]:
        if not name.strip():
            raise KbError(400, "INVALID_KB_NAME", "Knowledge base name cannot be blank")
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_owner(
                conn,
                actor_id,
                kb_id,
                code="MEMBERSHIP_FORBIDDEN",
                detail="Knowledge base owner access is required",
            )
            ts = now()
            await conn.execute(
                text("UPDATE ima.knowledge_bases SET name=:name,updated_at=:now WHERE id=:kb"),
                {"name": name.strip(), "now": ts, "kb": kb_id},
            )
            # The root folder mirrors the knowledge base name.
            await conn.execute(
                text(
                    "UPDATE ima.folders SET name=:name,normalized_name=:normalized,version=version+1,updated_at=:now WHERE id=:kb AND is_root"
                ),
                {
                    "name": name.strip(),
                    "normalized": name.casefold().strip(),
                    "now": ts,
                    "kb": kb_id,
                },
            )
            await self._audit(conn, actor_id, "kb.renamed", "success", kb=kb_id)
        return await self.get_knowledge_base(actor_id, kb_id)

    async def archive_knowledge_base(self, actor_id: str, kb_id: str) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_owner(
                conn,
                actor_id,
                kb_id,
                code="MEMBERSHIP_FORBIDDEN",
                detail="Knowledge base owner access is required",
            )
            result = await conn.execute(
                text(
                    "UPDATE ima.knowledge_bases SET is_active=false,archived_at=COALESCE(archived_at,:now),updated_at=:now WHERE id=:kb AND is_active"
                ),
                {"kb": kb_id, "now": now()},
            )
            if not result.rowcount:
                exists = await conn.scalar(
                    text("SELECT 1 FROM ima.knowledge_bases WHERE id=:kb"), {"kb": kb_id}
                )
                if not exists:
                    raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
                raise KbError(409, "KB_ARCHIVED", "Knowledge base is already archived")
            await self._audit(conn, actor_id, "kb.archived", "success", kb=kb_id)

    async def restore_knowledge_base(self, actor_id: str, kb_id: str) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            # Archival hides the knowledge base from reads; the owner keeps the
            # authority to restore it, so membership is loaded without the
            # active-kb requirement.
            member = await load_membership(conn, actor_id, kb_id)
            if member is None or not member.account_active or member.role is not KbRole.OWNER:
                raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
            result = await conn.execute(
                text(
                    "UPDATE ima.knowledge_bases SET is_active=true,archived_at=NULL,updated_at=:now WHERE id=:kb AND NOT is_active"
                ),
                {"kb": kb_id, "now": now()},
            )
            if not result.rowcount:
                exists = await conn.scalar(
                    text("SELECT 1 FROM ima.knowledge_bases WHERE id=:kb"), {"kb": kb_id}
                )
                if not exists:
                    raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
                raise KbError(409, "KB_ACTIVE", "Knowledge base is already active")
            await self._audit(conn, actor_id, "kb.restored", "success", kb=kb_id)

    async def delete_archived_knowledge_base(self, actor_id: str, kb_id: str) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            member = await load_membership(conn, actor_id, kb_id)
            if member is None or not member.account_active or member.role is not KbRole.OWNER:
                raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
            row = (
                (
                    await conn.execute(
                        text("SELECT archived_at FROM ima.knowledge_bases WHERE id=:kb FOR UPDATE"),
                        {"kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
            if row["archived_at"] is None:
                raise KbError(
                    409, "KB_NOT_ARCHIVED", "Knowledge base must be archived before deletion"
                )
            if await conn.scalar(
                text("SELECT count(*) FROM ima.folders WHERE kb_id=:kb AND id<>:kb"),
                {"kb": kb_id},
            ):
                raise KbError(
                    409,
                    "KB_CONTENT_DEPENDENCY",
                    "Knowledge base still has folder content dependencies",
                )
            if await conn.scalar(
                text("SELECT count(*) FROM ima.documents WHERE kb_id=:kb"), {"kb": kb_id}
            ):
                raise KbError(
                    409,
                    "KB_CONTENT_DEPENDENCY",
                    "Knowledge base still has document content dependencies",
                )
            await self._audit(
                conn,
                actor_id,
                "kb.deleted",
                "success",
                kb=kb_id,
                target=kb_id,
                metadata={"targetAuthorizationDeleted": True},
            )
            await conn.execute(
                text("DELETE FROM ima.kb_share_links WHERE kb_id=:kb"), {"kb": kb_id}
            )
            await conn.execute(text("DELETE FROM ima.kb_members WHERE kb_id=:kb"), {"kb": kb_id})
            await conn.execute(
                text("DELETE FROM ima.folder_closure WHERE kb_id=:kb"), {"kb": kb_id}
            )
            await conn.execute(text("DELETE FROM ima.folders WHERE kb_id=:kb"), {"kb": kb_id})
            # The registry keeps a nullable creator reference for auditability;
            # clear it before deletion so later account removal is not blocked
            # by a stale foreign-key reference.
            await conn.execute(
                text("UPDATE ima.knowledge_bases SET created_by=NULL WHERE id=:kb"), {"kb": kb_id}
            )
            await conn.execute(text("DELETE FROM ima.knowledge_bases WHERE id=:kb"), {"kb": kb_id})

    # ---------------------------------------------------------------- members

    async def list_members(
        self, actor_id: str, kb_id: str, query: str = ""
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, kb_id)
            rows = (
                (
                    await conn.execute(
                        text("""SELECT m.kb_id,m.user_id,m.role,m.state,m.version,m.joined_at,u.email,u.display_name,u.is_active
              FROM ima.kb_members m JOIN ima.users u ON u.id=m.user_id WHERE m.kb_id=:kb AND m.state='active' AND (:q='' OR u.normalized_email LIKE '%'||:q||'%' OR lower(u.display_name) LIKE '%'||:q||'%') ORDER BY u.display_name,u.id"""),
                        {"kb": kb_id, "q": query.casefold().strip()},
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    "kbId": row["kb_id"],
                    "userId": row["user_id"],
                    "role": row["role"],
                    "state": row["state"],
                    "version": int(row["version"]),
                    "joinedAt": row["joined_at"],
                    "email": row["email"],
                    "displayName": row["display_name"],
                    "accountActive": bool(row["is_active"]),
                }
                for row in rows
            ]

    async def update_member_role(
        self,
        actor_id: str,
        kb_id: str,
        user_id: str,
        role: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, kb_id)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT role,state,version FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u FOR UPDATE"
                        ),
                        {"kb": kb_id, "u": user_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise KbError(404, "MEMBER_NOT_FOUND", "Member not found")
            problem = role_change_problem(
                actor_role=info["role"], target_role=str(row["role"]), new_role=role
            )
            if problem == "MEMBERSHIP_FORBIDDEN":
                raise KbError(
                    403, "MEMBERSHIP_FORBIDDEN", "Knowledge base owner access is required"
                )
            if problem == "INVALID_ROLE":
                raise KbError(400, "INVALID_ROLE", "Role must be editor or viewer")
            if problem == "OWNER_PROTECTED":
                raise KbError(
                    403, "OWNER_PROTECTED", "The knowledge base owner role cannot be changed"
                )
            if expected_version is not None and int(row["version"]) != expected_version:
                raise KbError(409, "VERSION_CONFLICT", "The membership changed; reload and retry")
            version = int(row["version"]) + 1
            await conn.execute(
                text(
                    "UPDATE ima.kb_members SET role=:role,version=:version WHERE kb_id=:kb AND user_id=:u"
                ),
                {"role": role, "version": version, "kb": kb_id, "u": user_id},
            )
            await self._audit(
                conn,
                actor_id,
                "kb.member.updated",
                "success",
                kb=kb_id,
                target=user_id,
                metadata={"version": version},
            )
            return {
                "kbId": kb_id,
                "userId": user_id,
                "role": role,
                "state": "active",
                "version": version,
            }

    async def remove_member(
        self, actor_id: str, kb_id: str, user_id: str, expected_version: int | None = None
    ) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_owner(
                conn,
                actor_id,
                kb_id,
                code="MEMBERSHIP_FORBIDDEN",
                detail="Knowledge base owner access is required",
            )
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT role,version FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u FOR UPDATE"
                        ),
                        {"kb": kb_id, "u": user_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise KbError(404, "MEMBER_NOT_FOUND", "Member not found")
            if str(row["role"]) == KbRole.OWNER.value:
                raise KbError(409, "LAST_KB_OWNER", "The knowledge base owner cannot be removed")
            if expected_version is not None and int(row["version"]) != expected_version:
                raise KbError(409, "VERSION_CONFLICT", "The membership changed; reload and retry")
            await conn.execute(
                text("DELETE FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u"),
                {"kb": kb_id, "u": user_id},
            )
            await self._audit(
                conn,
                actor_id,
                "kb.member.removed",
                "success",
                kb=kb_id,
                target=user_id,
            )

    async def leave_knowledge_base(self, actor_id: str, kb_id: str) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            member = await load_membership(conn, actor_id, kb_id)
            if member is None or not membership_active(member):
                raise KbError(404, "KB_NOT_FOUND", "Knowledge base not found")
            if member.role is KbRole.OWNER:
                raise KbError(409, "LAST_KB_OWNER", "The knowledge base owner cannot leave")
            await conn.execute(
                text("DELETE FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u"),
                {"kb": kb_id, "u": actor_id},
            )
            await self._audit(
                conn, actor_id, "kb.member.left", "success", kb=kb_id, target=actor_id
            )

    # ----------------------------------------------------------------- folders

    async def folders(
        self, actor_id: str, kb_id: str, parent_id: str | None = None
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, kb_id, KbAction.VIEW_METADATA)
            if parent_id is not None:
                parent = await conn.scalar(
                    text(
                        "SELECT 1 FROM ima.folders WHERE kb_id=:kb AND id=:parent AND lifecycle='active'"
                    ),
                    {"kb": kb_id, "parent": parent_id},
                )
                if not parent:
                    raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,kb_id,parent_id,name,order_key,lifecycle,version,is_root FROM ima.folders WHERE kb_id=:kb AND (CAST(:p AS varchar(32)) IS NULL AND parent_id IS NULL OR parent_id=CAST(:p AS varchar(32))) AND lifecycle='active' ORDER BY order_key,name,id"
                        ),
                        {"kb": kb_id, "p": parent_id},
                    )
                )
                .mappings()
                .all()
            )
            return [self._folder_row(row) for row in rows]

    async def breadcrumbs(self, actor_id: str, kb_id: str, folder_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, kb_id, KbAction.VIEW_METADATA)
            exists = await conn.scalar(
                text(
                    "SELECT 1 FROM ima.folders WHERE kb_id=:kb AND id=:folder AND lifecycle='active'"
                ),
                {"kb": kb_id, "folder": folder_id},
            )
            if not exists:
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            rows = (
                (
                    await conn.execute(
                        text("""SELECT f.id,f.kb_id,f.parent_id,f.name,f.order_key,f.lifecycle,f.version,f.is_root,c.depth
              FROM ima.folder_closure c JOIN ima.folders f ON f.id=c.ancestor_id
              WHERE c.kb_id=:kb AND c.descendant_id=:folder AND f.lifecycle='active' ORDER BY c.depth DESC"""),
                        {"kb": kb_id, "folder": folder_id},
                    )
                )
                .mappings()
                .all()
            )
            return [self._folder_row(row) for row in rows]

    async def create_folder(
        self, actor_id: str, kb_id: str, parent_id: str, name: str
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            if not name.strip():
                raise KbError(400, "INVALID_FOLDER_NAME", "Folder name cannot be blank")
            await self._require_member(conn, actor_id, kb_id, KbAction.CREATE_CHILD)
            parent = (
                (
                    await conn.execute(
                        text(
                            "SELECT id FROM ima.folders WHERE id=:id AND kb_id=:kb AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": parent_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not parent:
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            normalized_name = name.casefold().strip()
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE kb_id=:kb AND parent_id=:p AND lifecycle='active' AND normalized_name=:name)"
                ),
                {"kb": kb_id, "p": parent_id, "name": normalized_name},
            ):
                raise KbError(409, "FOLDER_NAME_EXISTS", "A folder with this name already exists")
            fid = new_legacy_id()
            ts = now()
            await conn.execute(
                text(
                    "INSERT INTO ima.folders(id,kb_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,created_by,created_at,updated_at) VALUES (:id,CAST(:kb AS varchar(32)),CAST(:p AS varchar(32)),:name,:normalized,COALESCE((SELECT max(order_key)+1 FROM ima.folders WHERE kb_id=CAST(:kb AS varchar(32)) AND parent_id=CAST(:p AS varchar(32)) AND lifecycle='active'),0),'active',1,false,:actor,:now,:now)"
                ),
                {
                    "id": fid,
                    "kb": kb_id,
                    "p": parent_id,
                    "name": name.strip(),
                    "normalized": normalized_name,
                    "actor": actor_id,
                    "now": ts,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth) SELECT CAST(:kb AS varchar(32)),ancestor_id,CAST(:id AS varchar(32)),depth+1 FROM ima.folder_closure WHERE kb_id=CAST(:kb AS varchar(32)) AND descendant_id=CAST(:p AS varchar(32)) UNION ALL SELECT CAST(:kb AS varchar(32)),CAST(:id AS varchar(32)),CAST(:id AS varchar(32)),0"
                ),
                {"kb": kb_id, "p": parent_id, "id": fid},
            )
            order_key = await conn.scalar(
                text("SELECT order_key FROM ima.folders WHERE id=:id"), {"id": fid}
            )
            await self._audit(
                conn,
                actor_id,
                "kb.folder.created",
                "success",
                kb=kb_id,
                target=fid,
            )
            return {
                "id": fid,
                "kbId": kb_id,
                "parentId": parent_id,
                "name": name.strip(),
                "orderKey": int(order_key or 0),
                "version": 1,
                "lifecycle": "active",
                "isRoot": False,
            }

    async def folder(self, actor_id: str, kb_id: str, folder_id: str) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, kb_id, KbAction.VIEW_METADATA)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,kb_id,parent_id,name,order_key,lifecycle,version,is_root FROM ima.folders WHERE id=:id AND kb_id=:kb AND lifecycle='active'"
                        ),
                        {"id": folder_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            return self._folder_row(row)

    async def rename_folder(
        self, actor_id: str, kb_id: str, folder_id: str, name: str, expected_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            if not name.strip():
                raise KbError(400, "INVALID_FOLDER_NAME", "Folder name cannot be blank")
            await self._require_member(conn, actor_id, kb_id, KbAction.EDIT)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT version,is_root FROM ima.folders WHERE id=:id AND kb_id=:kb AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": folder_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if row["is_root"]:
                raise KbError(400, "ROOT_PROTECTED", "The root folder cannot be renamed")
            if int(row["version"]) != expected_version:
                raise KbError(409, "VERSION_CONFLICT", "The folder changed; reload and retry")
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders f JOIN ima.folders current ON current.id=:id WHERE f.kb_id=:kb AND f.parent_id=current.parent_id AND f.lifecycle='active' AND f.id<>:id AND f.normalized_name=:name)"
                ),
                {"kb": kb_id, "id": folder_id, "name": name.casefold().strip()},
            ):
                raise KbError(409, "FOLDER_NAME_EXISTS", "A folder with this name already exists")
            await conn.execute(
                text(
                    "UPDATE ima.folders SET name=:name,normalized_name=:normalized,version=version+1,updated_at=:now WHERE id=:id"
                ),
                {
                    "id": folder_id,
                    "name": name.strip(),
                    "normalized": name.casefold().strip(),
                    "now": now(),
                },
            )
            await self._audit(
                conn,
                actor_id,
                "kb.folder.renamed",
                "success",
                kb=kb_id,
                target=folder_id,
            )
            updated = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,kb_id,parent_id,name,order_key,lifecycle,version,is_root FROM ima.folders WHERE id=:id"
                        ),
                        {"id": folder_id},
                    )
                )
                .mappings()
                .one()
            )
            return self._folder_row(updated)

    async def move_folder(
        self,
        actor_id: str,
        kb_id: str,
        folder_id: str,
        destination_id: str,
        expected_version: int,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_member(conn, actor_id, kb_id, KbAction.MOVE)
            source = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,is_root,version,normalized_name FROM ima.folders WHERE id=:id AND kb_id=:kb AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": folder_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            dest = (
                (
                    await conn.execute(
                        text(
                            "SELECT id FROM ima.folders WHERE id=:id AND kb_id=:kb AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": destination_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not source or not dest:
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if source["is_root"]:
                raise KbError(400, "ROOT_PROTECTED", "The root folder cannot move")
            if int(source["version"]) != expected_version:
                raise KbError(409, "VERSION_CONFLICT", "The folder changed; reload and retry")
            if bool(
                await conn.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ima.folder_closure WHERE kb_id=CAST(:kb AS varchar(32)) AND ancestor_id=CAST(:source AS varchar(32)) AND descendant_id=CAST(:dest AS varchar(32)))"
                    ),
                    {"kb": kb_id, "source": folder_id, "dest": destination_id},
                )
            ):
                raise KbError(400, "FOLDER_CYCLE", "A folder cannot move into its own subtree")
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE kb_id=:kb AND parent_id=:dest AND lifecycle='active' AND normalized_name=:name AND id<>:source)"
                ),
                {
                    "kb": kb_id,
                    "dest": destination_id,
                    "name": source["normalized_name"],
                    "source": folder_id,
                },
            ):
                raise KbError(409, "FOLDER_NAME_EXISTS", "A folder with this name already exists")
            await conn.execute(
                text(
                    "DELETE FROM ima.folder_closure WHERE kb_id=CAST(:kb AS varchar(32)) AND descendant_id IN (SELECT descendant_id FROM ima.folder_closure WHERE kb_id=CAST(:kb AS varchar(32)) AND ancestor_id=CAST(:source AS varchar(32))) AND ancestor_id IN (SELECT ancestor_id FROM ima.folder_closure WHERE kb_id=CAST(:kb AS varchar(32)) AND descendant_id=CAST(:source AS varchar(32)) AND ancestor_id<>CAST(:source AS varchar(32)))"
                ),
                {"kb": kb_id, "source": folder_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth) SELECT CAST(:kb AS varchar(32)),up.ancestor_id,down.descendant_id,up.depth+down.depth+1 FROM ima.folder_closure up CROSS JOIN ima.folder_closure down WHERE up.kb_id=CAST(:kb AS varchar(32)) AND up.descendant_id=CAST(:dest AS varchar(32)) AND down.kb_id=CAST(:kb AS varchar(32)) AND down.ancestor_id=CAST(:source AS varchar(32)) ON CONFLICT DO NOTHING"
                ),
                {"kb": kb_id, "source": folder_id, "dest": destination_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.folders SET parent_id=:dest,version=version+1,updated_at=:now WHERE id=:source"
                ),
                {"source": folder_id, "dest": destination_id, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "kb.folder.moved",
                "success",
                kb=kb_id,
                target=folder_id,
            )
            moved = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,kb_id,parent_id,name,order_key,lifecycle,version,is_root FROM ima.folders WHERE id=:id"
                        ),
                        {"id": folder_id},
                    )
                )
                .mappings()
                .one()
            )
            return self._folder_row(moved)

    async def reorder_folder(
        self,
        actor_id: str,
        kb_id: str,
        folder_id: str,
        order_key: int,
        expected_version: int,
    ) -> dict[str, Any]:
        """Move a folder among active siblings while preserving dense order."""
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_member(conn, actor_id, kb_id, KbAction.EDIT)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT parent_id,order_key,version,is_root,lifecycle FROM ima.folders WHERE id=:id AND kb_id=:kb FOR UPDATE"
                        ),
                        {"id": folder_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row or row["lifecycle"] != "active":
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if row["is_root"]:
                raise KbError(400, "ROOT_PROTECTED", "The root folder cannot be reordered")
            if int(row["version"]) != expected_version:
                raise KbError(409, "VERSION_CONFLICT", "The folder changed; reload and retry")
            siblings = int(
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.folders WHERE kb_id=:kb AND parent_id=:p AND lifecycle='active'"
                    ),
                    {"kb": kb_id, "p": row["parent_id"]},
                )
                or 1
            )
            old = int(row["order_key"])
            desired = max(0, min(int(order_key), siblings - 1))
            if desired > old:
                await conn.execute(
                    text(
                        "UPDATE ima.folders SET order_key=order_key-1 WHERE kb_id=:kb AND parent_id=:p AND lifecycle='active' AND id<>:id AND order_key>:old AND order_key<=:desired"
                    ),
                    {
                        "kb": kb_id,
                        "p": row["parent_id"],
                        "id": folder_id,
                        "old": old,
                        "desired": desired,
                    },
                )
            elif desired < old:
                await conn.execute(
                    text(
                        "UPDATE ima.folders SET order_key=order_key+1 WHERE kb_id=:kb AND parent_id=:p AND lifecycle='active' AND id<>:id AND order_key>=:desired AND order_key<:old"
                    ),
                    {
                        "kb": kb_id,
                        "p": row["parent_id"],
                        "id": folder_id,
                        "desired": desired,
                        "old": old,
                    },
                )
            await conn.execute(
                text(
                    "UPDATE ima.folders SET order_key=:desired,version=version+1,updated_at=:now WHERE id=:id"
                ),
                {"id": folder_id, "desired": desired, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "kb.folder.reordered",
                "success",
                kb=kb_id,
                target=folder_id,
                metadata={"orderKey": desired},
            )
            updated = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,kb_id,parent_id,name,order_key,lifecycle,version,is_root FROM ima.folders WHERE id=:id"
                        ),
                        {"id": folder_id},
                    )
                )
                .mappings()
                .one()
            )
            return self._folder_row(updated)

    async def delete_folder(
        self, actor_id: str, kb_id: str, folder_id: str, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_member(conn, actor_id, kb_id, KbAction.DELETE)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT is_root,lifecycle,version FROM ima.folders WHERE id=:id AND kb_id=:kb FOR UPDATE"
                        ),
                        {"id": folder_id, "kb": kb_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise KbError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if row["is_root"]:
                raise KbError(400, "ROOT_PROTECTED", "The root folder cannot be deleted")
            if row["lifecycle"] != "active" or int(row["version"]) != expected_version:
                raise KbError(409, "VERSION_CONFLICT", "The folder changed; reload and retry")
            descendants = int(
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.folder_closure WHERE kb_id=:kb AND ancestor_id=:id AND depth>0"
                    ),
                    {"kb": kb_id, "id": folder_id},
                )
                or 0
            )
            if descendants:
                raise KbError(409, "FOLDER_DEPENDENCIES", "Folder still contains child folders")
            if await conn.scalar(
                text("SELECT count(*) FROM ima.documents WHERE folder_id=:id"),
                {"id": folder_id},
            ):
                raise KbError(409, "FOLDER_DEPENDENCIES", "Folder still contains documents")
            await conn.execute(text("DELETE FROM ima.folders WHERE id=:id"), {"id": folder_id})
            await self._audit(
                conn,
                actor_id,
                "kb.folder.deleted",
                "success",
                kb=kb_id,
                target=folder_id,
            )

    # ------------------------------------------------------------ share links

    def _share_pepper(self) -> str:
        return self.settings.token_pepper.get_secret_value()

    async def create_share_link(
        self,
        actor_user_id: str,
        kb_id: str,
        role: str,
        expires_in_days: int | None = None,
    ) -> dict[str, Any]:
        try:
            share_role = KbShareRole(role)
        except ValueError:
            raise KbError(
                400, "INVALID_SHARE_ROLE", "Share role must be editor or viewer"
            ) from None
        if expires_in_days is not None and expires_in_days < 1:
            raise KbError(400, "INVALID_SHARE_EXPIRY", "Share expiry must be at least one day")
        token = secrets.token_urlsafe(SHARE_LINK_TOKEN_BYTES)
        salt = secrets.token_urlsafe(SHARE_LINK_SALT_BYTES)
        link_id = new_legacy_id()
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_owner(
                conn,
                actor_user_id,
                kb_id,
                code="SHARE_LINK_FORBIDDEN",
                detail="Knowledge base owner access is required",
            )
            ts = now()
            expires = ts + timedelta(days=expires_in_days) if expires_in_days else None
            await conn.execute(
                text(
                    "INSERT INTO ima.kb_share_links(id,kb_id,token_digest,token_salt,role,created_by,expires_at,revoked_at,created_at) VALUES (:id,:kb,:digest,:salt,:role,:actor,:expires,NULL,:now)"
                ),
                {
                    "id": link_id,
                    "kb": kb_id,
                    "digest": share_token_digest(token, salt, self._share_pepper()),
                    "salt": salt,
                    "role": share_role.value,
                    "actor": actor_user_id,
                    "expires": expires,
                    "now": ts,
                },
            )
            await self._audit(
                conn,
                actor_user_id,
                "kb.share_link.created",
                "success",
                kb=kb_id,
                target=link_id,
                metadata={"role": share_role.value},
            )
        return {
            "id": link_id,
            "kbId": kb_id,
            "role": share_role.value,
            "url": share_link_url(self.settings.public_origin, token),
            "expiresAt": expires,
            "createdAt": ts,
        }

    async def list_share_links(self, actor_user_id: str, kb_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_owner(
                conn,
                actor_user_id,
                kb_id,
                code="SHARE_LINK_FORBIDDEN",
                detail="Knowledge base owner access is required",
            )
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,kb_id,role,created_by,expires_at,revoked_at,created_at FROM ima.kb_share_links WHERE kb_id=:kb ORDER BY created_at DESC,id DESC"
                        ),
                        {"kb": kb_id},
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    "id": row["id"],
                    "kbId": row["kb_id"],
                    "role": row["role"],
                    "createdBy": row["created_by"],
                    "expiresAt": row["expires_at"],
                    "revokedAt": row["revoked_at"],
                    "createdAt": row["created_at"],
                }
                for row in rows
            ]

    async def revoke_share_link(self, actor_user_id: str, kb_id: str, link_id: str) -> None:
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            await self._require_owner(
                conn,
                actor_user_id,
                kb_id,
                code="SHARE_LINK_FORBIDDEN",
                detail="Knowledge base owner access is required",
            )
            result = await conn.execute(
                text(
                    "UPDATE ima.kb_share_links SET revoked_at=:now WHERE id=:id AND kb_id=:kb AND revoked_at IS NULL"
                ),
                {"id": link_id, "kb": kb_id, "now": now()},
            )
            if not result.rowcount:
                raise KbError(404, "SHARE_LINK_NOT_FOUND", "Share link not found")
            await self._audit(
                conn,
                actor_user_id,
                "kb.share_link.revoked",
                "success",
                kb=kb_id,
                target=link_id,
            )

    async def accept_share_link(self, user_id: str, token: str) -> dict[str, Any]:
        pepper = self._share_pepper()
        async with self.engine.begin() as conn:
            await self._assert_writes_allowed(conn)
            active = await conn.scalar(
                text("SELECT is_active FROM ima.users WHERE id=:id"), {"id": user_id}
            )
            if not active:
                raise KbError(400, "SHARE_LINK_INVALID", "Share link is invalid")
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT l.id,l.kb_id,l.role,l.token_salt,l.token_digest,l.expires_at,l.revoked_at,kb.is_active AS kb_active
                               FROM ima.kb_share_links l JOIN ima.knowledge_bases kb ON kb.id=l.kb_id
                              WHERE l.revoked_at IS NULL FOR UPDATE"""
                        )
                    )
                )
                .mappings()
                .all()
            )
            # The digest binds the per-link salt, so candidates are matched in
            # constant time instead of reconstructing a lookup key.
            match = None
            for row in rows:
                candidate = share_token_digest(token, str(row["token_salt"]), pepper)
                if hmac.compare_digest(candidate, str(row["token_digest"])):
                    match = row
                    break
            if match is None:
                await self._audit(
                    conn,
                    user_id,
                    "kb.share_link.accepted",
                    "failure",
                    reason="invalid_token",
                )
                raise KbError(
                    400, "SHARE_LINK_INVALID", "Share link is invalid or has been revoked"
                )
            problem = share_link_problem(
                revoked_at=match["revoked_at"],
                expires_at=match["expires_at"],
                kb_active=bool(match["kb_active"]),
                at=now(),
            )
            if problem == "SHARE_LINK_EXPIRED":
                await self._audit(
                    conn,
                    user_id,
                    "kb.share_link.accepted",
                    "failure",
                    kb=str(match["kb_id"]),
                    target=str(match["id"]),
                    reason="expired",
                )
                raise KbError(400, "SHARE_LINK_EXPIRED", "Share link has expired")
            if problem is not None:
                raise KbError(404, problem, "Knowledge base not found")
            kb_id = str(match["kb_id"])
            link_role = str(match["role"])
            existing = await conn.scalar(
                text(
                    "SELECT role FROM ima.kb_members WHERE kb_id=:kb AND user_id=:u AND state='active'"
                ),
                {"kb": kb_id, "u": user_id},
            )
            ts = now()
            if existing is None:
                await conn.execute(
                    text(
                        "INSERT INTO ima.kb_members(kb_id,user_id,role,state,version,joined_at) VALUES (:kb,:u,:role,'active',1,:now) ON CONFLICT(kb_id,user_id) DO NOTHING"
                    ),
                    {"kb": kb_id, "u": user_id, "role": link_role, "now": ts},
                )
            await self._audit(
                conn,
                user_id,
                "kb.share_link.accepted",
                "success",
                kb=kb_id,
                target=str(match["id"]),
                metadata={"existingMember": existing is not None},
            )
            # Idempotent join: existing members keep their current role and are
            # never demoted, because only missing memberships are inserted.
            return await self._kb_summary(conn, kb_id, user_id)
