"""Canonical knowledge base authorization vocabulary and decision contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KbRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class MembershipState(StrEnum):
    ACTIVE = "active"


class KbShareRole(StrEnum):
    """Roles that a knowledge base share link may confer on joiners."""

    EDITOR = "editor"
    VIEWER = "viewer"


class KbAction(StrEnum):
    VIEW_METADATA = "view_metadata"
    VIEW_CONTENT = "view_content"
    DOWNLOAD = "download"
    ASK = "ask"
    CREATE_CHILD = "create_child"
    EDIT = "edit"
    MOVE = "move"
    DELETE = "delete"


class PolicyReason(StrEnum):
    ALLOWED = "allowed"
    INACTIVE_ACTOR = "inactive_actor"
    INACTIVE_KNOWLEDGE_BASE = "inactive_knowledge_base"
    MISSING_MEMBERSHIP = "missing_membership"
    INSUFFICIENT_ROLE = "insufficient_role"
    ROOT_PROTECTED = "root_protected"
    LAST_OWNER = "last_owner"
    VERSION_CONFLICT = "version_conflict"


ALL_ACTIONS: frozenset[KbAction] = frozenset(KbAction)
DEFAULT_ROLE_GRANTS: dict[KbRole, frozenset[KbAction]] = {
    KbRole.OWNER: ALL_ACTIONS,
    KbRole.EDITOR: frozenset(
        {
            KbAction.VIEW_METADATA,
            KbAction.VIEW_CONTENT,
            KbAction.DOWNLOAD,
            KbAction.ASK,
            KbAction.CREATE_CHILD,
            KbAction.EDIT,
            KbAction.MOVE,
            KbAction.DELETE,
        }
    ),
    KbRole.VIEWER: frozenset(
        {KbAction.VIEW_METADATA, KbAction.VIEW_CONTENT, KbAction.DOWNLOAD, KbAction.ASK}
    ),
}


@dataclass(frozen=True, slots=True)
class MemberContext:
    """The actor's membership posture inside one knowledge base."""

    user_id: str
    kb_id: str
    role: KbRole
    account_active: bool = True
    kb_active: bool = True


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: PolicyReason
    folder_id: str | None = None


def role_allows(role: KbRole, action: KbAction) -> bool:
    """Membership role decides every knowledge action; owner never loses."""
    return action in DEFAULT_ROLE_GRANTS[role]
