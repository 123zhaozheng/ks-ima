import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ima.application.search import SearchError, SearchService, fuse_scores
from ima.domain.authorization import AclAction


class _Context:
    def __init__(self, value: object) -> None:
        self.value = value

    async def __aenter__(self) -> object:
        return self.value

    async def __aexit__(self, *_: object) -> None:
        return None


class _Connection:
    execute = AsyncMock()
    scalar = AsyncMock(return_value=1)


class _Engine:
    def __init__(self) -> None:
        self.connection = _Connection()

    def begin(self) -> _Context:
        return _Context(self.connection)

    def connect(self) -> _Context:
        return _Context(self.connection)


class _BoundedSearch(SearchService):
    def __init__(self) -> None:
        self.engine = cast(Any, _Engine())
        self.workspace = cast(Any, SimpleNamespace())
        self.models = SimpleNamespace(
            managed_chat=AsyncMock(
                return_value={"choices": [{"message": {"content": "Grounded answer"}}]}
            )
        )
        self.citation = {
            "documentId": uuid4(),
            "documentVersion": 1,
            "fileGeneration": 1,
            "chunkOrdinal": 0,
            "chunkDigest": "digest",
            "title": "Source",
            "quote": "Evidence",
            "score": 1.0,
            "rank": 1,
        }
        self.persisted = AsyncMock()
        self.statuses: list[tuple[str, str]] = []

    async def _folders(self, *_: object, **__: object) -> set[str]:
        return {"folder-1"}

    async def _owned_conversation(self, *_: object, **__: object) -> dict[str, object]:
        return {
            "id": uuid4(),
            "workspace_id": "workspace-1",
            "owner_user_id": "user-1",
            "title": "Existing",
            "lifecycle": "active",
            "version": 1,
            "created_at": None,
            "updated_at": None,
        }

    async def _profile(self, *_: object, **__: object) -> object:
        return SimpleNamespace(retrieval_mode="keyword", top_k=8)

    async def search(self, *_: object, **__: object) -> dict[str, object]:
        return {"items": [self.citation]}

    async def _persist_citations(self, message_id: object, citations: object) -> None:
        await self.persisted(message_id, citations)

    async def _status(self, message_id: object, status: str) -> None:
        self.statuses.append((str(message_id), status))

    async def _complete(self, message_id: object, status: str, content: str) -> None:
        self.statuses.append((status, content))


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


def test_ask_bounded_does_not_consume_browser_sse_or_legacy_model_paths() -> None:
    source = Path("src/ima/application/search.py").read_text(encoding="utf-8")
    bounded = source.split("async def ask_bounded", 1)[1].split("async def ask(", 1)[0]
    assert "managed_chat_stream" not in bounded
    assert "self.ask(" not in bounded
    assert "_legacy_model" not in bounded
    assert "managed_chat(" in bounded


@pytest.mark.asyncio
async def test_ask_bounded_uses_non_streaming_gateway_and_persists_citations() -> None:
    service = _BoundedSearch()
    search = AsyncMock(return_value={"items": [service.citation]})
    cast(Any, service).search = search
    result = await service.ask_bounded(
        "user-1", "workspace-1", "Question?", uuid4(), max_answer_chars=100
    )
    assert result.status == "completed"
    assert result.answer == "Grounded answer"
    assert result.citations == (service.citation,)
    service.persisted.assert_awaited_once()
    service.models.managed_chat.assert_awaited_once()
    messages = service.models.managed_chat.await_args.args[2]
    assert "Evidence" in messages[0]["content"]
    assert service.statuses[-1] == ("completed", "Grounded answer")
    assert search.await_count == 3
    assert all(call.kwargs["action"] is AclAction.ASK for call in search.await_args_list)


@pytest.mark.asyncio
async def test_ask_bounded_rejects_oversized_model_answer_and_marks_failed() -> None:
    service = _BoundedSearch()
    service.models.managed_chat.return_value = {"choices": [{"message": {"content": "x" * 101}}]}
    with pytest.raises(SearchError) as exc:
        await service.ask_bounded(
            "user-1", "workspace-1", "Question?", uuid4(), max_answer_chars=100
        )
    assert exc.value.code == "INVALID_MODEL_RESPONSE"
    assert service.statuses[-1] == ("failed", "")


@pytest.mark.asyncio
async def test_ask_bounded_empty_retrieval_never_calls_model() -> None:
    service = _BoundedSearch()
    cast(Any, service).search = AsyncMock(return_value={"items": []})
    result = await service.ask_bounded("user-1", "workspace-1", "Question?", uuid4())
    assert result.status == "knowledge_gap"
    assert result.citations == ()
    service.models.managed_chat.assert_not_awaited()
    service.persisted.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_bounded_final_recheck_cancels_revoked_sources() -> None:
    service = _BoundedSearch()
    cast(Any, service).search = AsyncMock(
        side_effect=(
            {"items": [service.citation]},
            {"items": [service.citation]},
            {"items": []},
        )
    )
    with pytest.raises(SearchError) as exc:
        await service.ask_bounded("user-1", "workspace-1", "Question?", uuid4())
    assert exc.value.code == "ACCESS_REVOKED"
    assert service.statuses[-1] == ("cancelled", "")


@pytest.mark.asyncio
async def test_ask_bounded_cancellation_persists_cancelled_state() -> None:
    service = _BoundedSearch()
    service.models.managed_chat.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.ask_bounded("user-1", "workspace-1", "Question?", uuid4())
    assert service.statuses[-1] == ("cancelled", "")
