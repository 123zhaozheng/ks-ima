"""Safe legacy MCP connector inventory and sunset classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast

Decision = Literal["reissued", "revoked"]


@dataclass(frozen=True, slots=True)
class LegacyConnector:
    id: str
    mode: str
    folder_root_id: str | None
    expires_at: datetime | None
    revoked_at: datetime | None


def classify_connector(
    connector: LegacyConnector, decisions: dict[str, Decision], *, now: datetime
) -> Decision | Literal["pending"]:
    if connector.revoked_at is not None or (
        connector.expires_at is not None and connector.expires_at <= now
    ):
        return "revoked"
    return decisions.get(connector.id, "pending")


def safe_inventory(
    connectors: tuple[LegacyConnector, ...], decisions: Mapping[str, object]
) -> dict[str, object]:
    connector_ids = [connector.id for connector in connectors]
    duplicate_ids = sorted(
        connector_id for connector_id in set(connector_ids) if connector_ids.count(connector_id) > 1
    )
    if duplicate_ids:
        raise ValueError(f"duplicate legacy connector ids: {duplicate_ids}")
    if any(not isinstance(key, str) for key in decisions):
        raise ValueError("legacy connector decision ids must be strings")
    invalid = sorted(
        key for key, value in decisions.items() if value not in {"reissued", "revoked"}
    )
    if invalid:
        raise ValueError(f"invalid legacy connector decisions: {invalid}")
    unknown = sorted(set(decisions) - set(connector_ids))
    if unknown:
        raise ValueError(f"unknown legacy connector ids: {unknown}")
    unsupported_modes = sorted(
        connector.id for connector in connectors if connector.mode not in {"read", "readwrite"}
    )
    if unsupported_modes:
        raise ValueError(f"legacy connectors have unsupported modes: {unsupported_modes}")

    now = datetime.now(UTC)
    typed_decisions = cast(dict[str, Decision], dict(decisions))
    contradictory = sorted(
        connector.id
        for connector in connectors
        if typed_decisions.get(connector.id) == "reissued"
        and (
            connector.revoked_at is not None
            or (connector.expires_at is not None and connector.expires_at <= now)
        )
    )
    if contradictory:
        raise ValueError(f"inactive legacy connectors cannot be reissued: {contradictory}")
    records = [
        {
            "connectorId": item.id,
            "mode": item.mode,
            "folderScoped": item.folder_root_id is not None,
            "classification": classify_connector(item, typed_decisions, now=now),
        }
        for item in connectors
    ]
    counts = {
        status: sum(record["classification"] == status for record in records)
        for status in ("reissued", "revoked", "pending")
    }
    return {
        "canonicalResource": "/mcp",
        "legacyAlias": "/api/mcp",
        "records": records,
        "counts": counts,
        "complete": counts["pending"] == 0,
        "secretValues": False,
    }
