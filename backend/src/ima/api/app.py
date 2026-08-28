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
from ima.api.oauth import admin_router as oauth_admin_router
from ima.api.oauth import public_router as oauth_public_router
from ima.api.v1.account import router as account_router
from ima.api.v1.admin import router as admin_router
from ima.api.v1.auth import router as auth_router
from ima.api.v1.knowledge import router as knowledge_router
from ima.api.v1.model_governance import (
    internal_router as model_governance_bridge_router,
)
from ima.api.v1.model_governance import (
    router as model_governance_router,
)
from ima.api.v1.model_governance import (
    workspace_router as model_workspace_router,
)
from ima.api.v1.search import router as search_router
from ima.api.v1.system import readiness
from ima.api.v1.system import router as system_router
from ima.api.v1.workspaces import admin_router as workspace_admin_router
from ima.api.v1.workspaces import invitation_router
from ima.api.v1.workspaces import router as workspace_router
from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.identity import IdentityError, IdentityService
from ima.application.knowledge import KnowledgeError, KnowledgeService
from ima.application.mcp import McpRuntime, McpTransport
from ima.application.model_governance import ModelGovernanceError, ModelGovernanceService
from ima.application.oauth import McpAuthorizationError, McpAuthorizationService
from ima.application.search import SearchError, SearchService
from ima.application.storage import StorageService
from ima.config import Settings, get_settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.oauth import McpOauthRepository
from ima.infrastructure.observability.logging import configure_logging
from ima.infrastructure.tasks.service import JobService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    configure_logging(app_settings.log_level)
    engine = create_engine(app_settings)
    service = JobService(app_settings, engine)
    mcp_runtime: dict[str, McpRuntime] = {}
    mcp_transport = McpTransport(lambda: mcp_runtime["value"], app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.db_engine = engine
        app.state.settings = app_settings
        app.state.job_service = service
        app.state.identity_service = IdentityService(engine, app_settings)
        app.state.workspace_service = WorkspaceService(engine, app_settings)
        app.state.mcp_oauth_repository = McpOauthRepository(engine, app_settings)
        app.state.mcp_authorization_service = McpAuthorizationService(
            app.state.mcp_oauth_repository,
            app.state.identity_service,
            app.state.workspace_service,
            app_settings,
        )
        app.state.model_governance_service = ModelGovernanceService(engine, app_settings)
        app.state.knowledge_service = KnowledgeService(engine, app.state.workspace_service)
        app.state.search_service = SearchService(
            engine, app.state.workspace_service, app.state.model_governance_service
        )
        app.state.storage_service = StorageService(
            app_settings, engine, app.state.workspace_service, service
        )
        mcp_runtime["value"] = McpRuntime(
            authorization=app.state.mcp_authorization_service,
            workspace=app.state.workspace_service,
            knowledge=app.state.knowledge_service,
            storage=app.state.storage_service,
            search=app.state.search_service,
        )
        service_started = False
        try:
            async with mcp_transport.sdk_app.router.lifespan_context(mcp_transport.sdk_app):
                await service.start()
                service_started = True
                yield
        finally:
            try:
                if service_started:
                    await service.stop()
            finally:
                mcp_runtime.clear()
                await engine.dispose()

    app = FastAPI(
        title="IMA API",
        version=app_settings.build_version,
        lifespan=lifespan,
        docs_url="/api/v1/system/docs" if app_settings.environment != "production" else None,
        redoc_url=None,
        openapi_url="/api/v1/system/openapi.json",
    )
    app.state.settings = app_settings
    app.state.mcp_runtime_box = mcp_runtime
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

    async def model_governance_exception_handler(
        request: Request, exc: ModelGovernanceError
    ) -> JSONResponse:
        from ima.api.errors import make_problem

        return make_problem(
            request,
            status=exc.status_code,
            title="Model governance request failed",
            detail=exc.detail,
            code=exc.code,
        )

    app.add_exception_handler(ModelGovernanceError, model_governance_exception_handler)  # type: ignore[arg-type]

    async def knowledge_exception_handler(request: Request, exc: KnowledgeError) -> JSONResponse:
        from ima.api.errors import make_problem

        return make_problem(
            request,
            status=exc.status_code,
            title="Knowledge request failed",
            detail=exc.detail,
            code=exc.code,
        )

    app.add_exception_handler(KnowledgeError, knowledge_exception_handler)  # type: ignore[arg-type]

    async def search_exception_handler(request: Request, exc: SearchError) -> JSONResponse:
        from ima.api.errors import make_problem

        return make_problem(
            request,
            status=exc.status_code,
            title="Search request failed",
            detail=exc.detail,
            code=exc.code,
        )

    app.add_exception_handler(SearchError, search_exception_handler)  # type: ignore[arg-type]

    async def mcp_authorization_exception_handler(
        request: Request, exc: McpAuthorizationError
    ) -> JSONResponse:
        from ima.api.errors import make_problem

        status = 429 if exc.reason == "rate_limited" else 403
        if exc.reason in {"invalid_principal", "invalid_credential"}:
            status = 404
        return make_problem(
            request,
            status=status,
            title="Service access request failed",
            detail=exc.detail,
            code=exc.reason.upper(),
        )

    app.add_exception_handler(McpAuthorizationError, mcp_authorization_exception_handler)  # type: ignore[arg-type]
    app.add_middleware(CorrelationMiddleware)
    app.add_middleware(RequestTimingMiddleware)
    if app_settings.trusted_proxies:
        app.add_middleware(
            ProxyHeadersMiddleware,
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
    api.include_router(model_governance_router)
    api.include_router(model_workspace_router)
    api.include_router(model_governance_bridge_router)
    api.include_router(knowledge_router)
    api.include_router(search_router)
    api.include_router(oauth_admin_router)
    app.include_router(api)
    app.include_router(oauth_public_router)
    app.mount("/", mcp_transport.app, name="mcp-transport")
    # Route dependencies must use the same immutable settings instance as the
    # application factory, including in contract tests and embedded deployments.
    app.dependency_overrides[get_settings] = lambda: app_settings
    return app
