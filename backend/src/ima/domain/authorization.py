"""Canonical workspace authorization vocabulary and decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class WorkspaceRole(StrEnum):
    WORKSPACE_ADMIN = "workspace_admin"
    KNOWLEDGE_MANAGER = "knowledge_manager"
    EDITOR = "editor"
    VIEWER = "viewer"


class MembershipState(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class AclAction(StrEnum):
    VIEW_METADATA = "view_metadata"
    VIEW_CONTENT = "view_content"
    DOWNLOAD = "download"
    ASK = "ask"
    CREATE_CHILD = "create_child"
    EDIT = "edit"
    MOVE = "move"
    DELETE = "delete"
    MANAGE_ACL = "manage_acl"


class SubjectType(StrEnum):
    ROLE = "role"
    GROUP = "group"
    USER = "user"


class PolicyReason(StrEnum):
    ALLOWED = "allowed"
    INACTIVE_ACTOR = "inactive_actor"
    INACTIVE_WORKSPACE = "inactive_workspace"
    MISSING_MEMBERSHIP = "missing_membership"
    OUTSIDE_SCOPE = "outside_scope"
    MISSING_GRANT = "missing_grant"
    ROOT_PROTECTED = "root_protected"
    LAST_WORKSPACE_ADMIN = "last_workspace_admin"
    VERSION_CONFLICT = "version_conflict"


ALL_ACTIONS: frozenset[AclAction] = frozenset(AclAction)
DEFAULT_ROLE_GRANTS: dict[WorkspaceRole, frozenset[AclAction]] = {
    WorkspaceRole.WORKSPACE_ADMIN: ALL_ACTIONS,
    WorkspaceRole.KNOWLEDGE_MANAGER: ALL_ACTIONS,
    WorkspaceRole.EDITOR: ALL_ACTIONS - {AclAction.MANAGE_ACL},
    WorkspaceRole.VIEWER: frozenset(
        {AclAction.VIEW_METADATA, AclAction.VIEW_CONTENT, AclAction.DOWNLOAD, AclAction.ASK}
    ),
}


@dataclass(frozen=True, slots=True)
class SubjectContext:
    user_id: str
    workspace_id: str
    role: WorkspaceRole
    group_ids: frozenset[str] = frozenset()
    account_active: bool = True
    workspace_active: bool = True
    membership_active: bool = True


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: PolicyReason
    folder_id: str | None = None
    acl_anchor_id: str | None = None


def validate_grants(grants: frozenset[AclAction] | set[AclAction]) -> frozenset[AclAction]:
    """Reject dependent operations that would otherwise create misleading ACLs."""
    normalized = frozenset(grants)
    if AclAction.ASK in normalized and AclAction.VIEW_CONTENT not in normalized:
        raise ValueError("ask requires view_content")
    if AclAction.DOWNLOAD in normalized and not {
        AclAction.VIEW_METADATA,
        AclAction.VIEW_CONTENT,
    }.issubset(normalized):
        raise ValueError("download requires view_metadata and view_content")
    return normalized
