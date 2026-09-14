import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ima.application.ask_tools import AskToolError, AskToolExecutor, AskToolResult
from ima.application.search import (
    MAX_AGENT_ROUNDS,
    MAX_CITATION_PENDING_CHARS,
    AskScope,
    SearchError,
    SearchService,
    _CitationStreamFilter,
)


class _StreamModel:
    def __init__(self, responses: list[list[bytes]]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def managed_chat_stream(
        self,
        _kb: str,
        _workflow: object,
        messages: list[dict[str, object]],
        **kwargs: object,
    ):
        self.calls.append({"messages": [dict(message) for message in messages], **kwargs})
        response = self.responses[min(len(self.calls) - 1, len(self.responses) - 1)]

        async def stream():
            for chunk in response:
                yield chunk

        return stream()


def _sse_data(value: dict[str, object]) -> bytes:
    return f"data: {json.dumps(value, separators=(',', ':'))}\n\n".encode()


def _tool_response() -> bytes:
    return _sse_data(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "search_knowledge",
                                    "arguments": '{"query":"policy"}',
                                },
                            }
                        ]
                    }
                }
            ]
        }
    )


def _content_response() -> bytes:
    return _sse_data({"choices": [{"delta": {"content": "Grounded [1]"}}]})


def _tool_calls_response(count: int) -> bytes:
    return _sse_data(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": index,
                                "id": f"call-{index}",
                                "type": "function",
                                "function": {
                                    "name": "search_knowledge",
                                    "arguments": '{"query":"policy"}',
                                },
                            }
                            for index in range(count)
                        ]
                    }
                }
            ]
        }
    )


def _event(frame: bytes) -> tuple[str, dict[str, object]]:
    lines = frame.decode().splitlines()
    return lines[1].split(": ", 1)[1], json.loads(lines[2][6:])


@pytest.mark.asyncio
async def test_agent_loop_accumulates_split_tool_arguments_and_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_frame = _tool_response()
    midpoint = tool_frame.index(b"policy")
    model = _StreamModel([[tool_frame[:midpoint], tool_frame[midpoint:]], [_content_response()]])
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = model
    service.kb_service = None
    service.knowledge_service = None
    citation = {
        "documentId": str(uuid4()),
        "documentVersion": 1,
        "fileGeneration": 1,
        "chunkOrdinal": 0,
        "chunkDigest": "digest",
        "quote": "Policy source",
        "score": 0.9,
        "rank": 1,
    }
    persisted = AsyncMock()
    service._final_authorize_citations = AsyncMock(return_value=[citation])
    service._persist_citations = persisted
    service._status = AsyncMock()
    service._complete = AsyncMock()

    async def execute(self: AskToolExecutor, *_args: object, **_kwargs: object) -> AskToolResult:
        self.citations.append(citation)
        return AskToolResult(value={"items": [citation]}, citations=(citation,), hit_count=1)

    monkeypatch.setattr(AskToolExecutor, "execute", execute)
    frames = [
        frame
        async for frame in service._agent_loop(
            "user-1",
            "kb-1",
            "follow up",
            None,
            uuid4(),
            [{"role": "user", "content": "previous"}],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [4],
        )
    ]

    events = [_event(frame) for frame in frames]
    assert [name for name, _ in events] == ["tool_call", "citations", "delta", "delta"]
    assert events[0][1]["arguments"] == {"query": "policy"}
    assert events[1][1]["citations"] == [citation]
    assert (
        "".join(payload["delta"] for name, payload in events if name == "delta") == "Grounded [1]"
    )
    assert model.calls[0]["tools"]
    first_messages = model.calls[0]["messages"]
    assert first_messages[-1] == {"role": "user", "content": "follow up"}
    assert any(message.get("content") == "previous" for message in first_messages)
    second_messages = model.calls[1]["messages"]
    assert second_messages[-1]["role"] == "tool"
    persisted.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_loop_stops_at_max_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    model = _StreamModel([[_tool_response()]])
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = model
    service.kb_service = None
    service.knowledge_service = None
    service._final_authorize_citations = AsyncMock(return_value=[])
    service._status = AsyncMock()
    service._complete = AsyncMock()

    async def execute(self: AskToolExecutor, *_args: object, **_kwargs: object) -> AskToolResult:
        return AskToolResult(value={"items": []})

    monkeypatch.setattr(AskToolExecutor, "execute", execute)
    frames = [
        frame
        async for frame in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [4],
        )
    ]
    events = [_event(frame) for frame in frames]
    assert events[-1][0] == "knowledge_gap"
    assert events[-1][1]["citations"] == []
    assert service._complete.await_args.args[1] == "knowledge_gap"
    assert len(model.calls) == MAX_AGENT_ROUNDS


