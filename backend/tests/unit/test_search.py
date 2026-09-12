import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ima.application.search import AskScope, SearchError, SearchService, fuse_scores
from ima.domain.authorization import KbAction


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
        self.models = SimpleNamespace(
            managed_chat=AsyncMock(
                return_value={"choices": [{"message": {"content": "Grounded answer"}}]}
            )
        )
        self.citation = {
            # Search results serialize documentId as a string (SSE json.dumps).
            "documentId": str(uuid4()),
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

    async def _require_kb(self, *_: object, **__: object) -> str:
        return "Knowledge"

    async def _owned_conversation(self, *_: object, **__: object) -> dict[str, object]:
        return {
            "id": uuid4(),
            "kb_id": "kb-1",
            "kb_name": "Knowledge",
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


def test_search_sql_keeps_kb_inside_fts_and_vector_predicates() -> None:
    source = Path("src/ima/application/search.py").read_text(encoding="utf-8")
    assert "c.kb_id=:kb AND d.kb_id=:kb" in source
    assert 'kb_literal = kb_id.replace("\'", "\'\'")' in source
    assert "WHERE kb_id='{kb_literal}' AND embedding_status='ready'" in source
    assert "pg_advisory_xact_lock(hashtextextended(:key, 0))" in source
    assert "INDEX_BUILD_IN_PROGRESS" in source


def test_search_index_name_includes_kb_identity() -> None:
    source = Path("src/ima/application/search.py").read_text(encoding="utf-8")
    assert 'f"ix_cv_{sha256(kb_id.encode()).hexdigest()[:8]}_"' in source


def test_fusion_normalizes_and_is_deterministic() -> None:
    first = ("a", 1, 1, 0, "a")
    second = ("b", 1, 1, 0, "b")
    scores = fuse_scores({first: 4.0, second: 2.0}, {second: 8.0}, 0.5)
    assert scores[first] == 0.5
    assert scores[second] == 0.75


def test_search_migration_has_kb_identity_and_immutable_citations() -> None:
    source = Path("migrations/versions/20260826_0007_search_conversations.py").read_text(
        encoding="utf-8"
    )
    assert "ADD COLUMN IF NOT EXISTS kb_id varchar(32)" in source
    assert "FOREIGN KEY(kb_id,document_id) REFERENCES ima.documents(kb_id,id)" in source
    assert "FOREIGN KEY(kb_id,owner_user_id) REFERENCES ima.kb_members" in source
    assert "trg_message_citation_immutable" in source
    assert "CREATE TEXT SEARCH CONFIGURATION ima.mixed (PARSER=zhparser)" in source
    assert "ADD MAPPING FOR e WITH english_stem" in source


def test_grounded_search_openapi_has_lifecycle_and_owner_mutations() -> None:
    from ima.api.app import create_app

    paths = create_app().openapi()["paths"]
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/search-indexes/build"]["post"]["operationId"]
        == "buildGroundedSearchIndex"
    )
    conversation = paths["/api/v1/knowledge-bases/{kb_id}/conversations/{conversation_id}"]
    assert conversation["patch"]["operationId"] == "updateGroundedConversation"
    assert conversation["delete"]["operationId"] == "deleteGroundedConversation"
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/conversations/{conversation_id}/retry"]["post"][
            "operationId"
        ]
        == "retryGroundedConversation"
    )
    assert paths["/api/v1/conversations"]["get"]["operationId"] == "listGroundedConversations"
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
    result = await service.ask_bounded("user-1", "kb-1", "Question?", uuid4(), max_answer_chars=100)
    assert result.status == "completed"
    assert result.answer == "Grounded answer"
    assert result.citations == (service.citation,)
    service.persisted.assert_awaited_once()
    service.models.managed_chat.assert_awaited_once()
    messages = service.models.managed_chat.await_args.args[2]
    assert "Evidence" in messages[0]["content"]
    assert service.statuses[-1] == ("completed", "Grounded answer")
    assert search.await_count == 3
    assert all(call.kwargs["action"] is KbAction.ASK for call in search.await_args_list)


@pytest.mark.asyncio
async def test_ask_bounded_rejects_oversized_model_answer_and_marks_failed() -> None:
    service = _BoundedSearch()
    service.models.managed_chat.return_value = {"choices": [{"message": {"content": "x" * 101}}]}
    with pytest.raises(SearchError) as exc:
        await service.ask_bounded("user-1", "kb-1", "Question?", uuid4(), max_answer_chars=100)
    assert exc.value.code == "INVALID_MODEL_RESPONSE"
    assert service.statuses[-1] == ("failed", "")


