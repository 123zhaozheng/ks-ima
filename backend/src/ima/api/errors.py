"""HTTP error mapping using RFC 9457 Problem Details."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ima.api.contracts import ProblemDetails, problem_payload
from ima.infrastructure.observability.telemetry import ensure_correlation_id

logger = logging.getLogger(__name__)


def make_problem(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str,
    code: str,
    errors: dict[str, list[str]] | None = None,
) -> JSONResponse:
    correlation = ensure_correlation_id(request.headers.get("X-Correlation-ID"))
    problem = ProblemDetails(
        title=title,
        status=status,
        detail=detail,
        instance=str(request.url),
        code=code,
        correlationId=correlation,
        errors=errors,
    )
    return JSONResponse(
        status_code=status,
        content=problem_payload(problem),
        media_type="application/problem+json",
        headers={"X-Correlation-ID": correlation},
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return make_problem(
        request,
        status=exc.status_code,
        title="Request failed",
        detail=detail if exc.status_code < 500 else "The request could not be completed",
        code=f"HTTP_{exc.status_code}",
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors: dict[str, list[str]] = {}
    for error in exc.errors():
        location = (
            ".".join(str(part) for part in error.get("loc", ()) if part != "body") or "request"
        )
        errors.setdefault(location, []).append(str(error.get("msg", "Invalid value")))
    return make_problem(
        request,
        status=422,
        title="Validation failed",
        detail="One or more request fields are invalid",
        code="VALIDATION_ERROR",
        errors=errors,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    correlation = ensure_correlation_id(request.headers.get("X-Correlation-ID"))
    logger.exception(
        "unhandled_request_error", extra={"correlation_id": correlation, "path": request.url.path}
    )
    return make_problem(
        request,
        status=500,
        title="Internal server error",
        detail="The request could not be completed",
        code="INTERNAL_ERROR",
    )
