"""Counts-only archive report for legacy conversations.

Scope decision (2026-08-28): conversation/chat history is NOT migrated — the
system was never live in production. This report only counts legacy rows so
operators can record what is left behind before legacy deletion.
"""

from __future__ import annotations

from collections.abc import Mapping

CONVERSATION_TABLES = ("chat", "message", "messageEntity", "toolCall")


def build_conversation_archive_report(counts: Mapping[str, int | None]) -> dict[str, object]:
    """Build the counts-only archive report.

    ``counts`` maps legacy table name to row count; ``None`` means the table
    does not exist and is omitted from the report.
    """
    tables = {
        name: int(count) for name in CONVERSATION_TABLES if (count := counts.get(name)) is not None
    }
    return {
        "canonicalResource": "/conversations",
        "migrated": False,
        "decision": "counts_only_archive",
        "tables": tables,
        "totalRows": sum(tables.values()),
        "secretValues": False,
    }
