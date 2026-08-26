"""Public target search, private conversation, and grounded Ask contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from ima.api.contracts import ContractModel


class SearchResult(ContractModel):
    document_id: UUID = Field(alias="documentId")
    document_version: int = Field(alias="documentVersion")
    file_generation: int | None = Field(alias="fileGeneration")
    chunk_ordinal: int = Field(alias="chunkOrdinal")
    chunk_digest: str = Field(alias="chunkDigest")
    title: str
    quote: str
    score: float
    rank: int


class SearchResponse(ContractModel):
    items: tuple[SearchResult, ...]
    degraded: str | None = None
    profile_top_k: int = Field(alias="profileTopK")


class ConversationResponse(ContractModel):
    id: UUID
    workspace_id: str = Field(alias="workspaceId")
    title: str
    lifecycle: Literal["active", "archived"]
    version: int
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class MessageResponse(ContractModel):
    id: UUID
    role: Literal["user", "assistant"]
    status: Literal["pending", "streaming", "completed", "knowledge_gap", "failed", "cancelled"]
    content: str
    sequence: int
    version: int
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    completed_at: datetime | None = Field(alias="completedAt")


class ConversationDetail(ConversationResponse):
    messages: tuple[MessageResponse, ...]


class ConversationPage(ContractModel):
    items: tuple[ConversationResponse, ...]


class AskRequest(ContractModel):
    question: str = Field(min_length=1, max_length=20000)
    conversation_id: UUID | None = Field(default=None, alias="conversationId")


class ConversationPatchRequest(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None
    expected_version: int = Field(alias="expectedVersion", gt=0)


class ConversationRetryRequest(ContractModel):
    message_id: UUID = Field(alias="messageId")
    expected_version: int = Field(alias="expectedVersion", gt=0)


class VectorIndexResponse(ContractModel):
    id: UUID
    model_id: UUID = Field(alias="modelId")
    model_version: int = Field(alias="modelVersion")
    dimension: int
    source_count: int = Field(alias="sourceCount")
    status: Literal["active"]


class CitationResponse(ContractModel):
    document_id: UUID = Field(alias="documentId")
    document_version: int = Field(alias="documentVersion")
    file_generation: int | None = Field(alias="fileGeneration")
    chunk_ordinal: int = Field(alias="chunkOrdinal")
    chunk_digest: str = Field(alias="chunkDigest")
    quote: str
    rank: int
    score: float
