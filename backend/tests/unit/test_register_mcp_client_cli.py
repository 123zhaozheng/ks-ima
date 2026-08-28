"""Executable contracts for the administrative MCP client registration CLI."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError

import ima.cli as cli


class FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


def invoke(**overrides: object) -> None:
    values = {
        "client_id": "desktop-app",
        "client_name": "Desktop App",
        "client_type": "public",
        "app_type": "native",
        "auth_method": "none",
        "redirect_uris": ["http://127.0.0.1:8765/callback"],
        "operator_id": "super-1",
        **overrides,
    }
    cli._register_mcp_client_sync(**values)  # type: ignore[arg-type]


def install_registration(
    monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None
) -> tuple[FakeEngine, list[dict[str, object]]]:
    engine = FakeEngine()
    calls: list[dict[str, object]] = []
    settings = SimpleNamespace(mcp_resource_url="https://ima.example/mcp")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("ima.infrastructure.db.engine.create_engine", lambda _settings: engine)

    async def register_client(_self: object, **kwargs: object) -> UUID:
        calls.append(kwargs)
        if error:
            raise error
        return UUID("11111111-1111-1111-1111-111111111111")

    monkeypatch.setattr(
        "ima.infrastructure.oauth.McpOauthRepository.register_client", register_client
    )
    return engine, calls


def test_registration_runs_async_operation_disposes_engine_and_prints_safe_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, calls = install_registration(monkeypatch)
    invoke(redirect_uris=["http://localhost:8765/callback", "https://agent.example/cb"])
    assert engine.disposed is True
    assert calls[0]["created_by"] == "super-1"
    assert calls[0]["canonical_resource"] == "https://ima.example/mcp"
    assert calls[0]["redirect_uris"] == (
        "http://localhost:8765/callback",
        "https://agent.example/cb",
    )
    output = json.loads(capsys.readouterr().out)
    assert output["resource"] == "https://ima.example/mcp"
    assert "secret" not in json.dumps(output).lower()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"client_id": "Bad_ID"}, "lowercase alphanumeric"),
        ({"client_id": "bad-"}, "lowercase alphanumeric"),
        ({"client_name": "   "}, "must not be blank"),
        ({"operator_id": None}, "--operator-id is required"),
        ({"redirect_uris": []}, "at least one --redirect-uri"),
        ({"redirect_uris": ["https://user:pass@example.com/cb"]}, "HTTPS or loopback"),
        ({"redirect_uris": ["http://example.com/cb"]}, "HTTPS or loopback"),
        ({"redirect_uris": ["https://example.com/cb#fragment"]}, "HTTPS or loopback"),
        (
            {"redirect_uris": ["https://example.com/cb", "https://example.com/cb"]},
            "duplicate --redirect-uri",
        ),
    ],
)
def test_validation_fails_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, object],
    message: str,
) -> None:
    monkeypatch.setattr(
        cli,
        "get_settings",
        lambda: SimpleNamespace(mcp_resource_url="https://ima.example/mcp"),
    )
    with pytest.raises(SystemExit) as raised:
        invoke(**overrides)
    assert raised.value.code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "invalid_request"
    assert message in error["message"]


def test_duplicate_uses_sqlstate_and_always_disposes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    duplicate = IntegrityError("safe statement", {}, SimpleNamespace(sqlstate="23505"))
    engine, _ = install_registration(monkeypatch, error=duplicate)
    with pytest.raises(SystemExit) as raised:
        invoke()
    assert raised.value.code == 5
    assert engine.disposed is True
    assert json.loads(capsys.readouterr().err)["error"] == "duplicate_client_id"


def test_failures_are_redacted(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    engine, _ = install_registration(
        monkeypatch, error=RuntimeError("postgresql://user:password@private-db/app")
    )
    with pytest.raises(SystemExit) as raised:
        invoke()
    assert raised.value.code == 2 and engine.disposed is True
    stderr = capsys.readouterr().err
    assert json.loads(stderr) == {"error": "registration_failed", "message": "RuntimeError"}
    assert "password" not in stderr

    install_registration(monkeypatch, error=PermissionError("private role detail"))
    with pytest.raises(SystemExit) as forbidden:
        invoke()
    assert forbidden.value.code == 3
    assert json.loads(capsys.readouterr().err)["error"] == "operator_forbidden"


def test_parser_dispatches_registration_and_preserves_other_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[dict[str, object]] = []
    monkeypatch.setattr(
        cli, "_register_mcp_client_sync", lambda **kwargs: registered.append(kwargs)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ima",
            "register-mcp-client",
            "--client-id",
            "desktop-app",
            "--client-name",
            "Desktop",
            "--client-type",
            "public",
            "--app-type",
            "native",
            "--auth-method",
            "none",
            "--redirect-uri",
            "http://localhost:8765/callback",
            "--operator-id",
            "super-1",
        ],
    )
    cli.main()
    assert registered[0]["operator_id"] == "super-1"

    invoked: list[str] = []

    async def worker() -> None:
        invoked.append("worker")

    monkeypatch.setattr(cli, "_run_worker", worker)
    monkeypatch.setattr(cli, "get_settings", lambda: invoked.append("check-config"))
    monkeypatch.setattr(cli, "_check_worker", lambda: invoked.append("check-worker"))
    monkeypatch.setattr(cli, "_run_migrations", lambda: invoked.append("migrate"))
    monkeypatch.setattr(cli, "_bootstrap_admin", lambda: invoked.append("bootstrap-admin"))
    monkeypatch.setattr(
        cli, "_legacy_identity_report", lambda action: invoked.append(f"identity:{action}")
    )
    monkeypatch.setattr(
        cli,
        "_legacy_authorization_report",
        lambda action: invoked.append(f"authorization:{action}"),
    )
    monkeypatch.setattr(
        cli, "_rotate_model_secrets", lambda action: invoked.append(f"rotate:{action}")
    )
    monkeypatch.setattr(
        cli,
        "_legacy_model_governance_report",
        lambda action, mapping: invoked.append(f"model:{action}:{mapping}"),
    )
    monkeypatch.setattr(
        cli, "_legacy_knowledge_report", lambda action: invoked.append(f"knowledge:{action}")
    )
    monkeypatch.setattr(
        cli,
        "_legacy_mcp_inventory",
        lambda action, mapping, operator: invoked.append(
            f"inventory:{action}:{mapping}:{operator}"
        ),
    )
    commands = [
        (["worker"], "worker"),
        (["check-config"], "check-config"),
        (["check-worker"], "check-worker"),
        (["migrate"], "migrate"),
        (["bootstrap-admin"], "bootstrap-admin"),
        (["migrate-legacy-identity", "apply"], "identity:apply"),
        (["migrate-legacy-authorization", "verify"], "authorization:verify"),
        (["rotate-model-secrets", "report"], "rotate:report"),
        (["migrate-legacy-model-governance", "plan"], "model:plan:None"),
        (["migrate-legacy-knowledge", "apply"], "knowledge:apply"),
        (["inventory-legacy-mcp", "report"], "inventory:report:None:None"),
    ]
    for arguments, expected in commands:
        monkeypatch.setattr(sys, "argv", ["ima", *arguments])
        cli.main()
        assert invoked.pop() == expected