@pytest.mark.asyncio
async def test_ask_tool_scope_cannot_be_replaced_by_model_argument() -> None:
    search = SimpleNamespace(engine=object(), search=AsyncMock())
    membership = SimpleNamespace(require_membership=AsyncMock())
    executor = AskToolExecutor(search, kb_service=membership)
    with pytest.raises(AskToolError) as exc:
        await executor.execute(
            "search_knowledge",
            {"query": "secret", "folderId": "other-folder"},
            actor="user-1",
            kb_id="kb-1",
            scope=AskScope(folder_id="pinned-folder"),
        )
    assert exc.value.code == "SCOPE_FORBIDDEN"
    search.search.assert_not_awaited()
    membership.require_membership.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_tool_denies_unknown_membership_role_before_search() -> None:
    search = SimpleNamespace(engine=object(), search=AsyncMock())
    membership = SimpleNamespace(require_membership=AsyncMock(return_value="retired-role"))
    executor = AskToolExecutor(search, kb_service=membership)

    with pytest.raises(AskToolError) as exc:
        await executor.execute(
            "search_knowledge",
            {"query": "secret"},
            actor="user-1",
            kb_id="kb-1",
            scope=None,
        )

    assert exc.value.code == "KB_NOT_FOUND"
    search.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_ask_tool_executor_propagates_system_search_failure() -> None:
    search = SimpleNamespace(
        engine=object(),
        search=AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    membership = SimpleNamespace(require_membership=AsyncMock(return_value="owner"))
    executor = AskToolExecutor(search, kb_service=membership)

    with pytest.raises(RuntimeError, match="database unavailable"):
        await executor.execute(
            "search_knowledge",
            {"query": "private"},
            actor="user-1",
            kb_id="kb-1",
            scope=None,
        )


@pytest.mark.asyncio
async def test_agent_loop_returns_error_for_system_tool_failure() -> None:
    model = _StreamModel([[_tool_response()]])
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = model
    service.kb_service = SimpleNamespace(require_membership=AsyncMock(return_value="owner"))
    service.knowledge_service = None
    service.search = AsyncMock(side_effect=RuntimeError("database unavailable"))
    service._final_authorize_citations = AsyncMock(return_value=[])
    service._status = AsyncMock()
    service._complete = AsyncMock()
    terminal = ["completed"]
    frames = [
        frame
        async for frame in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
            terminal,
        )
    ]

    events = [_event(frame) for frame in frames]
    assert events[-1][0] == "error"
    assert events[-1][1]["code"] == "TOOL_FAILED"
    assert "database unavailable" not in json.dumps(events[-1][1])
    assert service._complete.await_args.args[1] == "failed"
    assert terminal == ["failed"]


@pytest.mark.asyncio
async def test_agent_loop_rejects_citations_revoked_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = _StreamModel([[_tool_response()], [_content_response()]])
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = model
    service.kb_service = None
    service.knowledge_service = None
    service._final_authorize_citations = AsyncMock(return_value=[])
    service._persist_citations = AsyncMock()
    service._status = AsyncMock()
    service._complete = AsyncMock()
    citation = {
        "documentId": str(uuid4()),
        "documentVersion": 1,
        "fileGeneration": 1,
        "chunkOrdinal": 0,
        "chunkDigest": "digest",
        "quote": "Source",
        "score": 0.9,
        "rank": 1,
    }

    async def execute(self: AskToolExecutor, *_args: object, **_kwargs: object) -> AskToolResult:
        self.citations.append(citation)
        return AskToolResult(value={"items": [citation]}, citations=(citation,), hit_count=1)

    monkeypatch.setattr(AskToolExecutor, "execute", execute)
    with pytest.raises(SearchError, match="access was revoked") as exc:
        async for _ in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
        ):
            pass

    assert exc.value.code == "ACCESS_REVOKED"
    service._final_authorize_citations.assert_awaited_once()
    service._persist_citations.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_loop_closes_upstream_when_cancelled() -> None:
    started = asyncio.Event()
    never = asyncio.Event()

    class BlockingStream:
        closed = False

        def __aiter__(self) -> "BlockingStream":
            return self

        async def __anext__(self) -> bytes:
            started.set()
            await never.wait()
            raise StopAsyncIteration

        async def aclose(self) -> None:
            self.closed = True

    class BlockingModel:
        def __init__(self) -> None:
            self.stream = BlockingStream()

        def managed_chat_stream(self, *_args: object, **_kwargs: object) -> BlockingStream:
            return self.stream

    model = BlockingModel()
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = model
    service.kb_service = None
    service.knowledge_service = None

    async def consume() -> None:
        async for _ in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
        ):
            pass

    task = asyncio.create_task(consume())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert model.stream.closed