@pytest.mark.asyncio
async def test_ask_bounded_empty_retrieval_never_calls_model() -> None:
    service = _BoundedSearch()
    cast(Any, service).search = AsyncMock(return_value={"items": []})
    result = await service.ask_bounded("user-1", "kb-1", "Question?", uuid4())
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
        await service.ask_bounded("user-1", "kb-1", "Question?", uuid4())
    assert exc.value.code == "ACCESS_REVOKED"
    assert service.statuses[-1] == ("cancelled", "")


@pytest.mark.asyncio
async def test_ask_bounded_cancellation_persists_cancelled_state() -> None:
    service = _BoundedSearch()
    service.models.managed_chat.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.ask_bounded("user-1", "kb-1", "Question?", uuid4())
    assert service.statuses[-1] == ("cancelled", "")


class _ScopedSearch(_BoundedSearch):
    """Ask flow with a pinned conversation scope and a scripted chat stream."""

    def __init__(self, persisted_scope: dict[str, object] | None = None) -> None:
        super().__init__()
        self.persisted_scope = persisted_scope

        async def _chat_stream(*_: object, **__: object) -> Any:
            yield b'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        self.models.managed_chat_stream = _chat_stream

    async def _owned_conversation(self, *_: object, **__: object) -> dict[str, object]:
        conversation = await super()._owned_conversation()
        conversation["scope"] = self.persisted_scope
        conversation["scope_title"] = "Folder A" if self.persisted_scope else None
        return conversation


def _event(frames: list[bytes], name: str) -> dict[str, Any] | None:
    for frame in frames:
        text = frame.decode()
        if f"event: {name}" in text:
            line = next(line for line in text.splitlines() if line.startswith("data: "))
            return cast(dict[str, Any], json.loads(line[6:]))
    return None


def test_ask_scope_contract_is_mutually_exclusive() -> None:
    from ima.api.v1.search_contracts import AskRequest, ConversationRetryRequest
    from ima.api.v1.search_contracts import AskScope as ScopeContract

    with pytest.raises(ValidationError):
        ScopeContract(folderId="folder-1", documentId=uuid4())
    assert ScopeContract(folderId="folder-1").document_id is None
    assert ScopeContract(documentId=uuid4()).folder_id is None
    assert AskRequest(question="q").scope is None
    scoped = ScopeContract(folderId="folder-1")
    assert AskRequest(question="q", scope=scoped).scope == scoped
    assert (
        ConversationRetryRequest(messageId=uuid4(), expectedVersion=1, scope=scoped).scope == scoped
    )
    assert ConversationRetryRequest(messageId=uuid4(), expectedVersion=1).scope is None


