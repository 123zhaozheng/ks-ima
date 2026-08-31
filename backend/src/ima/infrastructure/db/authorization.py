"""Knowledge base membership policy reads.

The membership role is the single authorization decision for knowledge base
access.  There are no folder ACL joins, user groups, or invitation states:
every predicate filters ``ima.kb_members`` joined to an active account and an
active knowledge base.  KnowledgeService, storage/search services, and the MCP
runtime reuse these helpers instead of duplicating mutable policy SQL.
"""

# Keep policy SQL visible for review.
# ruff: noqa: E501

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ima.domain.authorization import KbRole, MemberContext

ROLE_LEVEL: dict[KbRole, int] = {
    KbRole.VIEWER: 1,
    KbRole.EDITOR: 2,
    KbRole.OWNER: 3,
}


class MembershipRequired(LookupError):
    """The user has no active membership in the knowledge base.

    Adapters map this to their 404-equivalent error so non-membership never
    leaks knowledge base metadata.
    """

    def __init__(self, user_id: str, kb_id: str) -> None:
        super().__init__("knowledge base membership required")
        self.user_id = user_id
        self.kb_id = kb_id


class InsufficientRole(Exception):
    """The membership exists but the role is below the required minimum."""

    def __init__(self, user_id: str, kb_id: str, role: KbRole, required: KbRole) -> None:
        super().__init__(f"role {role.value} is below the required {required.value}")
        self.user_id = user_id
        self.kb_id = kb_id
        self.role = role
        self.required = required


def role_at_least(role: KbRole, minimum: KbRole) -> bool:
    """Owner > editor > viewer; write access requires editor or above."""
    return ROLE_LEVEL[role] >= ROLE_LEVEL[minimum]


def membership_sql() -> str:
    """The single membership predicate used by every knowledge base check."""
    return """
      SELECT m.role
        FROM ima.kb_members m
        JOIN ima.knowledge_bases kb ON kb.id=m.kb_id AND kb.is_active
        JOIN ima.users u ON u.id=m.user_id AND u.is_active
       WHERE m.kb_id=:kb_id AND m.user_id=:user_id AND m.state='active'
    """


async def load_membership(conn: AsyncConnection, user_id: str, kb_id: str) -> MemberContext | None:
    """Load the membership context, keeping inactive flags for audit detail."""
    row = (
        (
            await conn.execute(
                text(
                    """SELECT m.role,u.is_active AS account_active,kb.is_active AS kb_active
                         FROM ima.kb_members m
                         JOIN ima.knowledge_bases kb ON kb.id=m.kb_id
                         JOIN ima.users u ON u.id=m.user_id
                        WHERE m.kb_id=:kb_id AND m.user_id=:user_id AND m.state='active'"""
                ),
                {"kb_id": kb_id, "user_id": user_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    return MemberContext(
        user_id=user_id,
        kb_id=kb_id,
        role=KbRole(str(row["role"])),
        account_active=bool(row["account_active"]),
        kb_active=bool(row["kb_active"]),
    )


def membership_active(member: MemberContext) -> bool:
    """Account disablement and kb archival take effect on the very next decision."""
    return member.account_active and member.kb_active


async def require_membership(conn: AsyncConnection, user_id: str, kb_id: str) -> KbRole:
    """Return the active member role or raise ``MembershipRequired``."""
    member = await load_membership(conn, user_id, kb_id)
    if member is None or not membership_active(member):
        raise MembershipRequired(user_id, kb_id)
    return member.role


async def require_role(conn: AsyncConnection, user_id: str, kb_id: str, minimum: KbRole) -> KbRole:
    """Return the active role when it satisfies ``minimum``.

    Reads require ``viewer`` or above; writes require ``editor`` or above.
    """
    role = await require_membership(conn, user_id, kb_id)
    if not role_at_least(role, minimum):
        raise InsufficientRole(user_id, kb_id, role, minimum)
    return role
