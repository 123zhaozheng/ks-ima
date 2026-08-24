"""Pure compatibility checks used by the legacy identity importer."""

from __future__ import annotations

import base64
import binascii

import pyotp
from argon2 import extract_parameters
from argon2.low_level import Type


def compatible_argon2id_phc(value: str | None) -> bool:
    """Return true only for PHC strings the configured Argon2 verifier can parse."""
    if not value or not value.startswith("$argon2id$"):
        return False
    try:
        parameters = extract_parameters(value)
        return parameters.type is Type.ID and parameters.hash_len >= 16
    except Exception:
        return False


def compatible_totp_secret(value: str | None) -> bool:
    """Validate legacy TOTP as a base32 RFC 4648 secret and usable RFC 6238 code."""
    if not value:
        return False
    try:
        normalized = value.strip().replace(" ", "").upper()
        decoded = base64.b32decode(normalized + "=" * (-len(normalized) % 8), casefold=True)
        if len(decoded) < 10:
            return False
        return bool(pyotp.TOTP(normalized).now())
    except (ValueError, binascii.Error):
        return False
