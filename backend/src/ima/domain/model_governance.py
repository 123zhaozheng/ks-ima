"""Pure model-governance vocabulary and typed profile contracts.

This module has no database or HTTP dependency.  Keeping workflow validation
here means API, migration, resolver and tests cannot silently accept different
profile shapes.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal, cast
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ModelCapability(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"


class Workflow(StrEnum):
    GROUNDED_ASK = "grounded_ask"
    TITLE_GENERATION = "title_generation"
    SUMMARIZATION = "summarization"
    EMBEDDING = "embedding"
    RERANKING = "reranking"


class HealthState(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class Availability(StrEnum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class ProfileState(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class ModelGatewayInput(BaseModel):
    """Administrator supplied gateway metadata; credentials are separate."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(alias="baseUrl", min_length=8, max_length=2048)
    allowed_capabilities: frozenset[ModelCapability] = Field(
        alias="allowedCapabilities", min_length=1
    )
    insecure_private: bool = Field(default=False, alias="insecurePrivate")
    custom_ca_ref: str | None = Field(default=None, alias="customCaRef", max_length=512)
    allowed_hosts: tuple[str, ...] = Field(default=(), alias="allowedHosts", max_length=64)
    allowed_cidrs: tuple[str, ...] = Field(default=(), alias="allowedCidrs", max_length=64)
    connect_timeout_ms: int = Field(default=5000, alias="connectTimeoutMs", ge=100, le=300000)
    read_timeout_ms: int = Field(default=30000, alias="readTimeoutMs", ge=100, le=300000)
    write_timeout_ms: int = Field(default=30000, alias="writeTimeoutMs", ge=100, le=300000)
    pool_timeout_ms: int = Field(default=5000, alias="poolTimeoutMs", ge=100, le=300000)
    max_response_bytes: int = Field(
        default=8 * 1024 * 1024, alias="maxResponseBytes", ge=1024, le=128 * 1024 * 1024
    )

    @model_validator(mode="after")
    def validate_url_shape(self) -> ModelGatewayInput:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("baseUrl must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("baseUrl cannot contain credentials, query, or fragment")
        if ".." in parsed.path.split("/"):
            raise ValueError("baseUrl path must not contain '..' segments")
        if parsed.scheme == "https" and self.insecure_private:
            raise ValueError("insecurePrivate is only valid for HTTP gateways")
        if parsed.scheme == "http" and not self.insecure_private:
            raise ValueError("HTTP gateways require insecurePrivate")
        return self


class ChatModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    chat_model_id: str = Field(alias="chatModelId", min_length=1, max_length=64)
    system_prompt: str = Field(alias="systemPrompt", min_length=1, max_length=16000)
    context_limit: int = Field(alias="contextLimit", ge=128, le=2097152)
    output_limit: int = Field(alias="outputLimit", ge=1, le=524288)
    timeout_ms: int = Field(default=60000, alias="timeoutMs", ge=100, le=300000)
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=1, alias="topP", gt=0, le=1)


class GroundedAskConfig(ChatModelConfig):
    workflow: Literal[Workflow.GROUNDED_ASK] = Workflow.GROUNDED_ASK
    embedding_model_id: str | None = Field(default=None, alias="embeddingModelId", max_length=64)
    rerank_model_id: str | None = Field(default=None, alias="rerankModelId", max_length=64)
    retrieval_mode: Literal["hybrid", "keyword", "vector"] = Field(
        default="hybrid", alias="retrievalMode"
    )
    top_k: int = Field(default=8, alias="topK", ge=1, le=100)
    vector_weight: float = Field(default=0.7, alias="vectorWeight", ge=0, le=1)
    score_threshold: float = Field(default=0, alias="scoreThreshold", ge=0, le=1)
    max_context_chars: int = Field(default=24000, alias="maxContextChars", ge=1000, le=200000)
    generation_timeout_ms: int = Field(
        default=60000, alias="generationTimeoutMs", ge=100, le=300000
    )


class TitleGenerationConfig(ChatModelConfig):
    workflow: Literal[Workflow.TITLE_GENERATION] = Workflow.TITLE_GENERATION
    system_prompt: str = Field(
        default="Generate a concise title.", alias="systemPrompt", min_length=1, max_length=4000
    )


