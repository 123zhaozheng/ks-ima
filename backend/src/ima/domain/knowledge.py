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
    order_key: int
    normalized_name: str
    item_id: str

    def encode(self) -> str:
        raw = json.dumps(
            {
                "v": 1,
                "parentId": self.parent_id,
                "childrenVersion": self.children_version,
                "orderKey": self.order_key,
                "name": self.normalized_name,
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
            if payload.get("v") != 1 or not all(
                key in payload for key in ("parentId", "childrenVersion", "orderKey", "name", "id")
            ):
                raise ValueError
            return cls(
                str(payload["parentId"]),
                int(payload["childrenVersion"]),
                int(payload["orderKey"]),
                str(payload["name"]),
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