@pytest.mark.asyncio
async def test_agent_loop_returns_knowledge_gap_without_tool_evidence() -> None:
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = _StreamModel([[_content_response()]])
    service.kb_service = None
    service.knowledge_service = None
    service._final_authorize_citations = AsyncMock(return_value=[])
    service._persist_citations = AsyncMock()
    service._status = AsyncMock()
    service._complete = AsyncMock()

    frames = [
        frame
        async for frame in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
        )
    ]

    events = [_event(frame) for frame in frames]
    assert [name for name, _ in events] == ["knowledge_gap"]
    assert events[0][1]["citations"] == []
    service._final_authorize_citations.assert_awaited_once_with("user-1", "kb-1", None, [])
    service._persist_citations.assert_not_awaited()
    service._complete.assert_awaited_once()
    assert service._complete.await_args.args[1] == "knowledge_gap"


@pytest.mark.asyncio
async def test_agent_loop_emits_each_final_content_piece_after_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citation = {
        "documentId": str(uuid4()),
        "documentVersion": 1,
        "fileGeneration": 1,
        "chunkOrdinal": 0,
        "chunkDigest": "digest",
        "quote": "Policy source",
        "score": 0.9,
        "rank": 1,
    }
    final = [
        _sse_data({"choices": [{"delta": {"content": "First "}}]}),
        _sse_data({"choices": [{"delta": {"content": "second [1]"}}]}),
    ]
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = _StreamModel([[_tool_response()], final])
    service.kb_service = None
    service.knowledge_service = None
    service._final_authorize_citations = AsyncMock(return_value=[citation])
    service._persist_citations = AsyncMock()
    service._status = AsyncMock()
    service._complete = AsyncMock()

    async def execute(self: AskToolExecutor, *_args: object, **_kwargs: object) -> AskToolResult:
        self.citations.append(citation)
        return AskToolResult(value={"items": [citation]}, citations=(citation,), hit_count=1)

    monkeypatch.setattr(AskToolExecutor, "execute", execute)
    frames = [
        frame
        async for frame in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
        )
    ]
    events = [_event(frame) for frame in frames]
    assert [name for name, _ in events] == [
        "tool_call",
        "citations",
        "delta",
        "delta",
        "delta",
    ]
    assert "".join(payload["delta"] for name, payload in events if name == "delta") == (
        "First second [1]"
    )


