"""Public target search, private conversation, and grounded Ask contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

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


class AskScope(ContractModel):
    """Optional retrieval scope for grounded Ask: one folder subtree or one document."""

    folder_id: str | None = Field(default=None, alias="folderId", max_length=32)
    document_id: UUID | None = Field(default=None, alias="documentId")

    @model_validator(mode="after")
    def _single_target(self) -> AskScope:
        if self.folder_id and self.document_id:
            raise ValueError("folderId and documentId are mutually exclusive")
        return self


class ConversationScope(ContractModel):
    """The scope pinned on a conversation; title is resolved at read time."""

    folder_id: str | None = Field(default=None, alias="folderId")
    document_id: UUID | None = Field(default=None, alias="documentId")
    title: str | None = None


class ConversationResponse(ContractModel):
    id: UUID
    kb_id: str = Field(alias="kbId")
    kb_name: str = Field(alias="kbName")
    title: str
    lifecycle: Literal["active", "archived"]
    version: int
    scope: ConversationScope | None = None
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
    # Agent tool calling is opt-in at the HTTP boundary so existing clients
    # retain the single-shot event sequence.
    agent: bool = False
    # Scope pins a new conversation; on follow-ups it must match the pinned one.
    scope: AskScope | None = None


class ConversationPatchRequest(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    archived: bool | None = None
    expected_version: int = Field(alias="expectedVersion", gt=0)


class ConversationRetryRequest(ContractModel):
    message_id: UUID = Field(alias="messageId")
    expected_version: int = Field(alias="expectedVersion", gt=0)
    agent: bool = False
    # Optional scope echo; the conversation's pinned scope stays authoritative.
    scope: AskScope | None = None


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
