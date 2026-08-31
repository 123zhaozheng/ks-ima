"""Maintenance write-freeze for operational windows.

Transport-neutral service: the API layer maps ``MaintenanceFreezeError`` to a
RFC 9457 problem response. Migration-tagged writers (the ``ima`` CLI) never
call ``assert_writes_allowed`` and keep working during the freeze.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.domain.authorization import KbAction

MAINTENANCE_WRITE_FREEZE = "MAINTENANCE_WRITE_FREEZE"

#: Knowledge actions that mutate state and must be refused during freeze.
MUTATING_ACTIONS = frozenset(
    {
        KbAction.CREATE_CHILD,
        KbAction.EDIT,
        KbAction.MOVE,
        KbAction.DELETE,
    }
)


class MaintenanceFreezeError(Exception):
    """Safe refusal while the maintenance write freeze is active."""

    status_code = 503
    code = MAINTENANCE_WRITE_FREEZE

    def __init__(self, detail: str = "Write freeze active during migration maintenance") -> None:
        super().__init__(detail)
        self.detail = detail


async def freeze_active(conn: AsyncConnection) -> bool:
    value = await conn.scalar(
        text("SELECT maintenance_write_freeze FROM ima.system_settings WHERE id=true")
    )
    return bool(value)


async def assert_writes_allowed(conn: AsyncConnection) -> None:
    if await freeze_active(conn):
        raise MaintenanceFreezeError()


async def assert_mutation_allowed(conn: AsyncConnection, action: KbAction) -> None:
    """Refuse mutating knowledge actions while the freeze is active; reads pass."""
    if action in MUTATING_ACTIONS:
        await assert_writes_allowed(conn)


def _status_payload(row: Any) -> dict[str, Any]:
    return {
        "frozen": bool(row[0]),
        "reason": row[1],
        "enteredAt": row[2].isoformat() if row[2] else None,
        "enteredBy": row[3],
        "canonicalResource": "/system/settings",
        "secretValues": False,
    }


_STATUS_SQL = (
    "SELECT maintenance_write_freeze,maintenance_freeze_reason,"
    "maintenance_freeze_entered_at,maintenance_freeze_entered_by "
    "FROM ima.system_settings WHERE id=true"
)


class MaintenanceService:
    """Enter/exit/status for the typed write-freeze flag with audit rows."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def _require_super_admin(self, conn: AsyncConnection, operator_id: str) -> None:
        authorized = await conn.scalar(
            text(
                """SELECT EXISTS(
                       SELECT 1
                       FROM ima.platform_role_assignments AS role
                       JOIN ima.users AS operator ON operator.id=role.user_id
                       WHERE role.user_id=:operator AND role.role='super_admin'
                         AND operator.is_active=true AND operator.disabled_at IS NULL
                   )"""
            ),
            {"operator": operator_id},
        )
        if not authorized:
            raise PermissionError("operator is not an active super-admin")

    async def enter_freeze(self, operator_id: str, reason: str) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await self._require_super_admin(conn, operator_id)
            await conn.execute(
                text(
                    """UPDATE ima.system_settings SET maintenance_write_freeze=true,
                    maintenance_freeze_reason=:reason,maintenance_freeze_entered_at=now(),
                    maintenance_freeze_entered_by=:operator,updated_at=now(),updated_by=:operator
                    WHERE id=true"""
                ),
                {"reason": reason, "operator": operator_id},
            )
            await conn.execute(
                text(
                    """INSERT INTO ima.audit_events(
                        actor_id,action,target_type,target_id,
                        result,reason_code,metadata,created_at)
                    VALUES (
                        :operator,'maintenance.freeze.enter',
                        'system_settings','maintenance_write_freeze',
                        'success',NULL,CAST(:metadata AS jsonb),now())"""
                ),
                {
                    "operator": operator_id,
                    "metadata": json.dumps({"reason": reason, "secretValues": False}),
                },
            )
            row = (await conn.execute(text(_STATUS_SQL))).one()
        return _status_payload(row)

    async def exit_freeze(self, operator_id: str) -> dict[str, Any]:
        async with self.engine.begin() as conn:
            await self._require_super_admin(conn, operator_id)
            await conn.execute(
                text(
                    """UPDATE ima.system_settings SET maintenance_write_freeze=false,
                    maintenance_freeze_reason=NULL,maintenance_freeze_entered_at=NULL,
                    maintenance_freeze_entered_by=NULL,updated_at=now(),updated_by=:operator
                    WHERE id=true"""
                ),
                {"operator": operator_id},
            )
            await conn.execute(
                text(
                    """INSERT INTO ima.audit_events(
                        actor_id,action,target_type,target_id,
                        result,reason_code,metadata,created_at)
                    VALUES (
                        :operator,'maintenance.freeze.exit',
                        'system_settings','maintenance_write_freeze',
                        'success',NULL,'{"secretValues": false}'::jsonb,now())"""
                ),
                {"operator": operator_id},
            )
            row = (await conn.execute(text(_STATUS_SQL))).one()
        return _status_payload(row)

    async def freeze_status(self) -> dict[str, Any]:
        async with self.engine.connect() as conn:
            row = (await conn.execute(text(_STATUS_SQL))).one()
        return _status_payload(row)
