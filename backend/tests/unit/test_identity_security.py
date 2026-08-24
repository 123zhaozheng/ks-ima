from ima.infrastructure.auth.security import (
    decrypt_secret,
    digest,
    encrypt_secret,
    generate_recovery_code,
    hash_password,
    password_needs_rehash,
    safe_code,
    verify_password,
)


def test_argon2_password_round_trip_and_rehash_contract() -> None:
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
    assert verify_password(encoded, "correct horse battery staple")
    assert not verify_password(encoded, "wrong")
    assert password_needs_rehash(encoded) is False


def test_secret_envelope_and_peppered_digest() -> None:
    encrypted = encrypt_secret("JBSWY3DPEHPK3PXP", "deployment-key", "user-opaque-id")
    assert decrypt_secret(encrypted, "deployment-key", "user-opaque-id") == "JBSWY3DPEHPK3PXP"
    assert digest("token", "pepper") == digest("token", "pepper")
    assert digest("token", "pepper") != digest("token", "other")


def test_recovery_codes_are_normalized_and_high_entropy() -> None:
    code = generate_recovery_code()
    assert len(code) == 32
    assert safe_code(f" {code[:8]} {code[8:]} ") == code
