"""Versioned AES-GCM envelope encryption for model gateway credentials."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretEnvelopeError(ValueError):
    """A secret cannot safely be encrypted or decrypted."""


def _key(value: str) -> bytes:
    # Hashing normalizes operator supplied material to AES-256 while keeping
    # development settings deterministic and never persisting plaintext.
    return hashlib.sha256(value.encode()).digest()


@dataclass(frozen=True, slots=True)
class SecretEnvelope:
    key_version: str
    nonce: bytes
    ciphertext: bytes
    fingerprint: str


class SecretKeyRing:
    """Immutable key ring loaded once from validated settings."""

    def __init__(self, encoded: str, current_version: str, fingerprint_key: str) -> None:
        try:
            values = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise SecretEnvelopeError("model key ring is not valid JSON") from exc
        if not isinstance(values, dict) or not values:
            raise SecretEnvelopeError("model key ring must be a non-empty object")
        self._keys: Mapping[str, bytes] = {
            str(version): _key(str(material)) for version, material in values.items()
        }
        if current_version not in self._keys:
            raise SecretEnvelopeError("current model key version is missing")
        self.current_version = current_version
        self._fingerprint_key = fingerprint_key.encode()

    @property
    def versions(self) -> tuple[str, ...]:
        return tuple(sorted(self._keys))

    def fingerprint(self, plaintext: str) -> str:
        return hmac.new(self._fingerprint_key, plaintext.encode(), hashlib.sha256).hexdigest()[:24]

    def encrypt(self, plaintext: str, *, gateway_id: str, secret_id: str) -> SecretEnvelope:
        if not plaintext:
            raise SecretEnvelopeError("gateway secret cannot be empty")
        nonce = secrets.token_bytes(12)
        aad = f"model-gateway:{gateway_id}:{secret_id}".encode()
        ciphertext = AESGCM(self._keys[self.current_version]).encrypt(
            nonce, plaintext.encode(), aad
        )
        return SecretEnvelope(
            key_version=self.current_version,
            nonce=nonce,
            ciphertext=ciphertext,
            fingerprint=self.fingerprint(plaintext),
        )

    def decrypt(self, envelope: SecretEnvelope, *, gateway_id: str, secret_id: str) -> str:
        key = self._keys.get(envelope.key_version)
        if key is None:
            raise SecretEnvelopeError("model key version is unavailable")
        aad = f"model-gateway:{gateway_id}:{secret_id}".encode()
        try:
            value = AESGCM(key).decrypt(envelope.nonce, envelope.ciphertext, aad).decode()
        except (InvalidTag, UnicodeDecodeError, ValueError) as exc:
            raise SecretEnvelopeError("model secret integrity check failed") from exc
        if not hmac.compare_digest(self.fingerprint(value), envelope.fingerprint):
            raise SecretEnvelopeError("model secret fingerprint mismatch")
        return value

    def rotate(
        self, envelope: SecretEnvelope, *, gateway_id: str, secret_id: str
    ) -> SecretEnvelope:
        return self.encrypt(
            self.decrypt(envelope, gateway_id=gateway_id, secret_id=secret_id),
            gateway_id=gateway_id,
            secret_id=secret_id,
        )


def redact_model_secret(value: object) -> object:
    """Recursively redact secret-like fields for logs and audit metadata."""

    secret_words = (
        "key",
        "token",
        "secret",
        "password",
        "authorization",
        "credential",
        "ciphertext",
    )
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]"
            if any(word in str(k).casefold() for word in secret_words)
            else redact_model_secret(v)
            for k, v in value.items()
        }
    if isinstance(value, list | tuple | set):
        return [redact_model_secret(item) for item in value]
    return value


__all__ = ["SecretEnvelope", "SecretEnvelopeError", "SecretKeyRing", "redact_model_secret"]
