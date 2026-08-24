"""Set-based SQL policy predicates and authorization reads."""

# Keep policy SQL visible for review.
# ruff: noqa: E501

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ima.domain.authorization import (
    AclAction,
    PolicyDecision,
    PolicyReason,
    SubjectContext,
    WorkspaceRole,
)


def accessible_folder_ids_sql() -> str:
    """The single predicate used by direct and collection policy operations."""
    return """
      SELECT DISTINCT f.id
      FROM ima.folders f
      JOIN ima.workspaces w ON w.id=f.workspace_id AND w.is_active
      JOIN ima.workspace_members m ON m.workspace_id=f.workspace_id AND m.user_id=:user_id AND m.state='active'
      JOIN ima.users u ON u.id=m.user_id AND u.is_active
      JOIN ima.folder_acls a ON a.folder_id=f.acl_anchor_id
      JOIN ima.folder_acl_entries e ON e.acl_id=a.id AND e.action=:requested_action
      LEFT JOIN ima.workspace_group_members gm ON gm.group_id::text=e.subject_id AND gm.user_id=m.user_id
      LEFT JOIN ima.workspace_groups g ON g.id=gm.group_id AND g.workspace_id=f.workspace_id
      WHERE f.workspace_id=:workspace_id
        AND (:include_trashed OR f.lifecycle='active')
        AND (:include_trashed OR NOT EXISTS (
          SELECT 1 FROM ima.folder_closure blocked_scope
          JOIN ima.folders blocked_folder ON blocked_folder.id=blocked_scope.ancestor_id
          WHERE blocked_scope.workspace_id=f.workspace_id
            AND blocked_scope.descendant_id=f.id
            AND blocked_folder.lifecycle='trashed'
        ))
        AND (e.subject_type='user' AND e.subject_id=m.user_id
          OR e.subject_type='role' AND e.subject_id=m.role
          OR e.subject_type='group' AND gm.user_id=m.user_id AND g.id IS NOT NULL)
        AND NOT EXISTS (
          SELECT 1
          FROM unnest(CAST(:required_actions AS text[])) required_action(action)
          WHERE NOT EXISTS (
            SELECT 1 FROM ima.folder_acl_entries required_entry
            WHERE required_entry.acl_id=e.acl_id
              AND required_entry.subject_type=e.subject_type
              AND required_entry.subject_id=e.subject_id
              AND required_entry.action=required_action.action
          )
        )
    """


async def accessible_folder_ids(
    conn: AsyncConnection,
    subject: SubjectContext,
    action: AclAction,
    *,
    root_id: str | None = None,
    include_trashed: bool = False,
) -> set[str]:
    actions = [action.value]
    if action is AclAction.ASK:
        actions.append(AclAction.VIEW_CONTENT.value)
    if action is AclAction.DOWNLOAD:
        actions.extend((AclAction.VIEW_METADATA.value, AclAction.VIEW_CONTENT.value))
    query = accessible_folder_ids_sql()
    if root_id:
        query += " AND EXISTS (SELECT 1 FROM ima.folder_closure scope WHERE scope.workspace_id=f.workspace_id AND scope.ancestor_id=:root_id AND scope.descendant_id=f.id)"
    rows = await conn.execute(
        text(query),
        {
            "user_id": subject.user_id,
            "workspace_id": subject.workspace_id,
            "requested_action": action.value,
            "required_actions": actions,
            "root_id": root_id,
            "include_trashed": include_trashed,
        },
    )
    return {str(row[0]) for row in rows}


async def folder_decision(
    conn: AsyncConnection,
    subject: SubjectContext,
    folder_id: str,
    action: AclAction,
    *,
    include_trashed: bool = False,
) -> PolicyDecision:
    if not subject.account_active or not subject.membership_active:
        return PolicyDecision(False, PolicyReason.INACTIVE_ACTOR, folder_id)
    if not subject.workspace_active:
        return PolicyDecision(False, PolicyReason.INACTIVE_WORKSPACE, folder_id)
    ids = await accessible_folder_ids(conn, subject, action, include_trashed=include_trashed)
    if folder_id not in ids:
        return PolicyDecision(False, PolicyReason.MISSING_GRANT, folder_id)
    anchor = await conn.scalar(
        text(
            "SELECT acl_anchor_id FROM ima.folders WHERE id=:id AND workspace_id=:workspace_id AND (lifecycle='active' OR :include_trashed)"
        ),
        {
            "id": folder_id,
            "workspace_id": subject.workspace_id,
            "include_trashed": include_trashed,
        },
    )
    return PolicyDecision(True, PolicyReason.ALLOWED, folder_id, str(anchor) if anchor else None)


async def load_subject(
    conn: AsyncConnection, user_id: str, workspace_id: str
) -> SubjectContext | None:
    row = (
        (
            await conn.execute(
                text("""SELECT u.is_active AS account_active,w.is_active AS workspace_active,m.state,m.role
                    FROM ima.users u JOIN ima.workspaces w ON w.id=:workspace_id
                    LEFT JOIN ima.workspace_members m ON m.workspace_id=w.id AND m.user_id=u.id
                    WHERE u.id=:user_id"""),
                {"user_id": user_id, "workspace_id": workspace_id},
            )
        )
        .mappings()
        .first()
    )
    if not row or row["state"] != "active":
        return None
    groups = await conn.execute(
        text("""SELECT gm.group_id FROM ima.workspace_group_members gm JOIN ima.workspace_groups g ON g.id=gm.group_id
               WHERE g.workspace_id=:workspace_id AND gm.user_id=:user_id"""),
        {"workspace_id": workspace_id, "user_id": user_id},
    )
    return SubjectContext(
        user_id=user_id,
        workspace_id=workspace_id,
        role=WorkspaceRole(str(row["role"])),
        group_ids=frozenset(str(r[0]) for r in groups),
        account_active=bool(row["account_active"]),
        workspace_active=bool(row["workspace_active"]),
    )
