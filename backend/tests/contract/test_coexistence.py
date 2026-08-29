import re
from pathlib import Path


def test_caddy_python_match_is_exact_and_legacy_chat_is_not_captured() -> None:
    caddy = (Path(__file__).parents[3] / "Caddyfile").read_text()
    assert caddy.count("path /health/*") == 2
    assert caddy.count("path /api/v1/system/*") == 2
    assert "/api/v1/chat/completions" not in caddy.split("@ima_system", 1)[0]
    assert "@api path /api/*" in caddy
    assert "reverse_proxy {$PYTHON_API_URL}" in caddy
    compose = (Path(__file__).parents[3] / "docker-compose.example.yml").read_text()
    assert "IMA_TRUSTED_PROXIES: ${IMA_TRUSTED_PROXIES:-172.16.0.0/12}" in compose
    assert (
        caddy.count(
            "@ima_workspace path /api/v1/workspaces /api/v1/workspaces/* "
            "/api/v1/workspace-invitations /api/v1/workspace-invitations/* "
            "/api/v1/folders/* /api/v1/documents/*"
        )
        == 2
    )
    assert caddy.count("@ima_storage path /api/v1/folders/*/files/upload-ticket ") == 2
    assert "/api/v1/documents/*/file/* /api/v1/documents/*/ingestion" in caddy
    assert "@ima_internal_forbidden path /api/v1/internal/*" in caddy
    assert caddy.count("@ima_mcp path /mcp /.well-known/oauth-protected-resource ") == 2
    assert "/api/mcp" not in "\n".join(
        line for line in caddy.splitlines() if line.strip().startswith("@ima_mcp path")
    )
    assert caddy.count("/.well-known/oauth-authorization-server /oauth/authorize ") == 2
    assert caddy.count("/oauth/token /oauth/revoke /api/v1/oauth/*") == 2
    for server in caddy.split(":808")[1:]:
        assert server.index("@ima_mcp") < server.index("@api path /api/*")
        assert server.index("@ima_internal_forbidden") < server.index("@api path /api/*")


def test_oauth_mcp_runbook_preserves_rollback_order_and_snapshot_boundary() -> None:
    root = Path(__file__).parents[3]
    runbook = (root / "docs/oauth-mcp-coexistence-runbook.md").read_text(encoding="utf-8")
    assert "only preferred resource and token audience" in runbook
    assert "inventory-legacy-mcp verify" in runbook
    assert runbook.index(
        "Confirm `/api/mcp` still reaches the retained Bun handler"
    ) < runbook.index("Disable or withdraw the canonical Python `/mcp` route")
    assert "database snapshot identifier and checksum" in runbook
    assert "restore the identified pre-cutover database snapshot" in runbook
    assert "do not claim Cursor, Claude Desktop" in runbook
    assert "bun run test:caddy-routing" in runbook
    assert "caddy:2.10.2-alpine" in runbook
    assert "does not deploy a rollback" in runbook
    drill = (root / "scripts/caddy-routing-drill.ts").read_text(encoding="utf-8")
    assert "caddy:2.10.2-alpine" in drill
    assert "pre_sunset_rollback" in drill
    assert "buildRollbackConfig" in drill
    assert "imageDigest" in drill and "caddyfileSha256" in drill


def test_legacy_cutover_runbook_pins_freeze_cutover_rollback_and_recovery_phases() -> None:
    root = Path(__file__).parents[3]
    runbook = (root / "docs/legacy-cutover-runbook.md").read_text(encoding="utf-8")
    for section in (
        "## Pre-Flight Gates",
        "## Write Freeze",
        "## Cutover Steps",
        "## Pre-Deletion Rollback",
        "## Post-Deletion Recovery",
        "## Evidence Checklist",
    ):
        assert section in runbook
    assert runbook.index("## Pre-Flight Gates") < runbook.index("## Write Freeze")
    assert runbook.index("## Write Freeze") < runbook.index("## Cutover Steps")
    assert runbook.index("## Cutover Steps") < runbook.index("## Pre-Deletion Rollback")
    assert runbook.index("## Pre-Deletion Rollback") < runbook.index("## Post-Deletion Recovery")
    # Freeze entry must precede any routing change, and exit must be part of
    # the pre-deletion rollback path.
    assert runbook.index("maintenance freeze enter") < runbook.index("Load the cutover JSON")
    assert runbook.index("maintenance freeze exit") < runbook.index("## Post-Deletion Recovery")
    for command in (
        "migrate-legacy report-all",
        "migrate-legacy blob-verify",
        "reconcile-report",
        "reingest enqueue",
        "reingest report",
        "conversations-archive",
        "bun run test:caddy-routing",
    ):
        assert command in runbook
    assert "counts_only_archive" in runbook
    assert "`cutover.json`" in runbook and "`rollback.json`" in runbook
    assert "never restore legacy sessions without Python" in runbook
    assert "code is not supported" in runbook
    assert "does not deploy a rollback" in runbook
    drill = (root / "scripts/caddy-routing-drill.ts").read_text(encoding="utf-8")
    assert "buildCutoverConfig" in drill and "buildRollbackConfig" in drill
    assert "'cutover'" in drill and "'pre_sunset_rollback'" in drill
    assert "410" in drill and "terminal" in drill


def test_new_oauth_implementation_never_mutates_legacy_connector() -> None:
    root = Path(__file__).parents[3]
    protected_sources = [
        *root.glob("backend/src/ima/**/*.py"),
        *root.glob("backend/migrations/versions/*.py"),
    ]
    sources = "\n".join(path.read_text(encoding="utf-8") for path in protected_sources).lower()
    legacy_write = re.compile(
        r"\b(?:insert\s+into|update|delete\s+from)\s+\"?public\"?\s*\.\s*\"?connector\"?\b"
    )
    assert legacy_write.search(sources) is None
    cli = (root / "backend/src/ima/cli.py").read_text(encoding="utf-8")
    assert "FROM public.connector" in cli
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "preferred protected resource is `https://your-host/mcp`" in readme
    assert '"url": "https://your-host/api/mcp"' in readme
