"""Repository contracts for the knowledge cutover and retained adapters."""

from pathlib import Path

ROOT = Path(__file__).parents[3]


def read_source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_migrated_knowledge_client_has_no_zero_or_bun_writer_fallback() -> None:
    client = read_source("src/api/knowledge-client.ts")
    composable = read_source("src/composables/use-knowledge.ts")
    layout = read_source("src/layouts/TrashLayout.vue")

    assert "imaClient" in client
    assert "/api/v1/" in client
    assert "zero-session" not in client
    assert "knowledge-upload" not in client
    assert "src-server" not in client
    assert "zero-session" not in composable
    assert "knowledge-upload" not in composable
    assert "KnowledgeTrashList.vue" in layout


def test_python_knowledge_router_does_not_import_legacy_mutators() -> None:
    router = read_source("backend/src/ima/api/v1/knowledge.py")
    app = read_source("backend/src/ima/api/app.py")

    assert "KnowledgeService" in router
    assert "src-server" not in router
    assert "zero" not in router.casefold()
    assert "knowledge_router" in app
    assert "api.include_router(knowledge_router)" in app


def test_later_child_adapters_remain_present_and_connected() -> None:
    retained = {
        "src-server/kb/ops.ts",
        "src-server/kb.ts",
        "src-server/kb/ingest.ts",
        "src-server/kb/retrieve.ts",
        "src-server/s3.ts",
        "src-server/mcp.ts",
    }
    for relative in retained:
        path = ROOT / relative
        assert path.is_file(), relative
        assert path.stat().st_size > 0, relative

    ops = read_source("src-server/kb/ops.ts")
    mcp = read_source("src-server/mcp.ts")
    assert "./ingest" in ops
    assert "./retrieve" in ops
    assert "../utils/s3" in ops
    assert "./kb/ops" in mcp


def test_legacy_zero_is_scoped_not_claimed_deleted() -> None:
    mixed_component = read_source("src/components/EntityList.vue")
    workspace_store = read_source("src/stores/workspace.ts")

    assert "zero-session" in mixed_component
    assert "zero" in workspace_store.casefold()
    assert (
        ROOT / ".trellis/tasks/08-24-knowledge-tree-vue-api/research/retained-legacy-symbols.md"
    ).is_file()
