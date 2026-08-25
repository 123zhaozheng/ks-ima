"""Pure validation and normalization rules for the legacy knowledge import."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


class LegacyKnowledgeIssue(ValueError):
    """A source row cannot be imported without guessing."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class LegacyPatchImport:
    snapshots: tuple[str, ...]
    reason: str | None = None


def source_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return a stable digest without logging or storing source content."""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def normalize_legacy_tags(value: object) -> tuple[tuple[str, str], ...]:
    """Normalize JSON conf.tags while rejecting malformed values explicitly."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise LegacyKnowledgeIssue("malformed_tags")
    result: dict[str, str] = {}
    for raw in value:
        if not isinstance(raw, str):
            raise LegacyKnowledgeIssue("malformed_tag_value")
        display = unicodedata.normalize("NFKC", raw).strip()
        if not display or len(display) > 120:
            raise LegacyKnowledgeIssue("malformed_tag_value")
        result.setdefault(display.casefold(), display)
    return tuple(sorted(result.items()))


def hierarchy_issues(rows: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Classify cycles, dangling parents, and cross-workspace parent links."""
    source = {str(row["id"]): row for row in rows}
    issues: dict[str, str] = {}
    for source_id, row in source.items():
        root_id = str(row.get("root_id", row.get("rootId", "")))
        parent_id = row.get("parent_id", row.get("parentId")) or root_id
        parent_id = str(parent_id)
        parent = source.get(parent_id)
        if parent is None and parent_id != root_id:
            issues[source_id] = "dangling_parent"
            continue
        if parent is None:
            continue
        parent_root = str(parent.get("root_id", parent.get("rootId", "")))
        if parent_root != root_id:
            issues[source_id] = "cross_workspace_parent"
            continue
        seen: set[str] = set()
        current = source_id
        while current in source:
            if current in seen:
                issues[source_id] = "hierarchy_cycle"
                break
            seen.add(current)
            current_parent = source[current].get("parent_id", source[current].get("parentId"))
            if current_parent is None:
                break
            current = str(current_parent)
    return issues


def classify_page_patches(patches: Sequence[Mapping[str, Any]]) -> LegacyPatchImport:
    """Import only explicit complete-text snapshots from the patch log.

    Legacy rows do not carry an initial document or a sequence timestamp. A
    JSON-patch operation therefore cannot be replayed safely. The only
    supported shape is ``{"text": "..."}`` (or a list of those snapshots),
    where every version body is self-contained.
    """
    snapshots: list[str] = []
    for row in patches:
        raw = row.get("patch")
        try:
            value = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            return LegacyPatchImport((), "unsupported_patch_history")
        values = value if isinstance(value, list) else [value]
        if not values:
            return LegacyPatchImport((), "unsupported_patch_history")
        for item in values:
            if (
                not isinstance(item, dict)
                or set(item) != {"text"}
                or not isinstance(item["text"], str)
            ):
                return LegacyPatchImport((), "unsupported_patch_history")
            snapshots.append(item["text"])
    return LegacyPatchImport(tuple(snapshots))


def collision_reason(*, existing: bool, source_ids: Sequence[str]) -> str | None:
    """Return a stable collision reason for deterministic migration reports."""
    if existing:
        return "target_id_collision"
    if len(set(source_ids)) != len(source_ids):
        return "source_id_collision"
    return None
