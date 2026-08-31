"""Repository contracts for the post-deletion knowledge boundary."""

from pathlib import Path

ROOT = Path(__file__).parents[3]


def read_source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_knowledge_client_is_python_only_without_zero_or_bun_fallback() -> None:
    client = read_source("src/api/knowledge-client.ts")
    composable = read_source("src/composables/use-knowledge.ts")
    page = read_source("src/pages/KnowledgeBase.vue")

    assert "imaClient" in client
    assert "/api/v1/" in client
    assert "zero-session" not in client
    assert "knowledge-upload" not in client
    assert "src-server" not in client
    assert "zero-session" not in composable
    assert "knowledge-upload" not in composable
    assert "trash" not in client.casefold()
    assert not (ROOT / "src/layouts/TrashLayout.vue").exists()
    assert not (ROOT / "src/components/KnowledgeTrashList.vue").exists()
    assert page


def test_python_knowledge_router_is_the_only_knowledge_backend() -> None:
    router = read_source("backend/src/ima/api/v1/knowledge.py")
    app = read_source("backend/src/ima/api/app.py")

    assert "KnowledgeService" in router
    assert "src-server" not in router
    assert "zero" not in router.casefold()
    assert "knowledge_router" in app
    assert "api.include_router(knowledge_router)" in app


def test_legacy_bun_server_subtree_is_deleted() -> None:
    assert not (ROOT / "src-server").exists()
    for relative in (
        "src-server/kb/ops.ts",
        "src-server/kb.ts",
        "src-server/kb/ingest.ts",
        "src-server/kb/retrieve.ts",
        "src-server/s3.ts",
        "src-server/mcp.ts",
    ):
        assert not (ROOT / relative).exists(), relative


def test_checkpoint_history_tables_outlive_the_legacy_importers() -> None:
    knowledge = read_source("backend/migrations/versions/20260825_0005_knowledge_tree.py")
    governance = read_source("backend/migrations/versions/20260825_0004_model_governance.py")
    identity = read_source("backend/migrations/versions/20260824_0002_identity_platform.py")
    assert "legacy_knowledge_migration" in knowledge
    assert "legacy_model_governance_migration" in governance
    assert "legacy_identity_projection" in identity
