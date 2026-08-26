from pathlib import Path

from ima.application.search import fuse_scores


def test_search_sql_keeps_workspace_inside_fts_and_vector_predicates() -> None:
    source = Path("src/ima/application/search.py").read_text(encoding="utf-8")
    assert "c.workspace_id=:workspace AND d.workspace_id=:workspace" in source
    assert 'workspace_literal = workspace_id.replace("\'", "\'\'")' in source
    assert "WHERE workspace_id='{workspace_literal}' AND embedding_status='ready'" in source
    assert "pg_advisory_xact_lock(hashtextextended(:key, 0))" in source
    assert "INDEX_BUILD_IN_PROGRESS" in source


def test_search_index_name_includes_workspace_identity() -> None:
    source = Path("src/ima/application/search.py").read_text(encoding="utf-8")
    assert 'f"ix_cv_{sha256(workspace_id.encode()).hexdigest()[:8]}_"' in source


def test_fusion_normalizes_and_is_deterministic() -> None:
    first = ("a", 1, 1, 0, "a")
    second = ("b", 1, 1, 0, "b")
    scores = fuse_scores({first: 4.0, second: 2.0}, {second: 8.0}, 0.5)
    assert scores[first] == 0.5
    assert scores[second] == 0.75


def test_search_migration_has_workspace_identity_and_immutable_citations() -> None:
    source = Path("migrations/versions/20260826_0007_search_conversations.py").read_text(
        encoding="utf-8"
    )
    assert "ADD COLUMN IF NOT EXISTS workspace_id varchar(32)" in source
    assert (
        "FOREIGN KEY(workspace_id,document_id) REFERENCES ima.documents(workspace_id,id)" in source
    )
    assert "FOREIGN KEY(workspace_id,owner_user_id) REFERENCES ima.workspace_members" in source
    assert "trg_message_citation_immutable" in source
    assert "CREATE TEXT SEARCH CONFIGURATION ima.mixed (PARSER=zhparser)" in source
    assert "ADD MAPPING FOR e WITH english_stem" in source


def test_grounded_search_openapi_has_lifecycle_and_owner_mutations() -> None:
    from ima.api.app import create_app

    paths = create_app().openapi()["paths"]
    assert (
        paths["/api/v1/workspaces/{workspace_id}/search-indexes/build"]["post"]["operationId"]
        == "buildGroundedSearchIndex"
    )
    conversation = paths["/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}"]
    assert conversation["patch"]["operationId"] == "updateGroundedConversation"
    assert conversation["delete"]["operationId"] == "deleteGroundedConversation"
    assert (
        paths["/api/v1/workspaces/{workspace_id}/conversations/{conversation_id}/retry"]["post"][
            "operationId"
        ]
        == "retryGroundedConversation"
    )
    assert not any("/internal/" in path for path in paths)


def test_grounded_sse_framing_has_event_id_and_compact_payload() -> None:
    from ima.application.search import sse

    frame = sse("citations", 3, {"messageId": "message", "citations": []}).decode()
    assert frame == 'id: 3\nevent: citations\ndata: {"messageId":"message","citations":[]}\n\n'
