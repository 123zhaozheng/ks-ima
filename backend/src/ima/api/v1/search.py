"""Knowledge-base target search and private grounded Ask routes."""

from __future__ import annotations

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Path, Query, Request
from fastapi.responses import StreamingResponse

from ima.api.v1.auth import Current, check_csrf
from ima.api.v1.search_contracts import (
    AskRequest,
    CitationResponse,
    ConversationDetail,
    ConversationPage,
    ConversationPatchRequest,
    ConversationResponse,
    ConversationRetryRequest,
    SearchResponse,
    VectorIndexResponse,
)
from ima.api.v1.search_contracts import (
    AskScope as AskScopeContract,
)
from ima.application.search import AskScope, SearchService

router = APIRouter(tags=["search"])


def service(request: Request) -> SearchService:
    return cast(SearchService, request.app.state.search_service)


def request_scope(scope: AskScopeContract | None) -> AskScope | None:
    if scope is None:
        return None
    return AskScope(folder_id=scope.folder_id, document_id=scope.document_id)


@router.get(
    "/knowledge-bases/{kb_id}/search",
    response_model=SearchResponse,
    operation_id="searchKnowledgeBase",
)
async def search(
    kb_id: str,
    request: Request,
    current: Current,
    query: Annotated[str, Query(min_length=1, max_length=4000)],
    mode: Annotated[str, Query(pattern="^(keyword|vector|hybrid)$")] = "keyword",
    top_k: Annotated[int, Query(alias="topK", ge=1, le=50)] = 8,
    threshold: Annotated[float, Query(ge=0, le=1)] = 0,
    folder_id: Annotated[str | None, Query(alias="folderId", max_length=32)] = None,
    document_id: Annotated[UUID | None, Query(alias="documentId")] = None,
) -> dict[str, object]:
    return await service(request).search(
        current[1].id,
        kb_id,
        query,
        mode=mode,
        top_k=top_k,
        threshold=threshold,
        folder_id=folder_id,
        document_id=document_id,
    )


@router.post(
    "/knowledge-bases/{kb_id}/search-indexes/build",
    response_model=VectorIndexResponse,
    operation_id="buildGroundedSearchIndex",
)
async def build_index(kb_id: str, request: Request, current: Current) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await service(request).build_vector_index(actor.id, kb_id)


@router.get(
    "/conversations",
    response_model=ConversationPage,
    operation_id="listGroundedConversations",
)
async def conversations(request: Request, current: Current) -> dict[str, object]:
    return {"items": await service(request).list_conversations(current[1].id)}


@router.get(
    "/knowledge-bases/{kb_id}/conversations/{conversation_id}",
    response_model=ConversationDetail,
    operation_id="getGroundedConversation",
)
async def conversation(
    kb_id: str, conversation_id: UUID, request: Request, current: Current
) -> dict[str, object]:
    return await service(request).get_conversation(current[1].id, kb_id, conversation_id)


@router.patch(
    "/knowledge-bases/{kb_id}/conversations/{conversation_id}",
    response_model=ConversationResponse,
    operation_id="updateGroundedConversation",
)
async def update_conversation(
    kb_id: str,
    conversation_id: UUID,
    payload: ConversationPatchRequest,
    request: Request,
    current: Current,
) -> dict[str, object]:
    session, actor = current
    check_csrf(request, session)
    return await service(request).update_conversation(
        actor.id,
        kb_id,
        conversation_id,
        payload.title,
        payload.archived,
        payload.expected_version,
    )


@router.delete(
    "/knowledge-bases/{kb_id}/conversations/{conversation_id}",
    status_code=204,
    operation_id="deleteGroundedConversation",
)
async def delete_conversation(
    kb_id: str,
    conversation_id: UUID,
    expected_version: Annotated[int, Query(alias="expectedVersion", ge=1)],
    request: Request,
    current: Current,
) -> None:
    session, actor = current
    check_csrf(request, session)
    await service(request).delete_conversation(actor.id, kb_id, conversation_id, expected_version)


@router.post(
    "/knowledge-bases/{kb_id}/conversations/{conversation_id}/retry",
    operation_id="retryGroundedConversation",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def retry_conversation(
    kb_id: str,
    conversation_id: UUID,
    payload: ConversationRetryRequest,
    request: Request,
    current: Current,
) -> StreamingResponse:
    session, actor = current
    check_csrf(request, session)
    stream = await service(request).retry(
        actor.id,
        kb_id,
        conversation_id,
        payload.message_id,
        payload.expected_version,
        request_scope(payload.scope),
        payload.agent,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/knowledge-bases/{kb_id}/ask",
    operation_id="streamGroundedAsk",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def ask(
    kb_id: str, payload: AskRequest, request: Request, current: Current
) -> StreamingResponse:
    session, actor = current
    check_csrf(request, session)
    stream = await service(request).ask(
        actor.id,
        kb_id,
        payload.question,
        payload.conversation_id,
        request_scope(payload.scope),
        payload.agent,
    )
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/knowledge-bases/{kb_id}/messages/{message_id}/citations/{ordinal}",
    response_model=CitationResponse,
    operation_id="resolveGroundedCitation",
)
async def citation(
    kb_id: str,
    message_id: UUID,
    ordinal: Annotated[int, Path(ge=1)],
    request: Request,
    current: Current,
) -> dict[str, object]:
    return await service(request).resolve_citation(current[1].id, kb_id, message_id, ordinal)
