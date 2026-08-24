"""Small, auditable primitives used by identity services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Final

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PASSWORD_HASHER: Final = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
PASSWORD_PARAMETER_VERSION: Final = "argon2id-v1-m65536-t3-p2"


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def new_secret(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(password)


def verify_password(phc_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(phc_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def password_needs_rehash(phc_hash: str) -> bool:
    return PASSWORD_HASHER.check_needs_rehash(phc_hash)


def digest(value: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), value.encode(), hashlib.sha256).hexdigest()


def digest_bytes(value: bytes, pepper: str) -> str:
    return hmac.new(pepper.encode(), value, hashlib.sha256).hexdigest()


def encrypt_secret(secret: str, key_material: str, aad: str) -> bytes:
    key = hashlib.sha256(key_material.encode()).digest()
    nonce = secrets.token_bytes(12)
    return nonce + AESGCM(key).encrypt(nonce, secret.encode(), aad.encode())


def decrypt_secret(payload: bytes, key_material: str, aad: str) -> str:
    key = hashlib.sha256(key_material.encode()).digest()
    nonce, ciphertext = payload[:12], payload[12:]
    return AESGCM(key).decrypt(nonce, ciphertext, aad.encode()).decode()


def generate_recovery_code() -> str:
    return secrets.token_hex(16).upper()


def safe_code(value: str) -> str:
    return "".join(value.split()).upper()


def encode_challenge(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")