def test_conversation_scope_migration_persists_jsonb_with_exclusive_check() -> None:
    source = Path("migrations/versions/20260912_0014_ask_conversation_scope.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision = "20260910_0013"' in source
    assert "ADD COLUMN IF NOT EXISTS scope jsonb" in source
    assert "ck_conversations_scope" in source
    assert "jsonb_typeof(scope) = 'object'" in source
    assert "DROP CONSTRAINT IF EXISTS ck_conversations_scope" in source
    assert "DROP COLUMN IF EXISTS scope" in source


def test_search_sql_scopes_folder_subtree_and_document() -> None:
    source = Path("src/ima/application/search.py").read_text(encoding="utf-8")
    assert "SELECT descendant_id FROM ima.folder_closure" in source
    assert "ancestor_id=CAST(:folder AS varchar(32))" in source
    assert "c.document_id=CAST(:document AS uuid)" in source
    assert '"INVALID_SCOPE"' in source
    assert '"DOCUMENT_NOT_FOUND"' in source
    assert '"SCOPE_MISMATCH"' in source


@pytest.mark.asyncio
async def test_ask_follow_up_uses_persisted_scope_for_both_retrievals() -> None:
    service = _ScopedSearch({"folderId": "folder-1"})
    search = AsyncMock(return_value={"items": [service.citation]})
    cast(Any, service).search = search
    frames = [frame async for frame in await service.ask("user-1", "kb-1", "Question?", uuid4())]
    assert search.await_count == 2
    assert all(
        call.kwargs["folder_id"] == "folder-1" and call.kwargs["document_id"] is None
        for call in search.await_args_list
    )
    conversation = _event(frames, "conversation")
    assert conversation is not None
    assert conversation["conversation"]["scope"] == {"folderId": "folder-1", "title": "Folder A"}
    assert _event(frames, "completed") is not None


@pytest.mark.asyncio
async def test_ask_new_conversation_persists_scope_and_uses_scoped_gap_copy() -> None:
    service = _ScopedSearch()
    connection = cast(Any, service.engine).connection
    connection.execute.reset_mock()
    cast(Any, service)._resolve_scope_title = AsyncMock(return_value="Folder A")
    cast(Any, service).search = AsyncMock(return_value={"items": []})
    frames = [
        frame
        async for frame in await service.ask(
            "user-1", "kb-1", "Question?", None, AskScope(folder_id="folder-1")
        )
    ]
    inserts = [
        call
        for call in connection.execute.await_args_list
        if "INSERT INTO ima.conversations(" in str(call.args[0])
    ]
    assert len(inserts) == 1
    assert json.loads(inserts[0].args[1]["scope"]) == {"folderId": "folder-1"}
    conversation = _event(frames, "conversation")
    assert conversation is not None
    assert conversation["conversation"]["scope"] == {"folderId": "folder-1", "title": "Folder A"}
    gap = _event(frames, "knowledge_gap")
    assert gap is not None
    assert gap["answer"] == "该范围下未找到相关内容。"


@pytest.mark.asyncio
async def test_ask_without_scope_keeps_default_gap_copy_and_payload() -> None:
    service = _ScopedSearch()
    connection = cast(Any, service.engine).connection
    connection.execute.reset_mock()
    cast(Any, service).search = AsyncMock(return_value={"items": []})
    frames = [frame async for frame in await service.ask("user-1", "kb-1", "Question?", None)]
    inserts = [
        call
        for call in connection.execute.await_args_list
        if "INSERT INTO ima.conversations(" in str(call.args[0])
    ]
    assert len(inserts) == 1
    assert inserts[0].args[1]["scope"] is None
    conversation = _event(frames, "conversation")
    assert conversation is not None
    assert "scope" not in conversation["conversation"]
    gap = _event(frames, "knowledge_gap")
    assert gap is not None
    assert gap["answer"] == "I could not find relevant information in your accessible knowledge."


@pytest.mark.asyncio
async def test_ask_scope_mismatch_conflicts_before_writing_messages() -> None:
    service = _ScopedSearch({"folderId": "folder-1"})
    connection = cast(Any, service.engine).connection
    connection.execute.reset_mock()
    with pytest.raises(SearchError) as exc:
        await service.ask("user-1", "kb-1", "Question?", uuid4(), AskScope(folder_id="folder-2"))
    assert (exc.value.status_code, exc.value.code) == (409, "SCOPE_MISMATCH")
    assert not any(
        "INSERT INTO ima.conversation_messages" in str(call.args[0])
        for call in connection.execute.await_args_list
    )


@pytest.mark.asyncio
async def test_ask_rejects_a_missing_scope_target_without_partial_state() -> None:
    service = _ScopedSearch()
    connection = cast(Any, service.engine).connection
    connection.execute.reset_mock()
    cast(Any, service)._resolve_scope_title = AsyncMock(
        side_effect=SearchError(404, "FOLDER_NOT_FOUND", "Folder not found")
    )
    with pytest.raises(SearchError) as exc:
        await service.ask("user-1", "kb-1", "Question?", None, AskScope(folder_id="gone"))
    assert (exc.value.status_code, exc.value.code) == (404, "FOLDER_NOT_FOUND")
    assert not any(
        "INSERT INTO ima.conversations(" in str(call.args[0])
        or "INSERT INTO ima.conversation_messages" in str(call.args[0])
        for call in connection.execute.await_args_list
    )


@pytest.mark.asyncio
async def test_retry_forwards_scope_to_ask() -> None:
    service = _ScopedSearch({"folderId": "folder-1"})
    connection = cast(Any, service.engine).connection
    connection.execute = AsyncMock(
        return_value=SimpleNamespace(
            mappings=lambda: SimpleNamespace(first=lambda: {"content": "Question?", "version": 5})
        )
    )
    ask = AsyncMock(return_value=iter(()))
    cast(Any, service).ask = ask
    scope = AskScope(folder_id="folder-1")
    await service.retry("user-1", "kb-1", uuid4(), uuid4(), 5, scope)
    assert ask.await_args.kwargs["scope"] == scope
