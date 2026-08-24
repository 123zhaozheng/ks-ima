"""Operational foundation endpoints."""

from __future__ import annotations

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ima.api.contracts import (
    BuildInfo,
    DependencyStatus,
    DiagnosticJob,
    DiagnosticJobRequest,
    ProblemDetails,
    ReadyInfo,
)
from ima.api.dependencies import Engine
from ima.config import Settings, get_settings
from ima.infrastructure.db.health import check_database
from ima.infrastructure.observability.telemetry import correlation_id
from ima.infrastructure.tasks.service import JobService

router = APIRouter(prefix="/system", tags=["system"])
SettingsDependency = Annotated[Settings, Depends(get_settings)]
PROBLEM_DETAILS_RESPONSE = {
    "model": ProblemDetails,
    "content": {"application/problem+json": {}},
}


@router.get(
    "/info",
    response_model=BuildInfo,
    responses={500: PROBLEM_DETAILS_RESPONSE},
    operation_id="getSystemInfo",
)
async def get_system_info(settings: SettingsDependency) -> BuildInfo:
    return BuildInfo(
        apiVersion="v1", version=settings.build_version, capabilities=("health", "diagnostic-jobs")
    )


@router.post(
    "/jobs/diagnostic",
    response_model=DiagnosticJob,
    status_code=status.HTTP_202_ACCEPTED,
    responses={404: PROBLEM_DETAILS_RESPONSE, 422: PROBLEM_DETAILS_RESPONSE},
    operation_id="enqueueDiagnosticJob",
)
async def enqueue_diagnostic_job(
    payload: DiagnosticJobRequest,
    request: Request,
    settings: SettingsDependency,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> DiagnosticJob:
    if not settings.diagnostic_jobs_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    key = idempotency_key or payload.idempotency_key
    job_service = cast(JobService, request.app.state.job_service)
    return await job_service.enqueue(key, payload.fail_once, correlation_id.get())


@router.get(
    "/jobs/{job_id}",
    response_model=DiagnosticJob,
    responses={404: PROBLEM_DETAILS_RESPONSE, 422: PROBLEM_DETAILS_RESPONSE},
    operation_id="getDiagnosticJob",
)
async def get_diagnostic_job(
    job_id: UUID, request: Request, settings: SettingsDependency
) -> DiagnosticJob:
    if not settings.diagnostic_jobs_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    return await cast(JobService, request.app.state.job_service).get(job_id)


async def readiness(request: Request, engine: Engine) -> ReadyInfo:
    settings: Settings = request.app.state.settings
    database_ok, database_detail = await check_database(engine, settings)
    worker_ok, worker_detail = await request.app.state.job_service.readiness()
    dependencies = (
        DependencyStatus(
            name="database", status="ok" if database_ok else "unavailable", detail=database_detail
        ),
        DependencyStatus(
            name="worker", status="ok" if worker_ok else "degraded", detail=worker_detail
        ),
    )
    overall: Literal["ok", "degraded", "unavailable"] = (
        "ok" if all(item.status == "ok" for item in dependencies) else "degraded"
    )
    return ReadyInfo(status=overall, dependencies=dependencies)
