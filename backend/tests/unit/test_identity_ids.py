from ima.application.identity import new_legacy_id


def test_new_identity_ids_match_legacy_opaque_id_contract() -> None:
    values = {new_legacy_id() for _ in range(100)}
    assert len(values) == 100
    assert all(1 <= len(value) <= 32 for value in values)
    assert all(value.isascii() for value in values)
    assert all(not value.startswith("{") for value in values)