@pytest.mark.asyncio
async def test_agent_loop_emits_first_delta_before_final_upstream_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    citation = {
        "documentId": str(uuid4()),
        "documentVersion": 1,
        "fileGeneration": 1,
        "chunkOrdinal": 0,
        "chunkDigest": "digest",
        "quote": "Policy source",
        "score": 0.9,
        "rank": 1,
    }
    release = asyncio.Event()
    first_delta = asyncio.Event()
    first_frame_ready_before_upstream_close = False

    class BlockingFinalStream:
        def __init__(self) -> None:
            self.sent_content = False
            self.closed = False

        def __aiter__(self) -> "BlockingFinalStream":
            return self

        async def __anext__(self) -> bytes:
            if not self.sent_content:
                self.sent_content = True
                return _content_response()
            await release.wait()
            raise StopAsyncIteration

        async def aclose(self) -> None:
            self.closed = True

    final_stream = BlockingFinalStream()

    class Model:
        def __init__(self) -> None:
            self.calls = 0

        def managed_chat_stream(self, *_args: object, **_kwargs: object):
            self.calls += 1
            if self.calls == 1:

                async def tool_stream():
                    yield _tool_response()

                return tool_stream()
            return final_stream

    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = Model()
    service.kb_service = None
    service.knowledge_service = None
    service._final_authorize_citations = AsyncMock(return_value=[citation])
    service._persist_citations = AsyncMock()
    service._status = AsyncMock()
    service._complete = AsyncMock()

    async def execute(self: AskToolExecutor, *_args: object, **_kwargs: object) -> AskToolResult:
        self.citations.append(citation)
        return AskToolResult(value={"items": [citation]}, citations=(citation,), hit_count=1)

    monkeypatch.setattr(AskToolExecutor, "execute", execute)
    frames: list[bytes] = []

    async def consume() -> None:
        nonlocal first_frame_ready_before_upstream_close
        async for frame in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
        ):
            frames.append(frame)
            if _event(frame)[0] == "delta":
                first_frame_ready_before_upstream_close = not release.is_set()
                first_delta.set()

    task = asyncio.create_task(consume())
    await asyncio.wait_for(first_delta.wait(), timeout=1)
    assert first_frame_ready_before_upstream_close is True
    assert final_stream.closed is False
    release.set()
    await task
    assert any(_event(frame)[0] == "delta" for frame in frames)


@pytest.mark.asyncio
async def test_agent_loop_rejects_too_many_tool_calls_before_execution() -> None:
    service = SearchService.__new__(SearchService)
    service.engine = object()
    service.models = _StreamModel([[_tool_calls_response(5)]])
    service.kb_service = None
    service.knowledge_service = None
    service._final_authorize_citations = AsyncMock(return_value=[])
    service._complete = AsyncMock()

    with pytest.raises(SearchError) as exc:
        async for _ in service._agent_loop(
            "user-1",
            "kb-1",
            "question",
            None,
            uuid4(),
            [],
            SimpleNamespace(context_limit=4096),
            {"conversationId": "conv", "messageId": "msg"},
            [1],
        ):
            pass
    assert exc.value.code == "AGENT_TOOL_LIMIT"


def test_agent_answer_keeps_only_citations_returned_by_tools() -> None:
    answer = SearchService._ground_answer("known [1] and invented [9]", [{"rank": 1}])

    assert answer == "known [1] and invented "


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("[１]", "[1]"),
        ("[[1]]", "[1]"),
        ("[1] (https://attacker.invalid)", "[1]"),
        ("&#91;1&#93;", "[1]"),
        (r"\[1\]", "[1]"),
        ("[９]", ""),
    ],
)
def test_agent_answer_uses_one_canonical_citation_rule(answer: str, expected: str) -> None:
    assert SearchService._ground_answer(answer, [{"rank": 1}]) == expected


def test_agent_citation_filter_buffers_markers_split_across_content_chunks() -> None:
    stream = _CitationStreamFilter([{"rank": 1}])

    assert stream.feed("prefix [") == "prefix "
    assert stream.feed("１") == ""
    assert stream.feed("] suffix [9") == "[1] suffix "
    assert stream.feed("]") == ""
    assert stream.feed("", final=True) == ""

    linked = _CitationStreamFilter([{"rank": 1}])
    assert linked.feed("[1] ") == ""
    assert linked.feed("(https://attacker.invalid) tail") == "[1] tail"


def test_agent_citation_filter_flushes_overlong_unclosed_marker() -> None:
    stream = _CitationStreamFilter([{"rank": 1}])
    body = "x" * (MAX_CITATION_PENDING_CHARS + 1000)

    assert stream.feed("[") == ""
    output = stream.feed(body)

    assert output == "[" + body
    assert len(stream.pending) <= MAX_CITATION_PENDING_CHARS
    assert stream.feed("", final=True) == ""


def test_agent_context_always_keeps_the_current_question() -> None:
    messages = [
        {"role": "system", "content": "instructions"},
        {"role": "user", "content": "current question"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1"}]},
        {"role": "tool", "tool_call_id": "call-1", "content": "x" * 5000},
    ]

    bounded = SearchService._bounded_agent_messages(messages, 1024)

    assert any(message.get("content") == "current question" for message in bounded)
    assert all(message.get("role") != "tool" for message in bounded)
    assert not any(message.get("tool_calls") for message in bounded)
