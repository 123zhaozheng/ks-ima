import base64

from argon2 import PasswordHasher

from ima.application.legacy_identity import compatible_argon2id_phc, compatible_totp_secret


def test_legacy_argon2id_phc_format_is_verified_before_import() -> None:
    phc = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).hash("fixture-password")
    assert compatible_argon2id_phc(phc)
    assert not compatible_argon2id_phc("$2b$10$not-an-argon2-value")


def test_legacy_totp_requires_valid_base32_secret() -> None:
    secret = base64.b32encode(b"legacy-totp-secret").decode().rstrip("=")
    assert compatible_totp_secret(secret)
    assert not compatible_totp_secret("not a totp secret")
