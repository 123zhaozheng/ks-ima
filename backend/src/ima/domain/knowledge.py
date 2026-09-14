"""Pure contracts used by the knowledge tree application service."""

from __future__ import annotations

import base64
import hashlib
import json
import unicodedata
from dataclasses import dataclass
from typing import Any


def normalize_name(value: str, *, limit: int = 200) -> tuple[str, str]:
    display = unicodedata.normalize("NFKC", value).strip()
    if not display or len(display) > limit:
        raise ValueError("name must not be empty or exceed its limit")
    return display, display.casefold()


def markdown_digest(markdown: str) -> str:
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ListingCursor:
    parent_id: str
    children_version: int
    # v2: the sort context is part of the cursor so a page from one ordering is
    # never silently applied to another. ``last_value`` is the string form of
    # the active sort key's value on the last returned row (order_key for
    # manual, casefolded title for name, ISO timestamp for created_at).
    sort: str
    group: str
    last_value: str
    item_id: str

    def encode(self) -> str:
        raw = json.dumps(
            {
                "v": 2,
                "parentId": self.parent_id,
                "childrenVersion": self.children_version,
                "sort": self.sort,
                "group": self.group,
                "lastValue": self.last_value,
                "id": self.item_id,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, value: str) -> ListingCursor:
        try:
            padded = value + "=" * (-len(value) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
            if payload.get("v") != 2 or not all(
                key in payload
                for key in ("parentId", "childrenVersion", "sort", "group", "lastValue", "id")
            ):
                raise ValueError
            return cls(
                str(payload["parentId"]),
                int(payload["childrenVersion"]),
                str(payload["sort"]),
                str(payload["group"]),
                str(payload["lastValue"]),
                str(payload["id"]),
            )
        except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("invalid cursor") from exc


def safe_metadata(row: Any) -> dict[str, Any]:
    return {
        "mimeType": row.get("mime_type") if hasattr(row, "get") else None,
        "sizeBytes": row.get("size_bytes") if hasattr(row, "get") else None,
        "checksum": row.get("checksum") if hasattr(row, "get") else None,
        "fileState": row.get("file_state") if hasattr(row, "get") else "pending",
    }
