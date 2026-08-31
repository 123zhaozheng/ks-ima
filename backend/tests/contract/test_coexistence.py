"""Post-deletion routing, runbook, and data-boundary contracts.

Re-scoped from the coexistence contract after the legacy deletion release:
Python is the only backend, the edge answers 410/404 for retired legacy
resources, and the runbooks carry sunset-closure annotations.
"""

import re
from pathlib import Path


def test_caddy_terminal_matrix_routes_python_and_terminates_legacy() -> None:
    caddy = (Path(__file__).parents[3] / "Caddyfile").read_text()
    # Python-owned prefixes are present on both listeners.
    assert caddy.count("path /health/*") == 2
    assert caddy.count("path /api/v1/system/*") == 2
    assert caddy.count("@ima_mcp path /mcp /.well-known/oauth-protected-resource ") == 2
    assert (
        caddy.count(
            "@ima_kb path /api/v1/knowledge-bases /api/v1/knowledge-bases/* "
            "/api/v1/kb-share-links /api/v1/kb-share-links/* "
            "/api/v1/folders/* /api/v1/documents/*"
        )
        == 2
    )
    assert caddy.count("@ima_storage path /api/v1/folders/*/files/upload-ticket ") == 2
    assert "reverse_proxy {$PYTHON_API_URL}" in caddy
    # The retired private bridge space keeps answering a public 404.
    assert "@ima_internal_forbidden path /api/v1/internal/*" in caddy
    # Retired legacy resources answer Gone; residual /api/* answers 404.
    assert (
        "@api_gone path /api/mcp /api/mcp/* /api/kb /api/kb/* /api/s3 /api/s3/* "
        "/api/search /api/search/* /api/v1/chat /api/v1/chat/* "
        "/api/connectors /api/connectors/*" in caddy
    )
    assert caddy.count('respond "Gone" 410') == 2
    assert "@api path /api/*" in caddy
    assert caddy.count('respond "Not Found" 404') == 4
    # No legacy upstream remains: every proxy target is the Python API.
    assert caddy.count("reverse_proxy") == caddy.count("reverse_proxy {$PYTHON_API_URL}")
    compose = (Path(__file__).parents[3] / "docker-compose.example.yml").read_text()
    assert "IMA_TRUSTED_PROXIES: ${IMA_TRUSTED_PROXIES:-172.16.0.0/12}" in compose
    for server in caddy.split(":808")[1:]:
        assert server.index("@ima_mcp") < server.index("@api_gone")
        assert server.index("@ima_internal_forbidden") < server.index("@api path /api/*")
        assert server.index("@api_gone") < server.index("@api path /api/*")


def test_routing_drill_pins_terminal_matrix_with_image_evidence() -> None:
    drill = (Path(__file__).parents[3] / "scripts/caddy-routing-drill.ts").read_text(
        encoding="utf-8"
    )
    assert "caddy:2.10.2-alpine" in drill
    assert "phase: 'terminal'" in drill
    assert "'/api/v1/internal/session/introspect'" in drill
    assert "'/api/mcp'" in drill
    assert "imageDigest" in drill and "caddyfileSha256" in drill
    # The cutover-window derivation configs are retired with the legacy edge.
    assert "buildCutoverConfig" not in drill
    assert "buildRollbackConfig" not in drill
    assert "pre_sunset_rollback" not in drill


def test_runbooks_record_sunset_closure_over_historical_phases() -> None:
    root = Path(__file__).parents[3]
    cutover = (root / "docs/legacy-cutover-runbook.md").read_text(encoding="utf-8")
    oauth = (root / "docs/oauth-mcp-coexistence-runbook.md").read_text(encoding="utf-8")
    # The historical phase structure remains as cutover-window evidence.
    for section in (
        "## Pre-Flight Gates",
        "## Write Freeze",
        "## Cutover Steps",
        "## Pre-Deletion Rollback",
        "## Post-Deletion Recovery",
        "## Evidence Checklist",
    ):
        assert section in cutover
    assert runbook_order(cutover)
    # Sunset closure annotations are present in both runbooks.
    assert "## Sunset Closure" in cutover
    assert "## Sunset Closure" in oauth
    assert "legacy deletion release is complete" in cutover
    assert "legacy deletion release is complete" in oauth
    assert "20260829_0011" in cutover
    assert "snapshot restore" in cutover
    assert "terminal matrix" in oauth
    assert "bun run test:caddy-routing" in cutover
    assert "caddy:2.10.2-alpine" in cutover


def runbook_order(runbook: str) -> bool:
    return (
        runbook.index("## Pre-Flight Gates") < runbook.index("## Write Freeze")
        and runbook.index("## Write Freeze") < runbook.index("## Cutover Steps")
        and runbook.index("## Cutover Steps") < runbook.index("## Pre-Deletion Rollback")
        and runbook.index("## Pre-Deletion Rollback") < runbook.index("## Post-Deletion Recovery")
    )


def test_python_is_the_only_backend_and_readme_points_at_canonical_mcp() -> None:
    root = Path(__file__).parents[3]
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in root.glob("backend/src/ima/**/*.py")
    )
    legacy_write = re.compile(
        r"\b(?:insert\s+into|update|delete\s+from)\s+\"?public\"?\s*\.", re.IGNORECASE
    )
    assert legacy_write.search(sources) is None
    assert not (root / "src-server").exists()
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "preferred protected resource is `https://your-host/mcp`" in readme
    assert '"url": "https://your-host/api/mcp"' not in readme
