"""Post-deletion search contract: Python owns retrieval; the legacy chat view is gone."""

from pathlib import Path


def test_search_is_python_owned_and_legacy_chat_is_removed() -> None:
    root = Path(__file__).resolve().parents[3]
    search_source = (root / "backend/src/ima/application/search.py").read_text(encoding="utf-8")
    assert "ima.document_chunks" in search_source
    assert "src-server" not in search_source
    assert "legacy" not in search_source.lower()
    # The Bun retrieval backend and the legacy chat view are deleted.
    assert not (root / "src-server").exists()
    assert not (root / "src/views/ChatView.vue").exists()


def test_caddy_routes_workspace_search_and_blocks_private_bridge() -> None:
    root = Path(__file__).resolve().parents[3]
    caddy = (root / "Caddyfile").read_text(encoding="utf-8")
    assert "/api/v1/workspaces/*" in caddy
    assert "@ima_internal_forbidden path /api/v1/internal/*" in caddy
    assert 'respond "Not Found" 404' in caddy
    assert 'respond "Gone" 410' in caddy
