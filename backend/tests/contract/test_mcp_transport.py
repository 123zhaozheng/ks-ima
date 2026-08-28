"""Official SDK interoperability and target-service tracing for MCP transport."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

import ima.api.app as app_module
from ima.application.mcp import AuthenticatedMcpApp, McpRuntime, McpTransport, _current_actor
from ima.application.mcp_contracts import KNOWN_TOOLS, McpActor
from ima.application.oauth import McpAuthorizationError
from ima.application.search import BoundedAskResult
from ima.config import Settings


def runtime_for(scopes: tuple[str, ...]) -> tuple[McpRuntime, object]:
    actor = McpActor(
        actor_type="human",
        user_id="user-1",
        workspace_id="workspace-1",
        scopes=scopes,
        correlationId="corr-1",
    )

    async def authorize_tool(call_actor: McpActor, tool_name: str, **_: object) -> None:
        required = KNOWN_TOOLS.get(tool_name)
        if required is None or required not in call_actor.scopes:
            raise McpAuthorizationError("insufficient_scope", "Tool scope is not granted")

    authorization = SimpleNamespace(
        authenticate_bearer=AsyncMock(return_value=actor),
        authorize_tool=AsyncMock(side_effect=authorize_tool),
        acquire_tool_lease=AsyncMock(return_value=UUID("00000000-0000-0000-0000-000000000099")),
        release_tool_lease=AsyncMock(),
        repository=SimpleNamespace(append_audit=AsyncMock()),
    )
    workspace = SimpleNamespace(
        list_workspaces=AsyncMock(
            return_value=[
                {"id": "workspace-1", "name": "Allowed"},
                {"id": "workspace-2", "name": "Hidden"},
            ]
        ),
        create_folder=AsyncMock(),
        folder=AsyncMock(),
        breadcrumbs=AsyncMock(),
        folders=AsyncMock(),
    )
    knowledge = SimpleNamespace(
        list_contents=AsyncMock(),
        get_document=AsyncMock(),
        list_tags=AsyncMock(),
        create_note=AsyncMock(),
        patch_document=AsyncMock(),
        move_document=AsyncMock(),
        assign_tags=AsyncMock(),
        trash_document=AsyncMock(),
    )
    storage = SimpleNamespace(download=AsyncMock(), upload_ticket=AsyncMock())
    search = SimpleNamespace(
        search=AsyncMock(),
        ask_bounded=AsyncMock(
            return_value=BoundedAskResult(
                conversation_id=UUID("00000000-0000-0000-0000-000000000010"),
                message_id=UUID("00000000-0000-0000-0000-000000000011"),
                status="completed",
                answer="Grounded answer",
                citations=(),
            )
        ),
    )
    return (
        McpRuntime(
            authorization=authorization,
            workspace=workspace,
            knowledge=knowledge,
            storage=storage,
            search=search,
        ),
        SimpleNamespace(
            authorization=authorization,
            workspace=workspace,
            knowledge=knowledge,
            storage=storage,
            search=search,
        ),
    )


@pytest.mark.asyncio
async def test_official_client_initializes_filters_tools_and_calls_target_service() -> None:
    runtime, calls = runtime_for(("mcp:workspaces:read",))
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={
            "Authorization": "Bearer opaque-access",
            "X-IMA-MCP-Request": "client-spoof-must-be-replaced",
        },
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    initialized = await session.initialize()
                    assert initialized.server_info.name == "intranet-ima"
                    tools = await session.list_tools()
                    assert [tool.name for tool in tools.tools] == ["kb_list_workspaces"]
                    result = await session.call_tool("kb_list_workspaces", {})
    assert result.is_error is False
    assert result.structured_content == {"items": [{"id": "workspace-1", "name": "Allowed"}]}
    calls.workspace.list_workspaces.assert_awaited_once_with("user-1")
    calls.knowledge.get_document.assert_not_awaited()
    assert calls.authorization.authenticate_bearer.await_count >= 3
    calls.authorization.acquire_tool_lease.assert_awaited_once()
    calls.authorization.release_tool_lease.assert_awaited_once()
    assert transport.actors == {}


@pytest.mark.asyncio
async def test_write_tool_calls_only_target_knowledge_service() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    calls.knowledge.create_note.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "folderId": "folder-1",
        "kind": "note",
        "title": "Title",
    }
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer opaque-access"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    assert "kb_create_note" in {tool.name for tool in tools.tools}
                    assert "kb_search" not in {tool.name for tool in tools.tools}
                    result = await session.call_tool(
                        "kb_create_note",
                        {"folder_id": "folder-1", "title": "Title", "markdown": "Body"},
                    )
    assert result.is_error is False
    authorize_call = calls.authorization.authorize_tool.await_args
    assert authorize_call.args[1] == "kb_create_note"
    assert authorize_call.kwargs == {"target_folder_id": "folder-1"}
    calls.knowledge.create_note.assert_awaited_once_with("user-1", "folder-1", "Title", "Body")
    calls.workspace.create_folder.assert_not_awaited()


@pytest.mark.asyncio
async def test_target_exception_releases_concurrency_lease() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    calls.knowledge.create_note.side_effect = RuntimeError("target failed")
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer opaque-access"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "kb_create_note",
                        {"folder_id": "folder-1", "title": "Title", "markdown": "Body"},
                    )
    assert result.is_error is True
    calls.authorization.acquire_tool_lease.assert_awaited_once()
    calls.authorization.release_tool_lease.assert_awaited_once()


@pytest.mark.asyncio
async def test_target_cancellation_releases_concurrency_lease() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    started = asyncio.Event()

    async def blocked(*_: object) -> None:
        started.set()
        await asyncio.Event().wait()

    calls.knowledge.create_note.side_effect = blocked
    transport = McpTransport(
        lambda: runtime, Settings(environment="test", public_origin="http://testserver")
    )
    actor = await calls.authorization.authenticate_bearer()
    context = _current_actor.set(actor)
    try:
        task = asyncio.create_task(transport.adapter.create_note("folder-1", "Title", "Body"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        _current_actor.reset(context)
    calls.authorization.acquire_tool_lease.assert_awaited_once()
    calls.authorization.release_tool_lease.assert_awaited_once()


@pytest.mark.asyncio
async def test_ask_tool_calls_bounded_service_without_sse_parsing() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:ask",))
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer opaque-access"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool("kb_ask", {"question": "Question?"})
    assert result.is_error is False
    calls.search.ask_bounded.assert_awaited_once()
    assert calls.search.ask_bounded.await_args.args[:3] == (
        "user-1",
        "workspace-1",
        "Question?",
    )
    calls.search.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_tag_write_carries_expected_version_to_locked_target_mutation() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    calls.knowledge.get_document.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "folderId": "folder-1",
        "kind": "note",
        "version": 7,
    }
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer opaque-access"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "kb_set_tags",
                        {
                            "document_id": "00000000-0000-0000-0000-000000000001",
                            "tag_ids": ["00000000-0000-0000-0000-000000000002"],
                            "expected_version": 7,
                        },
                    )
    assert result.is_error is False
    calls.knowledge.assign_tags.assert_awaited_once()
    assert calls.knowledge.assign_tags.await_args.args[-1] == 7


@pytest.mark.asyncio
async def test_transport_rejects_missing_and_query_bearers_before_sdk() -> None:
    runtime, calls = runtime_for(("mcp:workspaces:read",))
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app), base_url="http://testserver"
    ) as http:
        missing = await http.post("/mcp", content=b"{}")
        query = await http.post("/mcp?access_token=raw", content=b"{}")
    assert missing.status_code == 401
    assert "resource_metadata=" in missing.headers["www-authenticate"]
    assert query.status_code == 401
    assert 'error="invalid_token"' in query.headers["www-authenticate"]
    calls.authorization.authenticate_bearer.assert_not_awaited()


@pytest.mark.asyncio
async def test_transport_rejects_rebinding_duplicate_auth_and_casefolded_query_before_auth() -> (
    None
):
    runtime, calls = runtime_for(("mcp:workspaces:read",))
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app), base_url="http://testserver"
    ) as http:
        rebound = await http.post(
            "/mcp", headers={"Host": "attacker.example", "Authorization": "Bearer opaque"}
        )
        query = await http.post("/mcp?Authorization=opaque")
        duplicate = await http.post(
            "/mcp",
            headers=[
                ("Authorization", "Bearer first"),
                ("Authorization", "Bearer second"),
            ],
        )
    assert rebound.status_code == 421
    assert query.status_code == 401
    assert duplicate.status_code == 401
    calls.authorization.authenticate_bearer.assert_not_awaited()


@pytest.mark.asyncio
async def test_hidden_tool_call_is_denied_before_target_document_lookup() -> None:
    runtime, calls = runtime_for(("mcp:workspaces:read",))
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer opaque"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        "kb_get_note", {"document_id": "00000000-0000-0000-0000-000000000001"}
                    )
    assert result.is_error is True
    calls.knowledge.get_document.assert_not_awaited()
    assert transport.actors == {}


@pytest.mark.asyncio
async def test_sdk_request_body_limit_runs_after_bearer_authentication() -> None:
    runtime, calls = runtime_for(("mcp:workspaces:read",))
    settings = Settings(
        environment="test", public_origin="http://testserver", mcp_request_max_bytes=128
    )
    transport = McpTransport(lambda: runtime, settings)
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=transport.app),
            base_url="http://testserver",
            headers={"Authorization": "Bearer opaque", "Content-Type": "application/json"},
        ) as http:
            response = await http.post("/mcp", content=b"{" + b"x" * 256 + b"}")
    assert response.status_code == 413
    calls.authorization.authenticate_bearer.assert_awaited_once()
    assert transport.actors == {}


def test_app_lifespan_disposes_engine_when_job_start_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = SimpleNamespace(dispose=AsyncMock())
    jobs = SimpleNamespace(
        start=AsyncMock(side_effect=RuntimeError("start failed")), stop=AsyncMock()
    )
    monkeypatch.setattr(app_module, "create_engine", lambda _: engine)
    monkeypatch.setattr(app_module, "JobService", lambda _settings, _engine: jobs)
    app = app_module.create_app(Settings(environment="test", public_origin="http://testserver"))

    with pytest.raises(BaseExceptionGroup, match="unhandled errors"):
        with TestClient(app, base_url="http://testserver"):
            pass
    engine.dispose.assert_awaited_once()
    jobs.stop.assert_not_awaited()
    assert app.state.mcp_runtime_box == {}


@pytest.mark.asyncio
async def test_service_principal_never_falls_back_to_owner_identity() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:read",))
    principal_actor = McpActor(
        actor_type="service_principal",
        principal_id="11111111-1111-1111-1111-111111111111",
        workspace_id="workspace-1",
        folder_root_id="root-1",
        scopes=("mcp:knowledge:read",),
    )
    calls.authorization.authenticate_bearer.return_value = principal_actor
    calls.knowledge.get_document.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "folderId": "folder-1",
        "kind": "note",
        "title": "Delegated",
        "markdown": "Visible through principal policy",
    }
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer service-access"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool(
                        "kb_get_note", {"document_id": "00000000-0000-0000-0000-000000000001"}
                    )
    assert "kb_get_note" in {tool.name for tool in tools.tools}
    assert "kb_list_tags" not in {tool.name for tool in tools.tools}
    assert "kb_create_note" not in {tool.name for tool in tools.tools}
    assert result.is_error is False
    assert calls.knowledge.get_document.await_count == 2
    assert all(
        call.args[0] is principal_actor for call in calls.knowledge.get_document.await_args_list
    )
    calls.workspace.list_workspaces.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_principal_search_and_download_keep_delegated_actor() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:read", "mcp:knowledge:search"))
    principal_actor = McpActor(
        actor_type="service_principal",
        principal_id="11111111-1111-1111-1111-111111111111",
        workspace_id="workspace-1",
        scopes=("mcp:knowledge:read", "mcp:knowledge:search"),
    )
    calls.authorization.authenticate_bearer.return_value = principal_actor
    calls.search.search.return_value = {"items": []}
    calls.knowledge.get_document.return_value = {
        "id": "00000000-0000-0000-0000-000000000001",
        "folderId": "folder-1",
        "kind": "file",
        "title": "File",
    }
    calls.storage.download.return_value = {
        "url": "https://storage.example/presigned",
        "expiresAt": "2026-08-27T13:00:00Z",
    }
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": "Bearer service-access"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    search_result = await session.call_tool(
                        "kb_search", {"query": "needle", "folder_id": "folder-1"}
                    )
                    file_result = await session.call_tool(
                        "kb_get_file",
                        {"document_id": "00000000-0000-0000-0000-000000000001"},
                    )
    assert search_result.is_error is False
    assert file_result.is_error is False
    assert calls.search.search.await_args.args[0] is principal_actor
    assert calls.storage.download.await_args.args[0] is principal_actor
    assert all(
        call.args[0] is principal_actor for call in calls.knowledge.get_document.await_args_list
    )


@pytest.mark.asyncio
async def test_authenticated_boundary_strips_raw_credentials_before_sdk_dispatch() -> None:
    runtime, calls = runtime_for(("mcp:workspaces:read",))
    captured: dict[str, object] = {}

    async def downstream(scope: Scope, _receive: Receive, send: Send) -> None:
        captured["headers"] = dict(scope["headers"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    actors: dict[str, McpActor] = {}
    settings = Settings(environment="test", public_origin="http://testserver")
    app = AuthenticatedMcpApp(
        downstream,
        lambda: runtime,
        settings,
        actors,
        TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["testserver"],
            allowed_origins=["http://testserver"],
        ),
    )
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://testserver",
        headers={
            "Authorization": "Bearer raw-secret",
            "Proxy-Authorization": "Basic raw-proxy-secret",
            "Cookie": "session=raw-cookie",
            "X-IMA-MCP-Request": "client-spoof",
        },
    ) as http:
        response = await http.get("/mcp")
    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert b"authorization" not in headers
    assert b"proxy-authorization" not in headers
    assert b"cookie" not in headers
    assert headers[b"x-ima-mcp-request"] != b"client-spoof"
    assert actors == {}
    calls.authorization.authenticate_bearer.assert_awaited_once()
