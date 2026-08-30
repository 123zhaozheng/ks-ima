"""Platform model-governance HTTP adapters and safe workspace projection."""

# ruff: noqa: E501

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from ima.api.v1.auth import Current, check_csrf, check_recent_auth
from ima.api.v1.model_governance_contracts import (
    Assignment,
    AssignmentList,
    AssignmentRequest,
    CapabilityProfile,
    GatewayCreateRequest,
    GatewayPatchRequest,
    GovernedModel,
    GovernedModelCreateRequest,
    GovernedModelList,
    GovernedModelPatchRequest,
    HealthRequest,
    ImpactResponse,
    ModelDiscoveryResponse,
    ModelGateway,
    ModelGatewayList,
    ProfileCloneRequest,
    ProfileCreateRequest,
    ProfileDiff,
    ProfileLifecycleRequest,
    ProfileList,
    ProfilePatchRequest,
    ProfileVersionList,
    SecretRotateRequest,
    VersionRequest,
    WorkspaceCapability,
)
from ima.application.model_governance import ModelGovernanceService
from ima.domain.model_governance import ModelGatewayInput, Workflow

router = APIRouter(prefix="/admin", tags=["model-governance"])
workspace_router = APIRouter(prefix="/workspaces", tags=["model-governance"])


def service(request: Request) -> ModelGovernanceService:
    return cast(ModelGovernanceService, request.app.state.model_governance_service)


async def require(
    request: Request, current: Current, *, mutate: bool
) -> tuple[dict[str, Any], Any]:
    session, user = current
    if mutate:
        check_recent_auth(request, session)
    capability = "model_governance_manage" if mutate else "model_governance_read"
    identity = cast(Any, request.app.state.identity_service)
    if not await identity.has_capability(user.id, capability):
        raise HTTPException(403, "You do not have permission for this action")
    if mutate:
        check_csrf(request, session)
    return session, user


@router.get("/model-gateways", response_model=ModelGatewayList, operation_id="listModelGateways")
async def list_gateways(request: Request, current: Current) -> dict[str, Any]:
    await require(request, current, mutate=False)
    include_sensitive = await cast(Any, request.app.state.identity_service).has_capability(
        current[1].id, "model_governance_manage"
    )
    return {"items": await service(request).list_gateways(include_sensitive=include_sensitive)}


