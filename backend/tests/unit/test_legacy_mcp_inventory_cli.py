from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import ima.cli as cli


class _SecretUrl:
    def get_secret_value(self) -> str:
        return "postgresql+psycopg://user:password@db/app"


class _Result:
    def __init__(
        self, *, rows: list[tuple[Any, ...]] | None = None, row: tuple[Any, ...] | None = None
    ) -> None:
        self.rows = rows or []
        self.row = row

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.row


class _Connection:
    def __init__(self, *, authorized: bool = True) -> None:
        self.authorized = authorized
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> _Result:
        self.calls.append((sql, params))
        if "FROM public.connector" in sql:
            return _Result(
                rows=[
                    (
                        "connector-1",
                        "read",
                        None,
                        None,
                        None,
                    )
                ]
            )
        if "platform_role_assignments" in sql:
            assert "operator.is_active=true" in sql
            assert "operator.disabled_at IS NULL" in sql
            return _Result(row=(self.authorized,))
        return _Result()


def _install_database(monkeypatch: pytest.MonkeyPatch, connection: _Connection) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: SimpleNamespace(database_url=_SecretUrl()))
    monkeypatch.setattr(cli.psycopg, "connect", lambda _conninfo: connection)


def test_mapping_rejects_duplicate_json_keys_with_machine_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"connector-1":"reissued","connector-1":"revoked"}', encoding="utf-8")

    with pytest.raises(SystemExit) as raised:
        cli._load_legacy_mcp_decisions(mapping)

    assert raised.value.code == 2
    assert json.loads(capsys.readouterr().err)["error"] == "invalid_mapping"


def test_verify_emits_report_before_incomplete_exit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install_database(monkeypatch, _Connection())

    with pytest.raises(SystemExit) as raised:
        cli._legacy_mcp_inventory("verify", None)

    assert raised.value.code == 4
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is False
    assert report["counts"]["pending"] == 1


def test_apply_requires_authorized_operator_and_audits_only_safe_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mapping = tmp_path / "mapping.json"
    mapping.write_text('{"connector-1":"reissued"}', encoding="utf-8")
    forbidden = _Connection(authorized=False)
    _install_database(monkeypatch, forbidden)
    with pytest.raises(SystemExit) as raised:
        cli._legacy_mcp_inventory("apply", mapping, "operator-1")
    assert raised.value.code == 3
    assert json.loads(capsys.readouterr().err)["error"] == "operator_forbidden"
    assert all("INSERT INTO ima.audit_events" not in sql for sql, _ in forbidden.calls)

    allowed = _Connection()
    _install_database(monkeypatch, allowed)
    cli._legacy_mcp_inventory("apply", mapping, "operator-1")
    report = json.loads(capsys.readouterr().out)
    assert report["complete"] is True
    audit = next(call for call in allowed.calls if "INSERT INTO ima.audit_events" in call[0])
    assert audit[1] is not None and audit[1][0] == "operator-1"
    serialized_metadata = str(audit[1][2]).lower()
    for forbidden_value in ("workspace", "name", "lastused", "keyhash", "apikey"):
        assert forbidden_value not in serialized_metadata
