from datetime import UTC, datetime, timedelta

import pytest

from ima.application.legacy_mcp_inventory import LegacyConnector, safe_inventory


def test_inventory_is_complete_and_never_contains_key_material() -> None:
    now = datetime.now(UTC)
    values = (
        LegacyConnector("a", "read", None, None, None),
        LegacyConnector("b", "readwrite", "f1", now - timedelta(1), None),
    )
    report = safe_inventory(values, {"a": "reissued"})
    assert report["complete"] is True
    assert report["counts"] == {"reissued": 1, "revoked": 1, "pending": 0}
    text = str(report).lower()
    assert (
        "keyhash" not in text
        and "apikey" not in text
        and "secret" not in text.replace("secretvalues", "")
    )
    assert "workspace" not in text
    assert "active" not in text
    assert "lastused" not in text


def test_inventory_marks_unclassified_active_connector_pending() -> None:
    value = LegacyConnector("a", "read", None, None, None)
    report = safe_inventory((value,), {})
    assert report["complete"] is False
    assert report["counts"]["pending"] == 1


@pytest.mark.parametrize(
    ("values", "decisions", "message"),
    [
        (
            (
                LegacyConnector("a", "read", None, None, None),
                LegacyConnector("a", "read", None, None, None),
            ),
            {"a": "reissued"},
            "duplicate legacy connector ids",
        ),
        (
            (LegacyConnector("a", "read", None, None, None),),
            {"unknown": "revoked"},
            "unknown legacy connector ids",
        ),
    ],
)
def test_inventory_rejects_ambiguous_classification(
    values: tuple[LegacyConnector, ...], decisions: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        safe_inventory(values, decisions)


def test_inventory_rejects_reissued_decision_for_inactive_connector() -> None:
    value = LegacyConnector("a", "read", None, None, datetime.now(UTC))
    with pytest.raises(ValueError, match="inactive legacy connectors cannot be reissued"):
        safe_inventory((value,), {"a": "reissued"})
