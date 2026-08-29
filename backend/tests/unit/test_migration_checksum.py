"""Tests for legacy blob checksum normalization (G1)."""

from __future__ import annotations

import base64

import pytest

from ima.application.migration_checksum import normalize_legacy_checksum

# sha256("abc") in both encodings the legacy and Python sides produce.
HEX_ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
BASE64_ABC = base64.b64encode(bytes.fromhex(HEX_ABC)).decode("ascii")


def test_base64_fixture_is_expected_encoding() -> None:
    assert BASE64_ABC == "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0="


def test_lowercase_hex_passes_through() -> None:
    assert normalize_legacy_checksum(HEX_ABC) == HEX_ABC


def test_uppercase_hex_is_lowered() -> None:
    assert normalize_legacy_checksum(HEX_ABC.upper()) == HEX_ABC


def test_base64_digest_normalizes_to_hex() -> None:
    assert normalize_legacy_checksum(BASE64_ABC) == HEX_ABC


def test_surrounding_whitespace_is_tolerated() -> None:
    assert normalize_legacy_checksum(f" {BASE64_ABC}\n") == HEX_ABC


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-checksum",
        HEX_ABC[:-1],
        HEX_ABC + "0",
        base64.b64encode(b"short").decode("ascii"),
        "ungWv48Bz+pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0",  # missing padding
        "ungWv48Bz-pBQUDeXa4iI7ADYaOWF3qctBD/YfIAFa0=",  # url-safe alphabet
        "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",
    ],
)
def test_unrecognized_formats_raise_value_error(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_legacy_checksum(value)
