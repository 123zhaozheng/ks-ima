"""Public generated-source contracts for central model governance."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field

from ima.api.v1.identity_contracts import IdentityModel

Capability = Literal["chat", "embedding", "rerank"]
Workflow = Literal["grounded_ask", "title_generation", "summarization", "embedding", "reranking"]
HealthState = Literal["unknown", "healthy", "degraded", "unavailable"]
AvailabilityState = Literal["available", "degraded", "unavailable"]
ProfileState = Literal["draft", "published", "disabled"]


class GatewayCreateRequest(IdentityModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(alias="baseUrl", min_length=8, max_length=2048)
    allowed_capabilities: tuple[Capability, ...] = Field(alias="allowedCapabilities", min_length=1)
    insecure_private: bool = Field(default=False, alias="insecurePrivate")
    allowed_hosts: tuple[str, ...] = Field(default=(), alias="allowedHosts", max_length=64)
    allowed_cidrs: tuple[str, ...] = Field(default=(), alias="allowedCidrs", max_length=64)
    custom_ca_ref: str | None = Field(default=None, alias="customCaRef", max_length=512)
    connect_timeout_ms: int = Field(default=5000, alias="connectTimeoutMs", ge=100, le=300000)
    read_timeout_ms: int = Field(default=30000, alias="readTimeoutMs", ge=100, le=300000)
    write_timeout_ms: int = Field(default=30000, alias="writeTimeoutMs", ge=100, le=300000)
    pool_timeout_ms: int = Field(default=5000, alias="poolTimeoutMs", ge=100, le=300000)
    max_response_bytes: int = Field(
        default=8 * 1024 * 1024, alias="maxResponseBytes", ge=1024, le=128 * 1024 * 1024
    )
    secret: str | None = Field(
        default=None,
        min_length=1,
        max_length=8192,
        json_schema_extra={"writeOnly": True},
    )


class GatewayPatchRequest(IdentityModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    base_url: str | None = Field(default=None, alias="baseUrl", min_length=8, max_length=2048)
    allowed_capabilities: tuple[Capability, ...] | None = Field(
        default=None, alias="allowedCapabilities", min_length=1
    )
    insecure_private: bool | None = Field(default=None, alias="insecurePrivate")
    allowed_hosts: tuple[str, ...] | None = Field(default=None, alias="allowedHosts", max_length=64)
    allowed_cidrs: tuple[str, ...] | None = Field(default=None, alias="allowedCidrs", max_length=64)
    custom_ca_ref: str | None = Field(default=None, alias="customCaRef", max_length=512)
    connect_timeout_ms: int | None = Field(
        default=None, alias="connectTimeoutMs", ge=100, le=300000
    )
    read_timeout_ms: int | None = Field(default=None, alias="readTimeoutMs", ge=100, le=300000)
    write_timeout_ms: int | None = Field(default=None, alias="writeTimeoutMs", ge=100, le=300000)
    pool_timeout_ms: int | None = Field(default=None, alias="poolTimeoutMs", ge=100, le=300000)
    max_response_bytes: int | None = Field(
        default=None, alias="maxResponseBytes", ge=1024, le=128 * 1024 * 1024
    )
    expected_version: int = Field(alias="expectedVersion", ge=1)


class SecretRotateRequest(IdentityModel):
    secret: str = Field(
        min_length=1,
        max_length=8192,
        json_schema_extra={"writeOnly": True},
    )
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class GatewayHealthDto(IdentityModel):
    capability: Capability
    state: HealthState
    reason_code: str | None = Field(default=None, alias="reasonCode")
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    checked_at: datetime | None = Field(default=None, alias="checkedAt")


class ModelGateway(IdentityModel):
    id: UUID
    name: str
    base_url: str | None = Field(default=None, alias="baseUrl")
    enabled: bool
    allowed_capabilities: tuple[Capability, ...] = Field(alias="allowedCapabilities")
    tls_mode: Literal["required", "private_http"] = Field(alias="tlsMode")
    insecure_private: bool = Field(alias="insecurePrivate")
    custom_ca_ref: str | None = Field(default=None, alias="customCaRef")
    version: int
    secret_present: bool = Field(alias="secretPresent")
    fingerprint: str | None = None
    health: tuple[GatewayHealthDto, ...] = ()
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ModelGatewayList(IdentityModel):
    items: tuple[ModelGateway, ...]


class ModelDiscoveryResponse(IdentityModel):
    names: tuple[str, ...]


class GovernedModelCreateRequest(IdentityModel):
    gateway_id: UUID = Field(alias="gatewayId")
    remote_name: str = Field(alias="remoteName", min_length=1, max_length=255)
    capability: Capability
    business_label: str = Field(alias="businessLabel", min_length=1, max_length=200)
    context_limit: int | None = Field(default=None, alias="contextLimit", ge=1, le=2097152)
    output_limit: int | None = Field(default=None, alias="outputLimit", ge=1, le=524288)
    embedding_dimension: int | None = Field(
        default=None, alias="embeddingDimension", ge=1, le=65536
    )
    max_documents: int | None = Field(default=None, alias="maxDocuments", ge=1, le=1000)


class GovernedModelPatchRequest(IdentityModel):
    business_label: str | None = Field(
        default=None, alias="businessLabel", min_length=1, max_length=200
    )
    context_limit: int | None = Field(default=None, alias="contextLimit", ge=1, le=2097152)
    output_limit: int | None = Field(default=None, alias="outputLimit", ge=1, le=524288)
    embedding_dimension: int | None = Field(
        default=None, alias="embeddingDimension", ge=1, le=65536
    )
    max_documents: int | None = Field(default=None, alias="maxDocuments", ge=1, le=1000)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class GovernedModel(IdentityModel):
    id: UUID
    gateway_id: UUID | None = Field(default=None, alias="gatewayId")
    remote_name: str | None = Field(default=None, alias="remoteName")
    capability: Capability
    business_label: str = Field(alias="businessLabel")
    enabled: bool
    validated: bool
    validation_digest: str | None = Field(default=None, alias="validationDigest")
    validated_at: datetime | None = Field(default=None, alias="validatedAt")
    context_limit: int | None = Field(default=None, alias="contextLimit")
    output_limit: int | None = Field(default=None, alias="outputLimit")
    embedding_dimension: int | None = Field(default=None, alias="embeddingDimension")
    max_documents: int | None = Field(default=None, alias="maxDocuments")
    version: int
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class GovernedModelList(IdentityModel):
    items: tuple[GovernedModel, ...]


class ProfileCreateRequest(IdentityModel):
    workflow: Workflow
    business_alias: str = Field(alias="businessAlias", min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=1000)
    config: dict[str, Any]


class ProfilePatchRequest(IdentityModel):
    config: dict[str, Any]
    expected_draft_version: int = Field(alias="expectedDraftVersion", ge=1)


class ProfileCloneRequest(IdentityModel):
    business_alias: str | None = Field(
        default=None, alias="businessAlias", min_length=1, max_length=200
    )
    description: str | None = Field(default=None, min_length=1, max_length=1000)


class ProfileLifecycleRequest(IdentityModel):
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=0)


class VersionRequest(IdentityModel):
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class CapabilityProfile(IdentityModel):
    id: UUID
    workflow: Workflow
    business_alias: str = Field(alias="businessAlias")
    description: str
    lifecycle: Literal["active", "disabled", "archived"]
    current_version: int = Field(alias="currentVersion")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class CapabilityProfileVersion(IdentityModel):
    profile_id: UUID = Field(alias="profileId")
    version: int
    state: ProfileState
    config: dict[str, Any] | None = None
    config_digest: str = Field(alias="configDigest")
    draft_version: int = Field(alias="draftVersion")
    published_at: datetime | None = Field(default=None, alias="publishedAt")
    disabled_at: datetime | None = Field(default=None, alias="disabledAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class ProfileList(IdentityModel):
    items: tuple[CapabilityProfile, ...]


class ProfileVersionList(IdentityModel):
    items: tuple[CapabilityProfileVersion, ...]


class ProfileDiff(IdentityModel):
    profile_id: UUID = Field(alias="profileId")
    from_version: int = Field(alias="fromVersion")
    to_version: int = Field(alias="toVersion")
    changed_fields: tuple[str, ...] = Field(alias="changedFields")


class AssignmentRequest(IdentityModel):
    workflow: Workflow
    profile_id: UUID = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion", ge=1)
    expected_version: int | None = Field(default=None, alias="expectedVersion", ge=1)


class Assignment(IdentityModel):
    workspace_id: str = Field(alias="workspaceId")
    workflow: Workflow
    profile_id: UUID = Field(alias="profileId")
    profile_version: int = Field(alias="profileVersion")
    version: int
    availability: AvailabilityState
    availability_reason: str | None = Field(default=None, alias="availabilityReason")
    assigned_at: datetime = Field(alias="assignedAt")


class AssignmentList(IdentityModel):
    items: tuple[Assignment, ...]


class WorkspaceCapability(IdentityModel):
    workflow: Workflow
    alias: str
    description: str
    version: int | None
    status: AvailabilityState
    reason: str | None = None


class ImpactItem(IdentityModel):
    workspace_id: str = Field(alias="workspaceId")
    workflow: Workflow
    current_model_id: UUID | None = Field(default=None, alias="currentModelId")
    current_dimension: int | None = Field(default=None, alias="currentDimension")
    affected_indexes: int = Field(alias="affectedIndexes")
    affected_source_ids: tuple[str, ...] = Field(alias="affectedSourceIds")


class ImpactResponse(IdentityModel):
    model_id: UUID = Field(alias="modelId")
    dimension: int | None
    affected: tuple[ImpactItem, ...]
    requires_reindex: bool = Field(alias="requiresReindex")


class GatewayResolveRequest(IdentityModel):
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=64)
    workflow: Workflow
    operation: Literal["chat", "embedding", "rerank"]


class GatewayResolveResponse(IdentityModel):
    source: Literal["target", "legacy", "denied"]
    workflow: Workflow
    profile_id: UUID | None = Field(default=None, alias="profileId")
    profile_version: int | None = Field(default=None, alias="profileVersion")
    binding_id: str | None = Field(default=None, alias="bindingId")
    reason: str | None = None


class ManagedChatRequest(IdentityModel):
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=64)
    workflow: Literal["grounded_ask", "title_generation", "summarization"]
    messages: tuple[dict[str, Any], ...] = Field(max_length=200)
    tools: tuple[dict[str, Any], ...] | None = Field(default=None, max_length=128)
    stream: bool = False


class ManagedEmbeddingRequest(IdentityModel):
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=64)
    inputs: tuple[str, ...] = Field(min_length=1, max_length=256)


class ManagedRerankRequest(IdentityModel):
    workspace_id: str = Field(alias="workspaceId", min_length=1, max_length=64)
    query: str = Field(min_length=1, max_length=10000)
    documents: tuple[str, ...] = Field(min_length=1, max_length=1000)


class HealthRequest(IdentityModel):
    capability: Capability | None = None


class ValidationResult(IdentityModel):
    ok: bool
    reason_code: str | None = Field(default=None, alias="reasonCode")
    latency_ms: int | None = Field(default=None, alias="latencyMs")


class AuditMetadata(IdentityModel):
    action: str
    target_id: str | None = Field(default=None, alias="targetId")
    result: str
    reason_code: str | None = Field(default=None, alias="reasonCode")
    created_at: datetime = Field(alias="createdAt")


__all__ = [name for name in globals() if not name.startswith("_")]
