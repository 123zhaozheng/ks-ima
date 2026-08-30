"""Workspace authorization application services.

This module is the only mutable owner of workspace authorization state.  API
routers map its stable errors to HTTP and never implement policy decisions.
"""

# ruff: noqa: E501

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.application.identity import new_legacy_id
from ima.application.maintenance import assert_writes_allowed
from ima.application.mcp_contracts import McpActor
from ima.config import Settings
from ima.domain.authorization import (
    DEFAULT_ROLE_GRANTS,
    AclAction,
    MembershipState,
    SubjectType,
    WorkspaceRole,
    validate_grants,
)
from ima.infrastructure.auth.security import digest
from ima.infrastructure.db.authorization import accessible_folder_ids, folder_decision, load_subject
from ima.infrastructure.mail import MailService


def now() -> datetime:
    return datetime.now(UTC)


class WorkspaceError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class WorkspaceService:
    def __init__(self, engine: AsyncEngine, settings: Settings) -> None:
        self.engine = engine
        self.settings = settings
        self.mail = MailService(settings)

    async def _audit(
        self,
        conn: AsyncConnection,
        actor: str | None,
        action: str,
        result: str,
        *,
        workspace: str | None = None,
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
                "target_type": "workspace" if workspace else None,
                "target": target or workspace,
                "result": result,
                "reason": reason,
                "metadata": json.dumps({"workspaceId": workspace, **(metadata or {})}),
                "created": now(),
            },
        )

    async def _platform(self, conn: AsyncConnection, user_id: str, capability: str) -> bool:
        roles: tuple[str, ...]
        if capability == "super_admin":
            roles = ("super_admin",)
        else:
            roles = ("super_admin", "platform_admin")
        return bool(
            await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.platform_role_assignments r WHERE r.user_id=:id AND r.role IN :roles)"
                ).bindparams(bindparam("roles", expanding=True)),
                {"id": user_id, "roles": roles},
            )
        )

    async def _require_member(
        self,
        conn: AsyncConnection,
        actor_id: str,
        workspace_id: str,
        action: AclAction | None = None,
    ) -> dict[str, Any]:
        subject = await load_subject(conn, actor_id, workspace_id)
        if not subject:
            await self._audit(
                conn,
                actor_id,
                "workspace.authorization.denied",
                "failure",
                workspace=workspace_id,
                reason="missing_membership",
            )
            raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
        # Membership rows are not sufficient authority by themselves.  Account
        # disablement and workspace archival must take effect on the very next
        # decision, including metadata/group/member reads that do not carry a
        # folder action.
        if not subject.account_active:
            await self._audit(
                conn,
                actor_id,
                "workspace.authorization.denied",
                "failure",
                workspace=workspace_id,
                reason="inactive_actor",
            )
            raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
        if not subject.workspace_active:
            await self._audit(
                conn,
                actor_id,
                "workspace.authorization.denied",
                "failure",
                workspace=workspace_id,
                reason="inactive_workspace",
            )
            raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
        if action:
            root = await conn.scalar(
                text("SELECT id FROM ima.folders WHERE workspace_id=:w AND is_root"),
                {"w": workspace_id},
            )
            if root:
                decision = await folder_decision(conn, subject, str(root), action)
                if not decision.allowed:
                    await self._audit(
                        conn,
                        actor_id,
                        "workspace.authorization.denied",
                        "failure",
                        workspace=workspace_id,
                        target=str(root),
                        reason=decision.reason.value,
                    )
                    raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
        return {"subject": subject, "role": subject.role.value}

    async def _require_folder_action(
        self,
        conn: AsyncConnection,
        subject: Any,
        workspace_id: str,
        folder_id: str,
        action: AclAction,
        *,
        include_trashed: bool = False,
    ) -> None:
        """Authorize the actual target, never only the workspace root."""
        decision = await folder_decision(
            conn, subject, folder_id, action, include_trashed=include_trashed
        )
        if not decision.allowed:
            await self._audit(
                conn,
                subject.user_id,
                "workspace.authorization.denied",
                "failure",
                workspace=workspace_id,
                target=folder_id,
                reason=decision.reason.value,
            )
            raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")

    async def _last_admin_guard(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        *,
        removing: str | None = None,
        new_role: str | None = None,
        actor_id: str | None = None,
    ) -> None:
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('ima:workspace-admin:'||:id))"),
            {"id": workspace_id},
        )
        count = int(
            await conn.scalar(
                text(
                    """SELECT count(*) FROM ima.workspace_members WHERE workspace_id=:w AND state='active' AND role='workspace_admin' AND (CAST(:remove AS varchar(32)) IS NULL OR user_id<>CAST(:remove AS varchar(32)))"""
                ),
                {"w": workspace_id, "remove": removing},
            )
            or 0
        )
        if new_role and removing and new_role == "workspace_admin":
            return
        if count < 1:
            await self._audit(
                conn,
                actor_id,
                "workspace.admin_invariant.denied",
                "failure",
                workspace=workspace_id,
                target=removing,
                reason="last_workspace_admin",
            )
            raise WorkspaceError(
                409,
                "LAST_WORKSPACE_ADMIN",
                "At least one active workspace administrator is required",
            )

    async def list_workspaces(self, actor_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text("""SELECT w.id,w.name,w.is_active,w.archived_at,w.created_at,w.updated_at,m.role
              FROM ima.workspaces w JOIN ima.workspace_members m ON m.workspace_id=w.id AND m.user_id=:u AND m.state='active'
              JOIN ima.users u ON u.id=m.user_id AND u.is_active WHERE w.is_active ORDER BY w.created_at DESC,w.id DESC"""),
                        {"u": actor_id},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def get_workspace(self, actor_id: str, workspace_id: str) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, workspace_id)
            row = (
                (
                    await conn.execute(
                        text("""SELECT w.id,w.name,w.is_active,w.archived_at,w.created_at,w.updated_at,m.role
              FROM ima.workspaces w JOIN ima.workspace_members m ON m.workspace_id=w.id AND m.user_id=:u AND m.state='active'
              WHERE w.id=:w AND w.is_active"""),
                        {"u": actor_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            return dict(row)

    async def authorize_oauth_boundary(
        self,
        actor_id: str,
        workspace_id: str,
        folder_root_id: str | None,
        target_folder_id: str | None = None,
        target_action: AclAction = AclAction.VIEW_METADATA,
    ) -> None:
        """Validate current human membership and an optional consent root."""
        async with self.engine.connect() as conn:
            member = await self._require_member(conn, actor_id, workspace_id)
            if folder_root_id is not None:
                await self._require_folder_action(
                    conn,
                    member["subject"],
                    workspace_id,
                    folder_root_id,
                    AclAction.VIEW_METADATA,
                )
            if target_folder_id is not None:
                await self._require_folder_action(
                    conn,
                    member["subject"],
                    workspace_id,
                    target_folder_id,
                    target_action,
                )
            if folder_root_id is not None and target_folder_id is not None:
                within_root = await conn.scalar(
                    text(
                        """SELECT EXISTS (
                             SELECT 1 FROM ima.folder_closure
                             WHERE workspace_id=:workspace
                               AND ancestor_id=:root AND descendant_id=:target
                           )"""
                    ),
                    {
                        "workspace": workspace_id,
                        "root": folder_root_id,
                        "target": target_folder_id,
                    },
                )
                if not within_root:
                    raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")

    async def require_workspace_admin(self, actor_id: str, workspace_id: str) -> None:
        """Require active workspace administration for service management."""
        async with self.engine.connect() as conn:
            member = await self._require_member(conn, actor_id, workspace_id)
            if member["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "WORKSPACE_ADMIN_REQUIRED", "Workspace administration is required"
                )

    async def authorize_delegated_boundary(
        self,
        workspace_id: str,
        approved_root_id: str | None,
        target_folder_id: str | None = None,
    ) -> None:
        """Validate service-principal lifecycle and root ancestry.

        The principal is the delegated policy subject and never borrows its
        owner or creator's membership or ACL entries.
        """
        async with self.engine.connect() as conn:
            workspace_active = await conn.scalar(
                text("SELECT is_active FROM ima.workspaces WHERE id=:id"),
                {"id": workspace_id},
            )
            if not workspace_active:
                raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            selected = target_folder_id or approved_root_id
            if selected is None:
                return
            target_active = await conn.scalar(
                text(
                    """SELECT EXISTS (
                         SELECT 1 FROM ima.folders
                         WHERE workspace_id=:workspace AND id=:selected AND lifecycle='active'
                       )"""
                ),
                {"workspace": workspace_id, "selected": selected},
            )
            if not target_active:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if approved_root_id:
                within_root = await conn.scalar(
                    text(
                        """SELECT EXISTS (
                             SELECT 1
                             FROM ima.folder_closure closure
                             JOIN ima.folders root
                               ON root.workspace_id=closure.workspace_id
                              AND root.id=closure.ancestor_id
                              AND root.lifecycle='active'
                             WHERE closure.workspace_id=:workspace
                               AND closure.ancestor_id=:root
                               AND closure.descendant_id=:selected
                           )"""
                    ),
                    {
                        "workspace": workspace_id,
                        "root": approved_root_id,
                        "selected": selected,
                    },
                )
                if not within_root:
                    raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")

    async def _require_delegated_action(
        self,
        conn: AsyncConnection,
        actor: McpActor,
        workspace_id: str,
        folder_id: str | None,
        action: AclAction,
    ) -> None:
        if actor.actor_type != "service_principal" or actor.principal_id is None:
            raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT p.workspace_id,p.folder_root_id,p.scopes,w.is_active
                           FROM ima.mcp_service_principals p
                           JOIN ima.workspaces w ON w.id=p.workspace_id
                           WHERE p.id=CAST(:principal AS uuid) AND p.state='active'
                             AND p.expires_at>:now"""
                    ),
                    {"principal": actor.principal_id, "now": now()},
                )
            )
            .mappings()
            .first()
        )
        if (
            not row
            or not row["is_active"]
            or str(row["workspace_id"]) != workspace_id
            or actor.workspace_id != workspace_id
            or row["folder_root_id"] != actor.folder_root_id
            or not set(actor.scopes).issubset(set(row["scopes"]))
        ):
            raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
        allowed_scopes = {
            AclAction.VIEW_METADATA: {
                "mcp:workspaces:read",
                "mcp:knowledge:read",
                "mcp:knowledge:search",
            },
            AclAction.VIEW_CONTENT: {
                "mcp:knowledge:read",
                "mcp:knowledge:search",
            },
            AclAction.DOWNLOAD: {"mcp:knowledge:read"},
            AclAction.ASK: {"mcp:knowledge:ask"},
        }.get(action, {"mcp:knowledge:write"})
        if not set(actor.scopes).intersection(allowed_scopes):
            raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
        selected = folder_id or actor.folder_root_id
        if selected is None:
            return
        active = await conn.scalar(
            text(
                "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE workspace_id=:workspace AND id=:folder AND lifecycle='active')"
            ),
            {"workspace": workspace_id, "folder": selected},
        )
        if not active:
            raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
        if actor.folder_root_id:
            within = await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folder_closure WHERE workspace_id=:workspace AND ancestor_id=:root AND descendant_id=:folder)"
                ),
                {
                    "workspace": workspace_id,
                    "root": actor.folder_root_id,
                    "folder": selected,
                },
            )
            if not within:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
        if action in {AclAction.ASK, AclAction.DOWNLOAD}:
            # Dependent content visibility is represented by the same active,
            # in-root delegated policy; no owner membership is consulted.
            return

    async def delegated_folder_ids(
        self, conn: AsyncConnection, actor: McpActor, workspace_id: str, action: AclAction
    ) -> set[str]:
        await self._require_delegated_action(
            conn, actor, workspace_id, actor.folder_root_id, action
        )
        if actor.folder_root_id:
            rows = await conn.execute(
                text(
                    """SELECT f.id FROM ima.folder_closure c
                       JOIN ima.folders f ON f.workspace_id=c.workspace_id AND f.id=c.descendant_id
                       WHERE c.workspace_id=:workspace AND c.ancestor_id=:root
                         AND f.lifecycle='active'"""
                ),
                {"workspace": workspace_id, "root": actor.folder_root_id},
            )
        else:
            rows = await conn.execute(
                text(
                    "SELECT id FROM ima.folders WHERE workspace_id=:workspace AND lifecycle='active'"
                ),
                {"workspace": workspace_id},
            )
        return {str(row[0]) for row in rows}

    async def delegated_workspace(self, actor: McpActor) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self._require_delegated_action(
                conn, actor, actor.workspace_id, actor.folder_root_id, AclAction.VIEW_METADATA
            )
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,name,is_active,archived_at,created_at,updated_at FROM ima.workspaces WHERE id=:id AND is_active"
                        ),
                        {"id": actor.workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            return dict(row)

    async def delegated_folder(self, actor: McpActor, folder_id: str) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            await self._require_delegated_action(
                conn, actor, actor.workspace_id, folder_id, AclAction.VIEW_METADATA
            )
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE workspace_id=:workspace AND id=:id AND lifecycle='active'"
                        ),
                        {"workspace": actor.workspace_id, "id": folder_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            return dict(row)

    async def delegated_folders(self, actor: McpActor, parent_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            visible = await self.delegated_folder_ids(
                conn, actor, actor.workspace_id, AclAction.VIEW_METADATA
            )
            await self._require_delegated_action(
                conn, actor, actor.workspace_id, parent_id, AclAction.VIEW_METADATA
            )
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE workspace_id=:workspace AND parent_id=:parent AND id=ANY(:visible) AND lifecycle='active' ORDER BY order_key,name,id"
                        ),
                        {
                            "workspace": actor.workspace_id,
                            "parent": parent_id,
                            "visible": list(visible),
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def delegated_breadcrumbs(self, actor: McpActor, folder_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_delegated_action(
                conn, actor, actor.workspace_id, folder_id, AclAction.VIEW_METADATA
            )
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT f.id,f.workspace_id,f.parent_id,f.name,f.order_key,f.lifecycle,
                                      f.version,f.is_root,f.acl_anchor_id,c.depth
                               FROM ima.folder_closure c JOIN ima.folders f ON f.id=c.ancestor_id
                                WHERE c.workspace_id=:workspace AND c.descendant_id=:folder
                                  AND f.lifecycle='active'
                                 AND (:root IS NULL OR EXISTS(
                                   SELECT 1 FROM ima.folder_closure scope
                                   WHERE scope.workspace_id=:workspace AND scope.ancestor_id=:root
                                     AND scope.descendant_id=f.id))
                               ORDER BY c.depth DESC"""
                        ),
                        {
                            "workspace": actor.workspace_id,
                            "folder": folder_id,
                            "root": actor.folder_root_id,
                        },
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def create_workspace(
        self, actor_id: str, name: str, admin_user_id: str
    ) -> dict[str, Any]:
        workspace_id = new_legacy_id()
        selected = admin_user_id
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not await self._platform(conn, actor_id, "platform_admin"):
                raise WorkspaceError(
                    403, "PLATFORM_FORBIDDEN", "Platform administration is required"
                )
            exists = await conn.scalar(
                text("SELECT is_active FROM ima.users WHERE id=:id"), {"id": selected}
            )
            if not exists:
                raise WorkspaceError(
                    400,
                    "INVALID_WORKSPACE_ADMIN",
                    "The selected workspace administrator is inactive",
                )
            ts = now()
            await conn.execute(
                text(
                    "INSERT INTO ima.workspaces(id,name,created_by,created_at,updated_at) VALUES (:id,:name,:actor,:now,:now)"
                ),
                {"id": workspace_id, "name": name.strip(), "actor": actor_id, "now": ts},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folders(id,workspace_id,parent_id,name,normalized_name,order_key,is_root,acl_anchor_id,created_by,created_at,updated_at) VALUES (:id,:w,NULL,:name,:normalized,0,true,:id,:actor,:now,:now)"
                ),
                {
                    "id": workspace_id,
                    "w": workspace_id,
                    "name": name.strip(),
                    "normalized": name.casefold().strip(),
                    "actor": actor_id,
                    "now": ts,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_closure(workspace_id,ancestor_id,descendant_id,depth) VALUES (:w,:id,:id,0)"
                ),
                {"w": workspace_id, "id": workspace_id},
            )
            acl_id = str(uuid4())
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_acls(id,folder_id,created_by,updated_by,created_at,updated_at) VALUES (:id,:folder,:actor,:actor,:now,:now)"
                ),
                {"id": acl_id, "folder": workspace_id, "actor": actor_id, "now": ts},
            )
            grants = [
                (role.value, action.value)
                for role, actions in DEFAULT_ROLE_GRANTS.items()
                for action in actions
            ]
            for role, action in grants:
                await conn.execute(
                    text(
                        "INSERT INTO ima.folder_acl_entries(acl_id,subject_type,subject_id,action) VALUES (:acl,'role',:subject,:action)"
                    ),
                    {"acl": acl_id, "subject": role, "action": action},
                )
            await conn.execute(
                text(
                    "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,granted_by,joined_at,updated_at) VALUES (:w,:u,'workspace_admin','active',:actor,:now,:now)"
                ),
                {"w": workspace_id, "u": selected, "actor": actor_id, "now": ts},
            )
            await self._audit(
                conn, actor_id, "workspace.created", "success", workspace=workspace_id
            )
        return await self.get_workspace(selected, workspace_id)

    async def members(
        self, actor_id: str, workspace_id: str, query: str = ""
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, workspace_id)
            rows = (
                (
                    await conn.execute(
                        text("""SELECT m.workspace_id,m.user_id,m.role,m.state,m.version,m.joined_at,m.disabled_at,u.email,u.display_name,u.is_active
              FROM ima.workspace_members m JOIN ima.users u ON u.id=m.user_id WHERE m.workspace_id=:w AND (:q='' OR u.normalized_email LIKE '%'||:q||'%' OR lower(u.display_name) LIKE '%'||:q||'%') ORDER BY u.display_name,u.id"""),
                        {"w": workspace_id, "q": query.casefold().strip()},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def search_users(
        self, actor_id: str, workspace_id: str, query: str
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "MEMBERSHIP_FORBIDDEN", "Workspace administrator access is required"
                )
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT u.id,u.email,u.display_name FROM ima.users u WHERE u.is_active AND (:q='' OR u.normalized_email LIKE '%'||:q||'%' OR lower(u.display_name) LIKE '%'||:q||'%') AND NOT EXISTS(SELECT 1 FROM ima.workspace_members m WHERE m.workspace_id=:w AND m.user_id=u.id) ORDER BY u.display_name,u.id LIMIT 50"""
                        ),
                        {"w": workspace_id, "q": query.casefold().strip()},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def acl_subjects(
        self, actor_id: str, workspace_id: str, query: str = ""
    ) -> list[dict[str, Any]]:
        """Return the complete, workspace-scoped ACL subject picker."""
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.MANAGE_ACL)
            if info["role"] not in {
                WorkspaceRole.WORKSPACE_ADMIN.value,
                WorkspaceRole.KNOWLEDGE_MANAGER.value,
            }:
                raise WorkspaceError(
                    403, "ACL_FORBIDDEN", "Folder permission administration is required"
                )
            needle = query.casefold().strip()
            subjects: list[dict[str, Any]] = [
                {
                    "subjectType": "role",
                    "subjectId": role.value,
                    "label": role.value,
                    "email": None,
                }
                for role in WorkspaceRole
                if not needle or needle in role.value
            ]
            groups = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,name FROM ima.workspace_groups WHERE workspace_id=:w AND (:q='' OR normalized_name LIKE '%'||:q||'%') ORDER BY normalized_name LIMIT 50"
                        ),
                        {"w": workspace_id, "q": needle},
                    )
                )
                .mappings()
                .all()
            )
            subjects.extend(
                {
                    "subjectType": "group",
                    "subjectId": str(row["id"]),
                    "label": str(row["name"]),
                    "email": None,
                }
                for row in groups
            )
            users = (
                (
                    await conn.execute(
                        text(
                            """SELECT u.id,u.email,u.display_name
                                 FROM ima.workspace_members m JOIN ima.users u ON u.id=m.user_id
                                WHERE m.workspace_id=:w AND m.state='active' AND u.is_active
                                  AND (:q='' OR u.normalized_email LIKE '%'||:q||'%' OR lower(u.display_name) LIKE '%'||:q||'%')
                                ORDER BY lower(u.display_name),u.id LIMIT 100"""
                        ),
                        {"w": workspace_id, "q": needle},
                    )
                )
                .mappings()
                .all()
            )
            subjects.extend(
                {
                    "subjectType": "user",
                    "subjectId": str(row["id"]),
                    "label": str(row["display_name"] or row["email"]),
                    "email": str(row["email"]),
                }
                for row in users
            )
            return subjects

    async def add_member(
        self, actor_id: str, workspace_id: str, user_id: str, role: WorkspaceRole
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "MEMBERSHIP_FORBIDDEN", "Workspace administrator access is required"
                )
            active = await conn.scalar(
                text("SELECT is_active FROM ima.users WHERE id=:id"), {"id": user_id}
            )
            if not active:
                raise WorkspaceError(404, "USER_NOT_FOUND", "User not found")
            try:
                await conn.execute(
                    text(
                        "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,granted_by,joined_at,updated_at) VALUES (:w,:u,:role,'active',:actor,:now,:now)"
                    ),
                    {
                        "w": workspace_id,
                        "u": user_id,
                        "role": role.value,
                        "actor": actor_id,
                        "now": now(),
                    },
                )
            except Exception as exc:
                if "unique" in str(exc).lower():
                    raise WorkspaceError(
                        409, "MEMBER_EXISTS", "The user is already a workspace member"
                    ) from None
                raise
            await self._audit(
                conn,
                actor_id,
                "workspace.member.added",
                "success",
                workspace=workspace_id,
                target=user_id,
            )
        return (
            (await self.members(actor_id, workspace_id, ""))[-1]
            if False
            else {
                "workspaceId": workspace_id,
                "userId": user_id,
                "role": role.value,
                "state": "active",
                "version": 1,
            }
        )

    async def issue_invitation(
        self, actor_id: str, workspace_id: str, user_id: str, role: WorkspaceRole
    ) -> dict[str, Any]:
        token = secrets.token_urlsafe(32)
        token_hash = digest(token, self.settings.token_pepper.get_secret_value())
        invitation_id = str(uuid4())
        expires = now() + timedelta(days=7)
        recipient_email: str | None = None
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "INVITATION_FORBIDDEN", "Workspace administrator access is required"
                )
            user = (
                (
                    await conn.execute(
                        text("SELECT email,is_active FROM ima.users WHERE id=:id"), {"id": user_id}
                    )
                )
                .mappings()
                .first()
            )
            if not user or not user["is_active"]:
                raise WorkspaceError(404, "USER_NOT_FOUND", "User not found")
            recipient_email = str(user["email"])
            existing = await conn.scalar(
                text(
                    "SELECT state FROM ima.workspace_members WHERE workspace_id=:w AND user_id=:u"
                ),
                {"w": workspace_id, "u": user_id},
            )
            if existing == MembershipState.ACTIVE.value:
                raise WorkspaceError(409, "MEMBER_EXISTS", "The user is already a workspace member")
            ts = now()
            await conn.execute(
                text(
                    "UPDATE ima.workspace_invitations SET revoked_at=:now WHERE workspace_id=:w AND user_id=:u AND accepted_at IS NULL AND revoked_at IS NULL"
                ),
                {"w": workspace_id, "u": user_id, "now": ts},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.workspace_invitations(id,workspace_id,user_id,role,token_digest,invited_by,expires_at,created_at) VALUES (:id,:w,:u,:role,:token,:actor,:expires,:now)"
                ),
                {
                    "id": invitation_id,
                    "w": workspace_id,
                    "u": user_id,
                    "role": role.value,
                    "token": token_hash,
                    "actor": actor_id,
                    "expires": expires,
                    "now": ts,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,granted_by,invited_at,updated_at) VALUES (:w,:u,:role,'invited',:actor,:now,:now) ON CONFLICT(workspace_id,user_id) DO UPDATE SET role=EXCLUDED.role,state='invited',invited_at=EXCLUDED.invited_at,version=ima.workspace_members.version+1,updated_at=EXCLUDED.updated_at"
                ),
                {"w": workspace_id, "u": user_id, "role": role.value, "actor": actor_id, "now": ts},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.invitation.issued",
                "success",
                workspace=workspace_id,
                target=invitation_id,
            )
        if self.mail.enabled:
            try:
                await self.mail.send_invitation(recipient_email or "", token)
            except Exception as exc:
                async with self.engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE ima.workspace_invitations SET revoked_at=:now WHERE id=:id AND accepted_at IS NULL"
                        ),
                        {"id": invitation_id, "now": now()},
                    )
                    await conn.execute(
                        text(
                            "UPDATE ima.workspace_members SET state='disabled',disabled_at=:now,version=version+1,updated_at=:now WHERE workspace_id=:w AND user_id=:u AND state='invited'"
                        ),
                        {"w": workspace_id, "u": user_id, "now": now()},
                    )
                    await self._audit(
                        conn,
                        actor_id,
                        "workspace.invitation.delivery_failed",
                        "failure",
                        workspace=workspace_id,
                        target=invitation_id,
                        reason="smtp_delivery_failed",
                    )
                raise WorkspaceError(
                    503, "INVITATION_DELIVERY_FAILED", "Invitation delivery is unavailable"
                ) from exc
            return {
                "id": invitation_id,
                "workspaceId": workspace_id,
                "userId": user_id,
                "role": role.value,
                "delivery": "sent",
                "expiresAt": expires,
            }
        return {
            "id": invitation_id,
            "workspaceId": workspace_id,
            "userId": user_id,
            "role": role.value,
            "delivery": "manual",
            "expiresAt": expires,
            "boundLink": f"{self.settings.public_origin.rstrip('/')}/invite/{token}",
        }

    async def invitations(self, actor_id: str, workspace_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "INVITATION_FORBIDDEN", "Workspace administrator access is required"
                )
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,user_id,role,expires_at,accepted_at,revoked_at,created_at FROM ima.workspace_invitations WHERE workspace_id=:w ORDER BY created_at DESC"
                        ),
                        {"w": workspace_id},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def revoke_invitation(self, actor_id: str, workspace_id: str, invitation_id: str) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "INVITATION_FORBIDDEN", "Workspace administrator access is required"
                )
            result = await conn.execute(
                text(
                    "UPDATE ima.workspace_invitations SET revoked_at=:now WHERE id=:id AND workspace_id=:w AND accepted_at IS NULL AND revoked_at IS NULL"
                ),
                {"id": invitation_id, "w": workspace_id, "now": now()},
            )
            if not result.rowcount:
                raise WorkspaceError(404, "INVITATION_NOT_FOUND", "Invitation not found")
            await conn.execute(
                text(
                    "UPDATE ima.workspace_members SET state='disabled',disabled_at=:now,version=version+1,updated_at=:now WHERE workspace_id=:w AND user_id=(SELECT user_id FROM ima.workspace_invitations WHERE id=:id) AND state='invited'"
                ),
                {"id": invitation_id, "w": workspace_id, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.invitation.revoked",
                "success",
                workspace=workspace_id,
                target=invitation_id,
            )

    async def accept_invitation(self, actor_id: str, token: str) -> dict[str, Any]:
        token_hash = digest(token, self.settings.token_pepper.get_secret_value())
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT i.id,i.workspace_id,i.user_id,i.role,i.expires_at,w.is_active,u.is_active AS user_active FROM ima.workspace_invitations i JOIN ima.workspaces w ON w.id=i.workspace_id JOIN ima.users u ON u.id=i.user_id WHERE i.token_digest=:token AND i.accepted_at IS NULL AND i.revoked_at IS NULL FOR UPDATE"
                        ),
                        {"token": token_hash},
                    )
                )
                .mappings()
                .first()
            )
            if (
                not row
                or str(row["user_id"]) != actor_id
                or row["expires_at"] <= now()
                or not row["is_active"]
                or not row["user_active"]
            ):
                raise WorkspaceError(
                    400,
                    "INVITATION_INVALID",
                    "Invitation is expired, revoked, or not assigned to this account",
                )
            ts = now()
            membership_updated = await conn.execute(
                text(
                    "UPDATE ima.workspace_members SET state='active',joined_at=:now,disabled_at=NULL,version=version+1,updated_at=:now WHERE workspace_id=:w AND user_id=:u AND state='invited'"
                ),
                {"w": row["workspace_id"], "u": actor_id, "now": ts},
            )
            if not membership_updated.rowcount:
                raise WorkspaceError(
                    400,
                    "INVITATION_INVALID",
                    "Invitation is expired, revoked, or not assigned to this account",
                )
            await conn.execute(
                text("UPDATE ima.workspace_invitations SET accepted_at=:now WHERE id=:id"),
                {"id": row["id"], "now": ts},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.invitation.accepted",
                "success",
                workspace=str(row["workspace_id"]),
                target=str(row["id"]),
            )
            return {
                "workspaceId": str(row["workspace_id"]),
                "userId": actor_id,
                "role": row["role"],
                "state": "active",
            }

    async def mutate_member(
        self,
        actor_id: str,
        workspace_id: str,
        user_id: str,
        *,
        role: WorkspaceRole | None = None,
        state: MembershipState | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "MEMBERSHIP_FORBIDDEN", "Workspace administrator access is required"
                )
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT role,state,version FROM ima.workspace_members WHERE workspace_id=:w AND user_id=:u FOR UPDATE"
                        ),
                        {"w": workspace_id, "u": user_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "MEMBER_NOT_FOUND", "Member not found")
            if expected_version is not None and int(row["version"]) != expected_version:
                raise WorkspaceError(
                    409, "VERSION_CONFLICT", "The membership changed; reload and retry"
                )
            if state is MembershipState.INVITED:
                raise WorkspaceError(
                    400,
                    "INVALID_MEMBERSHIP_STATE",
                    "Invited membership can only be created through an invitation",
                )
            demotes = (
                role is not None
                and row["role"] == WorkspaceRole.WORKSPACE_ADMIN.value
                and role is not WorkspaceRole.WORKSPACE_ADMIN
            )
            disables = (
                state is not None
                and state is not MembershipState.ACTIVE
                and row["state"] == MembershipState.ACTIVE
            )
            if demotes or disables:
                await self._last_admin_guard(
                    conn, workspace_id, removing=user_id, actor_id=actor_id
                )
            values = {
                "role": role.value if role else row["role"],
                "state": state.value if state else row["state"],
                "version": int(row["version"]) + 1,
                "disabled": now() if state and state is MembershipState.DISABLED else None,
            }
            await conn.execute(
                text(
                    "UPDATE ima.workspace_members SET role=:role,state=:state,version=:version,disabled_at=:disabled,updated_at=:now WHERE workspace_id=:w AND user_id=:u"
                ),
                {**values, "now": now(), "w": workspace_id, "u": user_id},
            )
            if state is MembershipState.DISABLED:
                await conn.execute(
                    text(
                        "UPDATE ima.workspace_invitations SET revoked_at=:now WHERE workspace_id=:w AND user_id=:u AND accepted_at IS NULL AND revoked_at IS NULL"
                    ),
                    {"w": workspace_id, "u": user_id, "now": now()},
                )
            await self._audit(
                conn,
                actor_id,
                "workspace.member.updated",
                "success",
                workspace=workspace_id,
                target=user_id,
                metadata={"version": values["version"]},
            )
            return {"workspaceId": workspace_id, "userId": user_id, **values}

    async def remove_member(
        self, actor_id: str, workspace_id: str, user_id: str, expected_version: int | None = None
    ) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "MEMBERSHIP_FORBIDDEN", "Workspace administrator access is required"
                )
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT role,version FROM ima.workspace_members WHERE workspace_id=:w AND user_id=:u FOR UPDATE"
                        ),
                        {"w": workspace_id, "u": user_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "MEMBER_NOT_FOUND", "Member not found")
            if row["role"] == WorkspaceRole.WORKSPACE_ADMIN.value:
                await self._last_admin_guard(
                    conn, workspace_id, removing=user_id, actor_id=actor_id
                )
            if expected_version is not None and int(row["version"]) != expected_version:
                raise WorkspaceError(
                    409, "VERSION_CONFLICT", "The membership changed; reload and retry"
                )
            await conn.execute(
                text("DELETE FROM ima.workspace_members WHERE workspace_id=:w AND user_id=:u"),
                {"w": workspace_id, "u": user_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.workspace_invitations SET revoked_at=:now WHERE workspace_id=:w AND user_id=:u AND accepted_at IS NULL AND revoked_at IS NULL"
                ),
                {"w": workspace_id, "u": user_id, "now": now()},
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.workspace_group_members gm USING ima.workspace_groups g WHERE gm.group_id=g.id AND g.workspace_id=:w AND gm.user_id=:u"
                ),
                {"w": workspace_id, "u": user_id},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.member.removed",
                "success",
                workspace=workspace_id,
                target=user_id,
            )

    async def leave(self, actor_id: str, workspace_id: str) -> None:
        await self.remove_member(actor_id, workspace_id, actor_id)

    async def groups(self, actor_id: str, workspace_id: str) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, workspace_id)
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT g.id,g.workspace_id,g.name,g.version,count(gm.user_id)::integer AS member_count FROM ima.workspace_groups g LEFT JOIN ima.workspace_group_members gm ON gm.group_id=g.id WHERE g.workspace_id=:w GROUP BY g.id ORDER BY g.name"""
                        ),
                        {"w": workspace_id},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def create_group(self, actor_id: str, workspace_id: str, name: str) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "GROUP_FORBIDDEN", "Workspace administrator access is required"
                )
            gid = str(uuid4())
            ts = now()
            try:
                await conn.execute(
                    text(
                        "INSERT INTO ima.workspace_groups(id,workspace_id,name,normalized_name,created_by,created_at,updated_at) VALUES (:id,:w,:name,:normalized,:actor,:now,:now)"
                    ),
                    {
                        "id": gid,
                        "w": workspace_id,
                        "name": name.strip(),
                        "normalized": name.casefold().strip(),
                        "actor": actor_id,
                        "now": ts,
                    },
                )
            except Exception as exc:
                if "unique" in str(exc).lower():
                    raise WorkspaceError(
                        409, "GROUP_EXISTS", "A group with this name already exists"
                    ) from None
                raise
            await self._audit(
                conn,
                actor_id,
                "workspace.group.created",
                "success",
                workspace=workspace_id,
                target=gid,
            )
            return {
                "id": gid,
                "workspaceId": workspace_id,
                "name": name.strip(),
                "version": 1,
                "memberCount": 0,
            }

    async def group_members(
        self, actor_id: str, workspace_id: str, group_id: str
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            await self._require_member(conn, actor_id, workspace_id)
            exists = await conn.scalar(
                text("SELECT 1 FROM ima.workspace_groups WHERE id=:g AND workspace_id=:w"),
                {"g": group_id, "w": workspace_id},
            )
            if not exists:
                raise WorkspaceError(404, "GROUP_NOT_FOUND", "Group not found")
            rows = (
                (
                    await conn.execute(
                        text("""SELECT u.id,u.email,u.display_name FROM ima.workspace_group_members gm
                              JOIN ima.users u ON u.id=gm.user_id WHERE gm.group_id=:g ORDER BY u.display_name,u.id"""),
                        {"g": group_id},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def delete_group(
        self, actor_id: str, workspace_id: str, group_id: str, expected_version: int | None = None
    ) -> dict[str, int]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "GROUP_FORBIDDEN", "Workspace administrator access is required"
                )
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT version FROM ima.workspace_groups WHERE id=:id AND workspace_id=:w FOR UPDATE"
                        ),
                        {"id": group_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "GROUP_NOT_FOUND", "Group not found")
            if expected_version is not None and int(row["version"]) != expected_version:
                raise WorkspaceError(409, "VERSION_CONFLICT", "The group changed; reload and retry")
            affected = int(
                await conn.scalar(
                    text(
                        "SELECT count(DISTINCT a.folder_id) FROM ima.folder_acl_entries e JOIN ima.folder_acls a ON a.id=e.acl_id WHERE e.subject_type='group' AND e.subject_id=:id"
                    ),
                    {"id": group_id},
                )
                or 0
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.folder_acl_entries WHERE subject_type='group' AND subject_id=:id"
                ),
                {"id": group_id},
            )
            await conn.execute(
                text("DELETE FROM ima.workspace_groups WHERE id=:id"), {"id": group_id}
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.group.deleted",
                "success",
                workspace=workspace_id,
                target=group_id,
                metadata={"affectedAclCount": affected},
            )
            return {"affectedAclCount": affected}

    async def group_member(
        self, actor_id: str, workspace_id: str, group_id: str, user_id: str, add: bool
    ) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id)
            if info["role"] != WorkspaceRole.WORKSPACE_ADMIN.value:
                raise WorkspaceError(
                    403, "GROUP_FORBIDDEN", "Workspace administrator access is required"
                )
            valid = await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.workspace_members m JOIN ima.workspace_groups g ON g.workspace_id=m.workspace_id WHERE g.id=:g AND m.user_id=:u AND m.state='active' AND m.workspace_id=:w)"
                ),
                {"g": group_id, "u": user_id, "w": workspace_id},
            )
            if not valid:
                raise WorkspaceError(404, "MEMBER_NOT_FOUND", "Active workspace member not found")
            if add:
                await conn.execute(
                    text(
                        "INSERT INTO ima.workspace_group_members(group_id,user_id,granted_by,created_at) VALUES (:g,:u,:a,:now) ON CONFLICT DO NOTHING"
                    ),
                    {"g": group_id, "u": user_id, "a": actor_id, "now": now()},
                )
            else:
                await conn.execute(
                    text(
                        "DELETE FROM ima.workspace_group_members WHERE group_id=:g AND user_id=:u"
                    ),
                    {"g": group_id, "u": user_id},
                )
            await self._audit(
                conn,
                actor_id,
                "workspace.group.member_changed",
                "success",
                workspace=workspace_id,
                target=group_id,
                metadata={"userId": user_id, "added": add},
            )

    async def folders(
        self, actor_id: str, workspace_id: str, parent_id: str | None = None
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.VIEW_METADATA)
            subject = info["subject"]
            if parent_id is not None:
                await self._require_folder_action(
                    conn, subject, workspace_id, parent_id, AclAction.VIEW_METADATA
                )
            ids = await accessible_folder_ids(
                conn, subject, AclAction.VIEW_METADATA, root_id=parent_id
            )
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE workspace_id=:w AND (:p IS NULL AND parent_id IS NULL OR parent_id=:p) AND id IN :ids ORDER BY order_key,name,id"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"w": workspace_id, "p": parent_id, "ids": ids or {"__none__"}},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def breadcrumbs(
        self, actor_id: str, workspace_id: str, folder_id: str
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id)
            visible = await accessible_folder_ids(conn, info["subject"], AclAction.VIEW_METADATA)
            if folder_id not in visible:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            rows = (
                (
                    await conn.execute(
                        text("""SELECT f.id,f.workspace_id,f.parent_id,f.name,f.order_key,f.lifecycle,f.version,f.is_root,f.acl_anchor_id,c.depth
                              FROM ima.folder_closure c JOIN ima.folders f ON f.id=c.ancestor_id
                             WHERE c.workspace_id=:w AND c.descendant_id=:folder AND f.id IN :visible
                             ORDER BY c.depth DESC""").bindparams(
                            bindparam("visible", expanding=True)
                        ),
                        {"w": workspace_id, "folder": folder_id, "visible": visible},
                    )
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in rows]

    async def create_folder(
        self, actor_id: str, workspace_id: str, parent_id: str, name: str
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not name.strip():
                raise WorkspaceError(400, "INVALID_FOLDER_NAME", "Folder name cannot be blank")
            info = await self._require_member(
                conn, workspace_id=workspace_id, actor_id=actor_id, action=AclAction.CREATE_CHILD
            )
            parent = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": parent_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not parent:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await self._require_folder_action(
                conn, info["subject"], workspace_id, parent_id, AclAction.CREATE_CHILD
            )
            normalized_name = name.casefold().strip()
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE workspace_id=:w AND parent_id=:p AND lifecycle='active' AND normalized_name=:name)"
                ),
                {"w": workspace_id, "p": parent_id, "name": normalized_name},
            ):
                raise WorkspaceError(
                    409, "FOLDER_NAME_EXISTS", "A folder with this name already exists"
                )
            fid = new_legacy_id()
            ts = now()
            anchor = str(parent["acl_anchor_id"])
            await conn.execute(
                text(
                    "INSERT INTO ima.folders(id,workspace_id,parent_id,name,normalized_name,order_key,lifecycle,version,is_root,acl_anchor_id,created_by,created_at,updated_at) VALUES (:id,CAST(:w AS varchar(32)),CAST(:p AS varchar(32)),:name,:normalized,COALESCE((SELECT max(order_key)+1 FROM ima.folders WHERE workspace_id=CAST(:w AS varchar(32)) AND parent_id=CAST(:p AS varchar(32)) AND lifecycle='active'),0),'active',1,false,:anchor,:actor,:now,:now)"
                ),
                {
                    "id": fid,
                    "w": workspace_id,
                    "p": parent_id,
                    "name": name.strip(),
                    "normalized": normalized_name,
                    "anchor": anchor,
                    "actor": actor_id,
                    "now": ts,
                },
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_closure(workspace_id,ancestor_id,descendant_id,depth) SELECT CAST(:w AS varchar(32)),ancestor_id,CAST(:id AS varchar(32)),depth+1 FROM ima.folder_closure WHERE workspace_id=CAST(:w AS varchar(32)) AND descendant_id=CAST(:p AS varchar(32)) UNION ALL SELECT CAST(:w AS varchar(32)),CAST(:id AS varchar(32)),CAST(:id AS varchar(32)),0"
                ),
                {"w": workspace_id, "p": parent_id, "id": fid},
            )
            order_key = await conn.scalar(
                text("SELECT order_key FROM ima.folders WHERE id=:id"), {"id": fid}
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.folder.created",
                "success",
                workspace=workspace_id,
                target=fid,
            )
            return {
                "id": fid,
                "workspaceId": workspace_id,
                "parentId": parent_id,
                "name": name.strip(),
                "orderKey": int(order_key or 0),
                "version": 1,
                "lifecycle": "active",
                "aclAnchorId": anchor,
                "isRoot": False,
            }

    async def folder(
        self,
        actor_id: str,
        workspace_id: str,
        folder_id: str,
        action: AclAction = AclAction.VIEW_METADATA,
    ) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id, action)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active'"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            decision = await folder_decision(conn, info["subject"], folder_id, action)
            if not decision.allowed:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            return dict(row)

    async def rename_folder(
        self, actor_id: str, workspace_id: str, folder_id: str, name: str, expected_version: int
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not name.strip():
                raise WorkspaceError(400, "INVALID_FOLDER_NAME", "Folder name cannot be blank")
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.EDIT)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT version,is_root FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await self._require_folder_action(
                conn,
                info["subject"],
                workspace_id,
                folder_id,
                AclAction.EDIT,
            )
            if row["is_root"]:
                raise WorkspaceError(400, "ROOT_PROTECTED", "The root folder cannot be renamed")
            if int(row["version"]) != expected_version:
                raise WorkspaceError(
                    409, "VERSION_CONFLICT", "The folder changed; reload and retry"
                )
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders f JOIN ima.folders current ON current.id=:id WHERE f.workspace_id=:w AND f.parent_id=current.parent_id AND f.lifecycle='active' AND f.id<>:id AND f.normalized_name=:name)"
                ),
                {"w": workspace_id, "id": folder_id, "name": name.casefold().strip()},
            ):
                raise WorkspaceError(
                    409, "FOLDER_NAME_EXISTS", "A folder with this name already exists"
                )
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
                "workspace.folder.renamed",
                "success",
                workspace=workspace_id,
                target=folder_id,
            )
            updated = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE id=:id"
                        ),
                        {"id": folder_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(updated)

    async def move_folder(
        self,
        actor_id: str,
        workspace_id: str,
        folder_id: str,
        destination_id: str,
        expected_version: int,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.MOVE)
            source = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            dest = (
                (
                    await conn.execute(
                        text(
                            "SELECT * FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": destination_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not source or not dest:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await self._require_folder_action(
                conn, info["subject"], workspace_id, folder_id, AclAction.MOVE
            )
            await self._require_folder_action(
                conn, info["subject"], workspace_id, destination_id, AclAction.CREATE_CHILD
            )
            if source["is_root"] or int(source["version"]) != expected_version:
                raise WorkspaceError(
                    409 if not source["is_root"] else 400,
                    "VERSION_CONFLICT" if not source["is_root"] else "ROOT_PROTECTED",
                    "The folder changed; reload and retry"
                    if not source["is_root"]
                    else "The root folder cannot move",
                )
            if bool(
                await conn.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ima.folder_closure WHERE workspace_id=CAST(:w AS varchar(32)) AND ancestor_id=CAST(:source AS varchar(32)) AND descendant_id=CAST(:dest AS varchar(32)))"
                    ),
                    {"w": workspace_id, "source": folder_id, "dest": destination_id},
                )
            ):
                raise WorkspaceError(
                    400, "FOLDER_CYCLE", "A folder cannot move into its own subtree"
                )
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE workspace_id=:w AND parent_id=:dest AND lifecycle='active' AND normalized_name=:name AND id<>:source)"
                ),
                {
                    "w": workspace_id,
                    "dest": destination_id,
                    "name": source["normalized_name"],
                    "source": folder_id,
                },
            ):
                raise WorkspaceError(
                    409, "FOLDER_NAME_EXISTS", "A folder with this name already exists"
                )
            if not (
                await folder_decision(conn, info["subject"], destination_id, AclAction.CREATE_CHILD)
            ).allowed:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await conn.execute(
                text(
                    "DELETE FROM ima.folder_closure WHERE workspace_id=CAST(:w AS varchar(32)) AND descendant_id IN (SELECT descendant_id FROM ima.folder_closure WHERE workspace_id=CAST(:w AS varchar(32)) AND ancestor_id=CAST(:source AS varchar(32))) AND ancestor_id IN (SELECT ancestor_id FROM ima.folder_closure WHERE workspace_id=CAST(:w AS varchar(32)) AND descendant_id=CAST(:source AS varchar(32)) AND ancestor_id<>CAST(:source AS varchar(32)))"
                ),
                {"w": workspace_id, "source": folder_id},
            )
            await conn.execute(
                text(
                    "INSERT INTO ima.folder_closure(workspace_id,ancestor_id,descendant_id,depth) SELECT CAST(:w AS varchar(32)),up.ancestor_id,down.descendant_id,up.depth+down.depth+1 FROM ima.folder_closure up CROSS JOIN ima.folder_closure down WHERE up.workspace_id=CAST(:w AS varchar(32)) AND up.descendant_id=CAST(:dest AS varchar(32)) AND down.workspace_id=CAST(:w AS varchar(32)) AND down.ancestor_id=CAST(:source AS varchar(32)) ON CONFLICT DO NOTHING"
                ),
                {"w": workspace_id, "source": folder_id, "dest": destination_id},
            )
            await conn.execute(
                text(
                    "UPDATE ima.folders SET parent_id=:dest,version=version+1,updated_at=:now WHERE id=:source"
                ),
                {"source": folder_id, "dest": destination_id, "now": now()},
            )
            # The nearest independent ACL can change when a subtree crosses an
            # ACL boundary.  Recompute anchors for the whole moved subtree in
            # this transaction; independent descendants resolve to themselves.
            await conn.execute(
                text(
                    """WITH subtree AS (
                         SELECT descendant_id AS id
                           FROM ima.folder_closure
                          WHERE workspace_id=:w AND ancestor_id=:source
                       ), next_anchor AS (
                         SELECT s.id,
                                (SELECT c.ancestor_id
                                   FROM ima.folder_closure c
                                   JOIN ima.folder_acls a ON a.folder_id=c.ancestor_id
                                  WHERE c.workspace_id=:w AND c.descendant_id=s.id
                                  ORDER BY c.depth ASC
                                  LIMIT 1) AS anchor_id
                           FROM subtree s
                       )
                       UPDATE ima.folders f
                          SET acl_anchor_id=n.anchor_id,
                              version=f.version + CASE WHEN f.acl_anchor_id IS DISTINCT FROM n.anchor_id THEN 1 ELSE 0 END,
                              updated_at=:now
                         FROM next_anchor n
                        WHERE f.id=n.id AND f.acl_anchor_id IS DISTINCT FROM n.anchor_id"""
                ),
                {"w": workspace_id, "source": folder_id, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.folder.moved",
                "success",
                workspace=workspace_id,
                target=folder_id,
            )
            return dict(
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE id=:id"
                        ),
                        {"id": folder_id},
                    )
                )
                .mappings()
                .one()
            )

    async def reorder_folder(
        self,
        actor_id: str,
        workspace_id: str,
        folder_id: str,
        order_key: int,
        expected_version: int,
    ) -> dict[str, Any]:
        """Move a folder among active siblings while preserving dense order."""
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.EDIT)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT parent_id,order_key,version,is_root,lifecycle FROM ima.folders WHERE id=:id AND workspace_id=:w FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row or row["lifecycle"] != "active":
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if row["is_root"]:
                raise WorkspaceError(400, "ROOT_PROTECTED", "The root folder cannot be reordered")
            await self._require_folder_action(
                conn, info["subject"], workspace_id, folder_id, AclAction.EDIT
            )
            if int(row["version"]) != expected_version:
                raise WorkspaceError(
                    409, "VERSION_CONFLICT", "The folder changed; reload and retry"
                )
            siblings = int(
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.folders WHERE workspace_id=:w AND parent_id=:p AND lifecycle='active'"
                    ),
                    {"w": workspace_id, "p": row["parent_id"]},
                )
                or 1
            )
            old = int(row["order_key"])
            desired = max(0, min(int(order_key), siblings - 1))
            if desired > old:
                await conn.execute(
                    text(
                        "UPDATE ima.folders SET order_key=order_key-1 WHERE workspace_id=:w AND parent_id=:p AND lifecycle='active' AND id<>:id AND order_key>:old AND order_key<=:desired"
                    ),
                    {
                        "w": workspace_id,
                        "p": row["parent_id"],
                        "id": folder_id,
                        "old": old,
                        "desired": desired,
                    },
                )
            elif desired < old:
                await conn.execute(
                    text(
                        "UPDATE ima.folders SET order_key=order_key+1 WHERE workspace_id=:w AND parent_id=:p AND lifecycle='active' AND id<>:id AND order_key>=:desired AND order_key<:old"
                    ),
                    {
                        "w": workspace_id,
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
                "workspace.folder.reordered",
                "success",
                workspace=workspace_id,
                target=folder_id,
                metadata={"orderKey": desired},
            )
            updated = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,parent_id,name,order_key,lifecycle,version,is_root,acl_anchor_id FROM ima.folders WHERE id=:id"
                        ),
                        {"id": folder_id},
                    )
                )
                .mappings()
                .one()
            )
            return dict(updated)

    async def trash_folder(
        self, actor_id: str, workspace_id: str, folder_id: str, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.DELETE)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT is_root,parent_id,order_key,version,lifecycle FROM ima.folders WHERE id=:id AND workspace_id=:w FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await self._require_folder_action(
                conn,
                info["subject"],
                workspace_id,
                folder_id,
                AclAction.DELETE,
            )
            if row["is_root"]:
                raise WorkspaceError(400, "ROOT_PROTECTED", "The root folder cannot be trashed")
            if row["lifecycle"] != "active" or int(row["version"]) != expected_version:
                raise WorkspaceError(
                    409, "VERSION_CONFLICT", "The folder changed; reload and retry"
                )
            await conn.execute(
                text(
                    "UPDATE ima.folders SET lifecycle='trashed',original_parent_id=parent_id,original_order_key=order_key,trashed_at=:now,version=version+1,updated_at=:now WHERE id=:id"
                ),
                {"id": folder_id, "now": now()},
            )
            await conn.execute(
                text(
                    """UPDATE ima.folders
                          SET lifecycle='trashed',trashed_at=:now,version=version+1,updated_at=:now
                        WHERE workspace_id=:w
                          AND id IN (SELECT descendant_id FROM ima.folder_closure
                                       WHERE workspace_id=:w AND ancestor_id=:id AND descendant_id<>:id)
                          AND lifecycle='active'"""
                ),
                {"w": workspace_id, "id": folder_id, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.folder.trashed",
                "success",
                workspace=workspace_id,
                target=folder_id,
            )

    async def restore_folder(
        self, actor_id: str, workspace_id: str, folder_id: str, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.EDIT)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT is_root,original_parent_id,normalized_name,version,lifecycle FROM ima.folders WHERE id=:id AND workspace_id=:w FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if (
                not row
                or row["is_root"]
                or row["lifecycle"] != "trashed"
                or int(row["version"]) != expected_version
            ):
                raise WorkspaceError(
                    409, "VERSION_CONFLICT", "The folder cannot be restored from its current state"
                )
            await self._require_folder_action(
                conn,
                info["subject"],
                workspace_id,
                folder_id,
                AclAction.EDIT,
                include_trashed=True,
            )
            parent = row["original_parent_id"] or workspace_id
            valid = await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active')"
                ),
                {"id": parent, "w": workspace_id},
            )
            if not valid:
                raise WorkspaceError(
                    409, "RESTORE_DESTINATION_MISSING", "The original parent is no longer available"
                )
            await self._require_folder_action(
                conn, info["subject"], workspace_id, str(parent), AclAction.CREATE_CHILD
            )
            if await conn.scalar(
                text(
                    "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE workspace_id=:w AND parent_id=:p AND lifecycle='active' AND normalized_name=:name AND id<>:id)"
                ),
                {
                    "w": workspace_id,
                    "p": parent,
                    "name": row["normalized_name"],
                    "id": folder_id,
                },
            ):
                raise WorkspaceError(
                    409, "FOLDER_NAME_EXISTS", "A folder with this name already exists"
                )
            await conn.execute(
                text(
                    "UPDATE ima.folders SET lifecycle='active',parent_id=:parent,trashed_at=NULL,version=version+1,updated_at=:now WHERE id=:id"
                ),
                {"id": folder_id, "parent": parent, "now": now()},
            )
            await conn.execute(
                text(
                    """UPDATE ima.folders
                          SET lifecycle='active',trashed_at=NULL,version=version+1,updated_at=:now
                        WHERE workspace_id=:w
                          AND id IN (SELECT descendant_id FROM ima.folder_closure
                                       WHERE workspace_id=:w AND ancestor_id=:id AND descendant_id<>:id)
                          AND lifecycle='trashed'"""
                ),
                {"w": workspace_id, "id": folder_id, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.folder.restored",
                "success",
                workspace=workspace_id,
                target=folder_id,
            )

    async def delete_folder(
        self, actor_id: str, workspace_id: str, folder_id: str, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.DELETE)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT is_root,lifecycle,version FROM ima.folders WHERE id=:id AND workspace_id=:w FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await self._require_folder_action(
                conn,
                info["subject"],
                workspace_id,
                folder_id,
                AclAction.DELETE,
                include_trashed=True,
            )
            if row["is_root"]:
                raise WorkspaceError(400, "ROOT_PROTECTED", "The root folder cannot be deleted")
            if row["lifecycle"] != "trashed" or int(row["version"]) != expected_version:
                raise WorkspaceError(
                    409, "FOLDER_NOT_TRASHED", "Only trashed folders can be permanently deleted"
                )
            descendants = int(
                await conn.scalar(
                    text(
                        "SELECT count(*) FROM ima.folder_closure WHERE workspace_id=:w AND ancestor_id=:id AND depth>0"
                    ),
                    {"w": workspace_id, "id": folder_id},
                )
                or 0
            )
            if descendants:
                raise WorkspaceError(
                    409, "FOLDER_DEPENDENCIES", "Folder still contains child folders"
                )
            await conn.execute(text("DELETE FROM ima.folders WHERE id=:id"), {"id": folder_id})
            await self._audit(
                conn,
                actor_id,
                "workspace.folder.deleted",
                "success",
                workspace=workspace_id,
                target=folder_id,
            )

    async def set_acl(
        self,
        actor_id: str,
        workspace_id: str,
        folder_id: str,
        *,
        inherit: bool,
        entries: list[dict[str, str]],
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.MANAGE_ACL)
            folder = (
                (
                    await conn.execute(
                        text(
                            "SELECT is_root,acl_anchor_id FROM ima.folders WHERE id=:id AND workspace_id=:w AND lifecycle='active' FOR UPDATE"
                        ),
                        {"id": folder_id, "w": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not folder:
                raise WorkspaceError(404, "FOLDER_NOT_FOUND", "Folder not found")
            await self._require_folder_action(
                conn, info["subject"], workspace_id, folder_id, AclAction.MANAGE_ACL
            )
            old_anchor = str(folder["acl_anchor_id"])
            current = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,version FROM ima.folder_acls WHERE folder_id=:f FOR UPDATE"
                        ),
                        {"f": folder_id},
                    )
                )
                .mappings()
                .first()
            )
            if current and expected_version is None:
                raise WorkspaceError(
                    409, "VERSION_REQUIRED", "The current ACL version is required for mutation"
                )
            if (
                expected_version is not None
                and current
                and int(current["version"]) != expected_version
            ):
                raise WorkspaceError(409, "VERSION_CONFLICT", "The ACL changed; reload and retry")
            if inherit:
                if folder["is_root"]:
                    raise WorkspaceError(
                        400, "ROOT_PROTECTED", "The root ACL is always independent"
                    )
                anchor = await conn.scalar(
                    text(
                        "SELECT p.acl_anchor_id FROM ima.folders f JOIN ima.folders p ON p.id=f.parent_id WHERE f.id=:f"
                    ),
                    {"f": folder_id},
                )
                await conn.execute(
                    text(
                        """UPDATE ima.folders
                              SET acl_anchor_id=:anchor, version=version+1, updated_at=:now
                            WHERE workspace_id=:w
                              AND id IN (SELECT descendant_id FROM ima.folder_closure
                                           WHERE workspace_id=:w AND ancestor_id=:folder)
                              AND (id=:folder OR acl_anchor_id=:old_anchor)"""
                    ),
                    {
                        "anchor": anchor,
                        "folder": folder_id,
                        "old_anchor": old_anchor,
                        "w": workspace_id,
                        "now": now(),
                    },
                )
                await conn.execute(
                    text("DELETE FROM ima.folder_acls WHERE folder_id=:f"), {"f": folder_id}
                )
            else:
                if not current and folder["acl_anchor_id"] != folder_id and not entries:
                    inherited = (
                        (
                            await conn.execute(
                                text(
                                    """SELECT e.subject_type,e.subject_id,e.action FROM ima.folder_acl_entries e
                                   JOIN ima.folder_acls a ON a.id=e.acl_id WHERE a.folder_id=:folder"""
                                ),
                                {"folder": folder["acl_anchor_id"]},
                            )
                        )
                        .mappings()
                        .all()
                    )
                    entries = [dict(item) for item in inherited]
                grants_by_subject: dict[tuple[str, str], set[AclAction]] = {}
                for entry in entries:
                    key = (entry.get("subject_type", ""), entry.get("subject_id", ""))
                    if key in grants_by_subject and entry["action"] in {
                        action.value for action in grants_by_subject[key]
                    }:
                        raise WorkspaceError(400, "DUPLICATE_ACL_ENTRY", "Duplicate ACL grant")
                    try:
                        parsed_action = AclAction(entry["action"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise WorkspaceError(400, "INVALID_ACTION", "Unknown ACL action") from exc
                    grants_by_subject.setdefault(key, set()).add(parsed_action)
                for grants in grants_by_subject.values():
                    try:
                        validate_grants(grants)
                    except ValueError as exc:
                        raise WorkspaceError(400, "INVALID_ACTION_DEPENDENCY", str(exc)) from exc
                administrable = any(
                    subject_type == SubjectType.ROLE.value
                    and subject_id
                    in {
                        WorkspaceRole.WORKSPACE_ADMIN.value,
                        WorkspaceRole.KNOWLEDGE_MANAGER.value,
                    }
                    and AclAction.MANAGE_ACL in grants
                    for (subject_type, subject_id), grants in grants_by_subject.items()
                )
                if not administrable:
                    raise WorkspaceError(
                        400,
                        "ACL_NOT_ADMINISTRABLE",
                        "An independent ACL must retain an administrable workspace administrator grant",
                    )
                acl_id = str(current["id"]) if current else str(uuid4())
                ts = now()
                if current:
                    await conn.execute(
                        text(
                            "UPDATE ima.folder_acls SET version=version+1,updated_by=:actor,updated_at=:now WHERE id=:id"
                        ),
                        {"id": acl_id, "actor": actor_id, "now": ts},
                    )
                else:
                    await conn.execute(
                        text(
                            "INSERT INTO ima.folder_acls(id,folder_id,created_by,updated_by,created_at,updated_at) VALUES (:id,:f,:actor,:actor,:now,:now)"
                        ),
                        {"id": acl_id, "f": folder_id, "actor": actor_id, "now": ts},
                    )
                await conn.execute(
                    text("DELETE FROM ima.folder_acl_entries WHERE acl_id=:acl"), {"acl": acl_id}
                )
                for entry in entries:
                    if entry["subject_type"] not in {t.value for t in SubjectType}:
                        raise WorkspaceError(400, "INVALID_SUBJECT", "Unsupported ACL subject")
                    if entry["subject_type"] == SubjectType.ROLE.value:
                        if entry["subject_id"] not in {r.value for r in WorkspaceRole}:
                            raise WorkspaceError(400, "INVALID_SUBJECT", "Unknown workspace role")
                    elif entry["subject_type"] == SubjectType.USER.value:
                        valid = await conn.scalar(
                            text("""SELECT EXISTS(SELECT 1 FROM ima.workspace_members m JOIN ima.users u ON u.id=m.user_id
                                      WHERE m.workspace_id=:w AND m.user_id=:id AND m.state='active' AND u.is_active)"""),
                            {"w": workspace_id, "id": entry["subject_id"]},
                        )
                        if not valid:
                            raise WorkspaceError(
                                400, "INVALID_SUBJECT", "User is not an active workspace member"
                            )
                    else:
                        valid = await conn.scalar(
                            text(
                                "SELECT EXISTS(SELECT 1 FROM ima.workspace_groups WHERE id=:id AND workspace_id=:w)"
                            ),
                            {"id": entry["subject_id"], "w": workspace_id},
                        )
                        if not valid:
                            raise WorkspaceError(
                                400, "INVALID_SUBJECT", "Group is not in this workspace"
                            )
                    await conn.execute(
                        text(
                            "INSERT INTO ima.folder_acl_entries(acl_id,subject_type,subject_id,action) VALUES (:acl,:type,:subject,:action)"
                        ),
                        {
                            "acl": acl_id,
                            "type": entry["subject_type"],
                            "subject": entry["subject_id"],
                            "action": entry["action"],
                        },
                    )
                await conn.execute(
                    text(
                        """UPDATE ima.folders
                              SET acl_anchor_id=:f,version=version+1,updated_at=:now
                            WHERE workspace_id=:w
                              AND id IN (SELECT descendant_id FROM ima.folder_closure
                                           WHERE workspace_id=:w AND ancestor_id=:f)
                              AND (id=:f OR acl_anchor_id=:old_anchor)"""
                    ),
                    {"f": folder_id, "old_anchor": old_anchor, "w": workspace_id, "now": ts},
                )
            await self._audit(
                conn,
                actor_id,
                "workspace.folder.acl_changed",
                "success",
                workspace=workspace_id,
                target=folder_id,
                metadata={"inherit": inherit, "entryCount": len(entries)},
            )
        return await self.acl(actor_id, workspace_id, folder_id)

    async def acl(self, actor_id: str, workspace_id: str, folder_id: str) -> dict[str, Any]:
        folder = await self.folder(actor_id, workspace_id, folder_id, AclAction.MANAGE_ACL)
        async with self.engine.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT a.id,a.version,a.folder_id FROM ima.folder_acls a WHERE a.folder_id=:f"
                        ),
                        {"f": folder["acl_anchor_id"]},
                    )
                )
                .mappings()
                .first()
            )
            entries = []
            if row:
                entries = [
                    dict(x)
                    for x in (
                        await conn.execute(
                            text(
                                "SELECT subject_type,subject_id,action FROM ima.folder_acl_entries WHERE acl_id=:a ORDER BY subject_type,subject_id,action"
                            ),
                            {"a": row["id"]},
                        )
                    )
                    .mappings()
                    .all()
                ]
            return {
                "folderId": folder_id,
                "inherited": folder["acl_anchor_id"] != folder_id,
                "effectiveSource": folder["acl_anchor_id"],
                "version": row["version"] if row else 0,
                "entries": entries,
            }

    async def permission_preview(
        self, actor_id: str, workspace_id: str, selected_user_id: str
    ) -> list[dict[str, Any]]:
        async with self.engine.connect() as conn:
            info = await self._require_member(conn, actor_id, workspace_id, AclAction.MANAGE_ACL)
            if info["role"] not in {
                WorkspaceRole.WORKSPACE_ADMIN.value,
                WorkspaceRole.KNOWLEDGE_MANAGER.value,
            }:
                raise WorkspaceError(
                    403, "PREVIEW_FORBIDDEN", "Workspace permission preview is restricted"
                )
            subject = await load_subject(conn, selected_user_id, workspace_id)
            if not subject:
                return []
            ids = await accessible_folder_ids(conn, subject, AclAction.VIEW_METADATA)
            if not ids:
                return []
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,parent_id,name,acl_anchor_id FROM ima.folders WHERE workspace_id=:w AND id IN :ids ORDER BY id"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"w": workspace_id, "ids": ids},
                    )
                )
                .mappings()
                .all()
            )
            return [
                {
                    **dict(row),
                    # A directly granted child may be visible below a hidden
                    # ancestor. Do not leak that ancestor's identifier through
                    # the preview response.
                    "parent_id": row["parent_id"] if row["parent_id"] in ids else None,
                }
                for row in rows
            ]

    async def repair_admin(self, actor_id: str, workspace_id: str, user_id: str) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not await self._platform(conn, actor_id, "platform_admin"):
                raise WorkspaceError(
                    403, "PLATFORM_FORBIDDEN", "Platform administration is required"
                )
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext('ima:workspace-admin:'||:id))"),
                {"id": workspace_id},
            )
            active = await conn.scalar(
                text("SELECT is_active FROM ima.users WHERE id=:id"), {"id": user_id}
            )
            if not active:
                raise WorkspaceError(404, "USER_NOT_FOUND", "User not found")
            exists = await conn.scalar(
                text("SELECT 1 FROM ima.workspaces WHERE id=:id AND is_active"),
                {"id": workspace_id},
            )
            if not exists:
                raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            await conn.execute(
                text(
                    "INSERT INTO ima.workspace_members(workspace_id,user_id,role,state,granted_by,joined_at,updated_at) VALUES (:w,:u,'workspace_admin','active',:a,:now,:now) ON CONFLICT(workspace_id,user_id) DO UPDATE SET role='workspace_admin',state='active',disabled_at=NULL,version=ima.workspace_members.version+1,updated_at=EXCLUDED.updated_at"
                ),
                {"w": workspace_id, "u": user_id, "a": actor_id, "now": now()},
            )
            await self._audit(
                conn,
                actor_id,
                "workspace.admin.repaired",
                "success",
                workspace=workspace_id,
                target=user_id,
            )
            return {
                "workspaceId": workspace_id,
                "userId": user_id,
                "role": WorkspaceRole.WORKSPACE_ADMIN.value,
                "state": MembershipState.ACTIVE.value,
            }

    async def archive_workspace(self, actor_id: str, workspace_id: str) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not await self._platform(conn, actor_id, "platform_admin"):
                raise WorkspaceError(
                    403, "PLATFORM_FORBIDDEN", "Platform administration is required"
                )
            result = await conn.execute(
                text(
                    "UPDATE ima.workspaces SET is_active=false,archived_at=COALESCE(archived_at,:now),updated_at=:now WHERE id=:id AND is_active"
                ),
                {"id": workspace_id, "now": now()},
            )
            if not result.rowcount:
                exists = await conn.scalar(
                    text("SELECT 1 FROM ima.workspaces WHERE id=:id"), {"id": workspace_id}
                )
                if not exists:
                    raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
                raise WorkspaceError(409, "WORKSPACE_ARCHIVED", "Workspace is already archived")
            await self._audit(
                conn, actor_id, "workspace.archived", "success", workspace=workspace_id
            )

    async def restore_workspace(self, actor_id: str, workspace_id: str) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not await self._platform(conn, actor_id, "platform_admin"):
                raise WorkspaceError(
                    403, "PLATFORM_FORBIDDEN", "Platform administration is required"
                )
            result = await conn.execute(
                text(
                    "UPDATE ima.workspaces SET is_active=true,archived_at=NULL,updated_at=:now WHERE id=:id AND NOT is_active"
                ),
                {"id": workspace_id, "now": now()},
            )
            if not result.rowcount:
                exists = await conn.scalar(
                    text("SELECT 1 FROM ima.workspaces WHERE id=:id"), {"id": workspace_id}
                )
                if not exists:
                    raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
                raise WorkspaceError(409, "WORKSPACE_ACTIVE", "Workspace is already active")
            await self._audit(
                conn, actor_id, "workspace.restored", "success", workspace=workspace_id
            )

    async def delete_archived_workspace(self, actor_id: str, workspace_id: str) -> None:
        async with self.engine.begin() as conn:
            await assert_writes_allowed(conn)
            if not await self._platform(conn, actor_id, "platform_admin"):
                raise WorkspaceError(
                    403, "PLATFORM_FORBIDDEN", "Platform administration is required"
                )
            row = (
                (
                    await conn.execute(
                        text("SELECT archived_at FROM ima.workspaces WHERE id=:id FOR UPDATE"),
                        {"id": workspace_id},
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise WorkspaceError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            if row["archived_at"] is None:
                raise WorkspaceError(
                    409, "WORKSPACE_NOT_ARCHIVED", "Workspace must be archived before deletion"
                )
            if await conn.scalar(
                text("SELECT count(*) FROM ima.folders WHERE workspace_id=:id AND id<>:id"),
                {"id": workspace_id},
            ):
                raise WorkspaceError(
                    409,
                    "WORKSPACE_CONTENT_DEPENDENCY",
                    "Workspace still has folder content dependencies",
                )
            await self._audit(
                conn,
                actor_id,
                "workspace.deleted",
                "success",
                workspace=workspace_id,
                target=workspace_id,
                metadata={"targetAuthorizationDeleted": True},
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.folder_acl_entries WHERE acl_id IN (SELECT a.id FROM ima.folder_acls a JOIN ima.folders f ON f.id=a.folder_id WHERE f.workspace_id=:id)"
                ),
                {"id": workspace_id},
            )
            await conn.execute(
                text("DELETE FROM ima.folder_closure WHERE workspace_id=:id"), {"id": workspace_id}
            )
            await conn.execute(
                text("DELETE FROM ima.folders WHERE workspace_id=:id"), {"id": workspace_id}
            )
            await conn.execute(
                text(
                    "DELETE FROM ima.workspace_group_members WHERE group_id IN (SELECT id FROM ima.workspace_groups WHERE workspace_id=:id)"
                ),
                {"id": workspace_id},
            )
            await conn.execute(
                text("DELETE FROM ima.workspace_groups WHERE workspace_id=:id"),
                {"id": workspace_id},
            )
            await conn.execute(
                text("DELETE FROM ima.workspace_invitations WHERE workspace_id=:id"),
                {"id": workspace_id},
            )
            await conn.execute(
                text("DELETE FROM ima.workspace_members WHERE workspace_id=:id"),
                {"id": workspace_id},
            )
            # The registry keeps a nullable creator reference for auditability;
            # clear it before deleting the workspace so later account removal is
            # not blocked by a stale foreign-key reference.
            await conn.execute(
                text("UPDATE ima.workspaces SET created_by=NULL WHERE id=:id"),
                {"id": workspace_id},
            )
            await conn.execute(
                text("DELETE FROM ima.workspaces WHERE id=:id"), {"id": workspace_id}
            )
