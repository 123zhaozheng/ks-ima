"""Read-time normalization of legacy blob checksums.

The legacy Bun server stored SHA-256 digests as base64 (``digest('base64')``)
while the Python storage layer compares lowercase hex digests. Legacy rows are
never rewritten; values are normalized only at read time before they reach
``ObjectStorageClient.copy_verified`` or any ``ima.*`` checksum column.
"""

from __future__ import annotations

import base64
import binascii
import re

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEX_SHA256_LOOSE = re.compile(r"^[0-9a-fA-F]{64}$")
_BASE64_SHA256 = re.compile(r"^[A-Za-z0-9+/]{43}=$")


def normalize_legacy_checksum(value: str) -> str:
    """Return the lowercase hex SHA-256 for a legacy checksum value.

    Accepts either a 64-character hex digest (any case) or the base64
    encoding of a 32-byte digest as written by the legacy server. Raises
    ``ValueError`` for anything else so callers can route the row to review.
    """
    candidate = value.strip()
    if _HEX_SHA256.match(candidate):
        return candidate
    if _HEX_SHA256_LOOSE.match(candidate):
        return candidate.lower()
    if _BASE64_SHA256.match(candidate):
        try:
            raw = base64.b64decode(candidate, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError(f"unreadable legacy checksum encoding: {candidate!r}") from exc
        if len(raw) == 32:
            return raw.hex()
    raise ValueError(f"unrecognized legacy checksum format: {candidate!r}")