@router.post("/model-gateways", response_model=ModelGateway, operation_id="createModelGateway")
async def create_gateway(
    payload: GatewayCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    gateway_data = payload.model_dump(by_alias=True, exclude={"secret"})
    return await service(request).create_gateway(
        actor.id,
        ModelGatewayInput.model_validate(gateway_data),
        payload.secret,
    )


@router.patch(
    "/model-gateways/{gateway_id}", response_model=ModelGateway, operation_id="updateModelGateway"
)
async def update_gateway(
    gateway_id: UUID, payload: GatewayPatchRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    values = payload.model_dump(exclude_unset=True, by_alias=False)
    expected = int(values.pop("expected_version"))
    return await service(request).update_gateway(actor.id, gateway_id, values, expected)


@router.delete("/model-gateways/{gateway_id}", status_code=204, operation_id="deleteModelGateway")
async def delete_gateway(gateway_id: UUID, request: Request, current: Current) -> None:
    _, actor = await require(request, current, mutate=True)
    await service(request).delete_gateway(actor.id, gateway_id)


@router.post(
    "/model-gateways/{gateway_id}/rotate-secret",
    response_model=ModelGateway,
    operation_id="rotateModelGatewaySecret",
)
async def rotate_gateway_secret(
    gateway_id: UUID, payload: SecretRotateRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).rotate_gateway_secret(
        actor.id, gateway_id, payload.secret, payload.expected_version
    )


@router.post(
    "/model-gateways/{gateway_id}/enable",
    response_model=ModelGateway,
    operation_id="enableModelGateway",
)
async def enable_gateway(
    gateway_id: UUID, request: Request, current: Current, payload: VersionRequest | None = None
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).set_gateway_enabled(
        actor.id, gateway_id, True, payload.expected_version if payload else None
    )


@router.post(
    "/model-gateways/{gateway_id}/disable",
    response_model=ModelGateway,
    operation_id="disableModelGateway",
)
async def disable_gateway(
    gateway_id: UUID, request: Request, current: Current, payload: VersionRequest | None = None
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).set_gateway_enabled(
        actor.id, gateway_id, False, payload.expected_version if payload else None
    )


@router.post(
    "/model-gateways/{gateway_id}/discover",
    response_model=ModelDiscoveryResponse,
    operation_id="discoverModelGateway",
)
async def discover_gateway(gateway_id: UUID, request: Request, current: Current) -> dict[str, Any]:
    await require(request, current, mutate=True)
    return {"names": await service(request).discover_gateway(gateway_id)}


@router.post(
    "/model-gateways/{gateway_id}/health",
    response_model=list[dict[str, Any]],
    operation_id="checkModelGatewayHealth",
)
async def check_gateway_health(
    gateway_id: UUID, payload: HealthRequest, request: Request, current: Current
) -> list[dict[str, Any]]:
    _, actor = await require(request, current, mutate=True)
    from ima.domain.model_governance import ModelCapability

    return await service(request).check_gateway_health(
        actor.id,
        gateway_id,
        ModelCapability(payload.capability) if payload.capability else None,
    )


@router.post(
    "/model-gateways/{gateway_id}/health/queue",
    response_model=dict[str, str],
    operation_id="queueModelGatewayHealth",
)
async def queue_gateway_health(
    gateway_id: UUID, payload: HealthRequest, request: Request, current: Current
) -> dict[str, str]:
    await require(request, current, mutate=True)
    await request.app.state.job_service.enqueue_model_health(gateway_id, payload.capability)
    return {"status": "queued"}


@router.get("/governed-models", response_model=GovernedModelList, operation_id="listGovernedModels")
async def list_models(request: Request, current: Current) -> dict[str, Any]:
    await require(request, current, mutate=False)
    include_sensitive = await cast(Any, request.app.state.identity_service).has_capability(
        current[1].id, "model_governance_manage"
    )
    return {"items": await service(request).list_models(include_sensitive=include_sensitive)}


@router.post("/governed-models", response_model=GovernedModel, operation_id="createGovernedModel")
async def create_model(
    payload: GovernedModelCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).create_model(
        actor.id,
        {
            "gateway_id": payload.gateway_id,
            "remote_name": payload.remote_name,
            "capability": payload.capability,
            "business_label": payload.business_label,
            "context_limit": payload.context_limit,
            "output_limit": payload.output_limit,
            "embedding_dimension": payload.embedding_dimension,
            "max_documents": payload.max_documents,
        },
    )


@router.patch(
    "/governed-models/{model_id}", response_model=GovernedModel, operation_id="updateGovernedModel"
)
async def update_model(
    model_id: UUID, payload: GovernedModelPatchRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    data = payload.model_dump(by_alias=False)
    expected = int(data.pop("expected_version"))
    return await service(request).update_model(actor.id, model_id, data, expected)


@router.delete("/governed-models/{model_id}", status_code=204, operation_id="deleteGovernedModel")
async def delete_model(model_id: UUID, request: Request, current: Current) -> None:
    _, actor = await require(request, current, mutate=True)
    await service(request).delete_model(actor.id, model_id)


@router.post(
    "/governed-models/{model_id}/validate",
    response_model=GovernedModel,
    operation_id="validateGovernedModel",
)
async def validate_model(
    model_id: UUID, request: Request, current: Current, payload: VersionRequest | None = None
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).validate_model(
        actor.id, model_id, payload.expected_version if payload else None
    )


@router.post(
    "/governed-models/{model_id}/enable",
    response_model=GovernedModel,
    operation_id="enableGovernedModel",
)
async def enable_model(
    model_id: UUID, request: Request, current: Current, payload: VersionRequest | None = None
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).set_model_enabled(
        actor.id, model_id, True, payload.expected_version if payload else None
    )


@router.post(
    "/governed-models/{model_id}/disable",
    response_model=GovernedModel,
    operation_id="disableGovernedModel",
)
async def disable_model(
    model_id: UUID, request: Request, current: Current, payload: VersionRequest | None = None
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).set_model_enabled(
        actor.id, model_id, False, payload.expected_version if payload else None
    )


@router.get(
    "/capability-profiles", response_model=ProfileList, operation_id="listCapabilityProfiles"
)
async def list_profiles(request: Request, current: Current) -> dict[str, Any]:
    await require(request, current, mutate=False)
    return {"items": await service(request).list_profiles()}


@router.post(
    "/capability-profiles", response_model=CapabilityProfile, operation_id="createCapabilityProfile"
)
async def create_profile(
    payload: ProfileCreateRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).create_profile(
        actor.id,
        Workflow(payload.workflow),
        payload.business_alias,
        payload.description,
        payload.config,
    )


@router.get(
    "/capability-profiles/{profile_id}/versions",
    response_model=ProfileVersionList,
    operation_id="listCapabilityProfileVersions",
)
async def profile_versions(profile_id: UUID, request: Request, current: Current) -> dict[str, Any]:
    await require(request, current, mutate=False)
    include = await cast(Any, request.app.state.identity_service).has_capability(
        current[1].id, "model_governance_manage"
    )
    return {
        "items": await service(request).list_profile_versions(profile_id, include_config=include)
    }


@router.patch(
    "/capability-profiles/{profile_id}/draft",
    response_model=dict,
    operation_id="patchCapabilityProfileDraft",
)
async def patch_profile(
    profile_id: UUID, payload: ProfilePatchRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).patch_profile_draft(
        actor.id, profile_id, payload.config, payload.expected_draft_version
    )


@router.post(
    "/capability-profiles/{profile_id}/clone",
    response_model=CapabilityProfile,
    operation_id="cloneCapabilityProfile",
)
async def clone_profile(
    profile_id: UUID, payload: ProfileCloneRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).clone_profile(
        actor.id, profile_id, payload.business_alias, payload.description
    )


@router.post(
    "/capability-profiles/{profile_id}/publish",
    response_model=dict,
    operation_id="publishCapabilityProfile",
)
async def publish_profile(
    profile_id: UUID, payload: ProfilePatchRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).publish_profile(
        actor.id, profile_id, payload.expected_draft_version
    )


@router.post(
    "/capability-profiles/{profile_id}/disable",
    status_code=204,
    operation_id="disableCapabilityProfile",
)
async def disable_profile(
    profile_id: UUID,
    request: Request,
    current: Current,
    payload: ProfileLifecycleRequest | None = None,
) -> None:
    _, actor = await require(request, current, mutate=True)
    await service(request).set_profile_disabled(
        actor.id, profile_id, True, payload.expected_version if payload else None
    )


@router.post(
    "/capability-profiles/{profile_id}/restore",
    status_code=204,
    operation_id="restoreCapabilityProfile",
)
async def restore_profile(
    profile_id: UUID,
    request: Request,
    current: Current,
    payload: ProfileLifecycleRequest | None = None,
) -> None:
    _, actor = await require(request, current, mutate=True)
    await service(request).set_profile_disabled(
        actor.id, profile_id, False, payload.expected_version if payload else None
    )


@router.post(
    "/capability-profiles/{profile_id}/validate",
    response_model=dict,
    operation_id="validateCapabilityProfile",
)
async def validate_profile(
    profile_id: UUID, request: Request, current: Current
) -> dict[str, object]:
    _, actor = await require(request, current, mutate=True)
    return await service(request).validate_profile(actor.id, profile_id)


@router.delete(
    "/capability-profiles/{profile_id}", status_code=204, operation_id="deleteCapabilityProfile"
)
async def delete_profile(profile_id: UUID, request: Request, current: Current) -> None:
    _, actor = await require(request, current, mutate=True)
    await service(request).delete_profile(actor.id, profile_id)


@router.get(
    "/capability-profiles/{profile_id}/diff",
    response_model=ProfileDiff,
    operation_id="diffCapabilityProfile",
)
async def profile_diff(
    profile_id: UUID, request: Request, current: Current, from_version: int, to_version: int
) -> dict[str, Any]:
    await require(request, current, mutate=False)
    return await service(request).profile_diff(profile_id, from_version, to_version)


@router.put(
    "/workspaces/{workspace_id}/profile-assignments/{workflow}",
    response_model=Assignment,
    operation_id="assignWorkspaceCapabilityProfile",
)
async def assign_profile(
    workspace_id: str, workflow: str, payload: AssignmentRequest, request: Request, current: Current
) -> dict[str, Any]:
    _, actor = await require(request, current, mutate=True)
    if payload.workflow != workflow:
        raise HTTPException(400, "Workflow path and request do not match")
    return await service(request).assign_profile(
        actor.id,
        workspace_id,
        Workflow(workflow),
        payload.profile_id,
        payload.profile_version,
        payload.expected_version,
    )


@router.delete(
    "/workspaces/{workspace_id}/profile-assignments/{workflow}",
    status_code=204,
    operation_id="removeWorkspaceCapabilityProfile",
)
async def remove_assignment(
    workspace_id: str,
    workflow: str,
    request: Request,
    current: Current,
    expected_version: int | None = None,
) -> None:
    _, actor = await require(request, current, mutate=True)
    await service(request).remove_assignment(
        actor.id, workspace_id, Workflow(workflow), expected_version
    )


@router.get(
    "/model-governance/impact",
    response_model=ImpactResponse,
    operation_id="getModelGovernanceImpact",
)
async def impact(model_id: UUID, request: Request, current: Current) -> dict[str, Any]:
    # Impact is a read-only dependency report.  Requiring mutation CSRF here
    # makes the browser's GET contract unusable and is unnecessary for a
    # report whose response contains only safe IDs/counts.
    await require(request, current, mutate=False)
    return await service(request).impact(model_id)


@router.get(
    "/workspaces/{workspace_id}/profile-assignments",
    response_model=AssignmentList,
    operation_id="listWorkspaceCapabilityAssignments",
)
async def assignments(workspace_id: str, request: Request, current: Current) -> dict[str, Any]:
    await require(request, current, mutate=False)
    async with service(request).engine.connect() as conn:
        from sqlalchemy import text

        rows = (
            (
                await conn.execute(
                    text(
                        "SELECT * FROM ima.workspace_profile_assignments WHERE workspace_id=:workspace ORDER BY workflow"
                    ),
                    {"workspace": workspace_id},
                )
            )
            .mappings()
            .all()
        )
    return {"items": [dict(row) for row in rows]}


@workspace_router.get(
    "/{workspace_id}/capabilities",
    response_model=tuple[WorkspaceCapability, ...],
    operation_id="listWorkspaceModelCapabilities",
)
async def workspace_capabilities(
    workspace_id: str, request: Request, current: Current
) -> list[dict[str, Any]]:
    return await service(request).workspace_capabilities(current[1].id, workspace_id)


__all__ = ["router", "workspace_router"]
