"""Stable public API contract types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProblemDetails(ContractModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    code: str
    correlation_id: str = Field(alias="correlationId")
    errors: dict[str, list[str]] | None = None


class BuildInfo(ContractModel):
    version: str
    api_version: Literal["v1"] = Field(alias="apiVersion")
    capabilities: tuple[str, ...]


class DependencyStatus(ContractModel):
    name: str
    status: Literal["ok", "degraded", "unavailable"]
    detail: str | None = None


class ReadyInfo(ContractModel):
    status: Literal["ok", "degraded", "unavailable"]
    dependencies: tuple[DependencyStatus, ...]
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="checkedAt")


class DiagnosticJobRequest(ContractModel):
    idempotency_key: str = Field(min_length=1, max_length=128, alias="idempotencyKey")
    fail_once: bool = Field(default=False, alias="failOnce")


class DiagnosticJob(ContractModel):
    id: UUID
    status: Literal["queued", "running", "succeeded", "failed"]
    attempts: int
    correlation_id: str = Field(alias="correlationId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


T = TypeVar("T")


class SseEvent[T](ContractModel):
    id: str
    type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="occurredAt")
    data: T


def problem_payload(problem: ProblemDetails) -> dict[str, Any]:
    return problem.model_dump(by_alias=True, exclude_none=True)
