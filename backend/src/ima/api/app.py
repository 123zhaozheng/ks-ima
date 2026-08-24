"""FastAPI application assembly."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from ima.api.dependencies import Engine
from ima.api.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from ima.api.internal.authorization_bridge import router as authorization_bridge_router
from ima.api.internal.session_bridge import router as bridge_router
from ima.api.middleware import BodyLimitMiddleware, CorrelationMiddleware, RequestTimingMiddleware
from ima.api.v1.account import router as account_router
from ima.api.v1.admin import router as admin_router
from ima.api.v1.auth import router as auth_router
from ima.api.v1.system import readiness
from ima.api.v1.system import router as system_router
from ima.api.v1.workspaces import admin_router as workspace_admin_router
from ima.api.v1.workspaces import invitation_router
from ima.api.v1.workspaces import router as workspace_router
from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.identity import IdentityError, IdentityService
from ima.config import Settings, get_settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.observability.logging import configure_logging
from ima.infrastructure.tasks.service import JobService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    configure_logging(app_settings.log_level)
    engine = create_engine(app_settings)
    service = JobService(app_settings, engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db_engine = engine
        app.state.settings = app_settings
        app.state.job_service = service
        app.state.identity_service = IdentityService(engine, app_settings)
        app.state.workspace_service = WorkspaceService(engine, app_settings)
        await service.start()
        try:
            yield
        finally:
            await service.stop()
            await engine.dispose()

    app = FastAPI(
        title="IMA API",
        version=app_settings.build_version,
        lifespan=lifespan,
        docs_url="/api/v1/system/docs" if app_settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/v1/system/openapi.json",
    )
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    async def identity_exception_handler(request: Request, exc: IdentityError) -> JSONResponse:
        from ima.api.errors import make_problem

        return make_problem(
            request,
            status=exc.status_code,
            title="Identity request failed",
            detail=exc.detail,
            code="IDENTITY_ERROR",
        )

    app.add_exception_handler(IdentityError, identity_exception_handler)  # type: ignore[arg-type]

    async def workspace_exception_handler(request: Request, exc: WorkspaceError) -> JSONResponse:
        from ima.api.errors import make_problem

        return make_problem(
            request,
            status=exc.status_code,
            title="Workspace request failed",
            detail=exc.detail,
            code=exc.code,
        )

    app.add_exception_handler(WorkspaceError, workspace_exception_handler)  # type: ignore[arg-type]
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    if app_settings.trusted_proxies:
        app.add_middleware(
            ProxyHeadersMiddleware,  # type: ignore[arg-type]
            trusted_hosts=list(app_settings.trusted_proxies),
        )
    app.add_middleware(BodyLimitMiddleware, max_bytes=app_settings.max_body_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(app_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "Idempotency-Key",
            "X-Correlation-ID",
            "X-CSRF-Token",
        ],
    )

    @app.get("/health/live", include_in_schema=False, operation_id="healthLive")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/health/ready", response_model=None, include_in_schema=False, operation_id="healthReady"
    )
    async def health_ready(request: Request, engine: Engine) -> object:
        return await readiness(request, engine)

    api = APIRouter(prefix="/api/v1")
    api.include_router(system_router)
    api.include_router(auth_router)
    api.include_router(admin_router)
    api.include_router(account_router)
    api.include_router(workspace_router)
    api.include_router(invitation_router)
    api.include_router(workspace_admin_router)
    # This router is intentionally excluded from the public Caddy matchers and
    # OpenAPI schema; Bun reaches it only on the private network.
    api.include_router(bridge_router)
    api.include_router(authorization_bridge_router)
    app.include_router(api)
    # Route dependencies must use the same immutable settings instance as the
    # application factory, including in contract tests and embedded deployments.
    app.dependency_overrides[get_settings] = lambda: app_settings
    return app