class SummarizationConfig(ChatModelConfig):
    workflow: Literal[Workflow.SUMMARIZATION] = Workflow.SUMMARIZATION
    system_prompt: str = Field(
        default="Summarize the supplied content.",
        alias="systemPrompt",
        min_length=1,
        max_length=4000,
    )
    max_context_chars: int = Field(default=30000, alias="maxContextChars", ge=1000, le=200000)


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    workflow: Literal[Workflow.EMBEDDING] = Workflow.EMBEDDING
    embedding_model_id: str = Field(alias="embeddingModelId", min_length=1, max_length=64)
    dimension: int = Field(ge=1, le=65536)
    batch_size: int = Field(default=32, alias="batchSize", ge=1, le=256)
    max_tokens: int = Field(default=8192, alias="maxTokens", ge=1, le=131072)
    timeout_ms: int = Field(default=30000, alias="timeoutMs", ge=100, le=300000)


class RerankingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    workflow: Literal[Workflow.RERANKING] = Workflow.RERANKING
    rerank_model_id: str = Field(alias="rerankModelId", min_length=1, max_length=64)
    max_documents: int = Field(default=50, alias="maxDocuments", ge=1, le=1000)
    result_limit: int = Field(default=10, alias="resultLimit", ge=1, le=1000)
    timeout_ms: int = Field(default=30000, alias="timeoutMs", ge=100, le=300000)


ProfileConfig = Annotated[
    GroundedAskConfig
    | TitleGenerationConfig
    | SummarizationConfig
    | EmbeddingConfig
    | RerankingConfig,
    Field(discriminator="workflow"),
]


def parse_profile_config(value: object, workflow: Workflow | str) -> BaseModel:
    """Validate a profile config against exactly one workflow."""

    target = Workflow(workflow)
    types: dict[Workflow, type[BaseModel]] = {
        Workflow.GROUNDED_ASK: GroundedAskConfig,
        Workflow.TITLE_GENERATION: TitleGenerationConfig,
        Workflow.SUMMARIZATION: SummarizationConfig,
        Workflow.EMBEDDING: EmbeddingConfig,
        Workflow.RERANKING: RerankingConfig,
    }
    data = dict(value) if isinstance(value, dict) else value
    if isinstance(data, dict):
        data.setdefault("workflow", target.value)
    return types[target].model_validate(data)


def canonical_config(config: BaseModel | dict[str, object]) -> dict[str, object]:
    model = (
        config
        if isinstance(config, BaseModel)
        else parse_profile_config(config, cast(str, config["workflow"]))
    )
    result = cast(
        dict[str, object],
        json.loads(
            json.dumps(
                model.model_dump(by_alias=True, exclude_none=True),
                ensure_ascii=True,
                sort_keys=True,
            )
        ),
    )

    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {str(key): normalize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value

    return cast(dict[str, object], normalize(result))


def config_digest(config: BaseModel | dict[str, object]) -> str:
    encoded = json.dumps(
        canonical_config(config), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def required_capabilities(
    workflow: Workflow | str, config: BaseModel | dict[str, object]
) -> tuple[ModelCapability, ...]:
    target = Workflow(workflow)
    if target in {Workflow.GROUNDED_ASK, Workflow.TITLE_GENERATION, Workflow.SUMMARIZATION}:
        values = [ModelCapability.CHAT]
        if target == Workflow.GROUNDED_ASK:
            parsed = parse_profile_config(config, target)
            if getattr(parsed, "embedding_model_id", None):
                values.append(ModelCapability.EMBEDDING)
            if getattr(parsed, "rerank_model_id", None):
                values.append(ModelCapability.RERANK)
        return tuple(values)
    return (ModelCapability.EMBEDDING if target == Workflow.EMBEDDING else ModelCapability.RERANK,)


class SafeSecret(BaseModel):
    secret_present: bool = Field(alias="secretPresent")
    fingerprint: str | None = None


class GatewayHealth(BaseModel):
    capability: ModelCapability
    state: HealthState
    reason_code: str | None = Field(default=None, alias="reasonCode")
    latency_ms: int | None = Field(default=None, alias="latencyMs")


class AvailabilityResult(BaseModel):
    workflow: Workflow
    alias: str
    description: str
    version: int | None
    status: Availability
    reason: str | None = None


__all__ = [
    "Availability",
    "AvailabilityResult",
    "EmbeddingConfig",
    "GatewayHealth",
    "GroundedAskConfig",
    "HealthState",
    "ModelCapability",
    "ModelGatewayInput",
    "ProfileConfig",
    "ProfileState",
    "RerankingConfig",
    "SafeSecret",
    "SummarizationConfig",
    "TitleGenerationConfig",
    "Workflow",
    "canonical_config",
    "config_digest",
    "parse_profile_config",
    "required_capabilities",
]
