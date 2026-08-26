from pathlib import Path


def test_target_search_remains_python_owned_and_legacy_chat_is_retained() -> None:
    root = Path(__file__).resolve().parents[3]
    search_source = (root / "backend/src/ima/application/search.py").read_text(encoding="utf-8")
    legacy_retrieval = root / "src-server/kb/retrieve.ts"
    legacy_chat = root / "src/views/ChatView.vue"
    assert "ima.document_chunks" in search_source
    assert "src-server" not in search_source
    assert "legacy" not in search_source.lower()
    assert legacy_retrieval.exists()
    assert legacy_chat.exists()


def test_caddy_routes_target_workspace_search_and_blocks_private_bridge() -> None:
    root = Path(__file__).resolve().parents[3]
    caddy = (root / "Caddyfile").read_text(encoding="utf-8")
    assert "/api/v1/workspaces/*" in caddy
    assert "/api/v1/internal/*" in caddy
    assert 'respond "Not Found" 404' in caddy
