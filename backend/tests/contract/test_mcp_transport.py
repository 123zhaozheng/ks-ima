"""Official SDK interoperability and target-service tracing for MCP transport."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
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
from ima.application.oauth import (
    KB_ROLE_RANK,
    TOOL_MIN_ROLE,
    McpAuthorizationError,
    McpAuthorizationService,
)
from ima.application.search import BoundedAskResult
from ima.config import Settings
from ima.domain.oauth import CredentialRecord, ServicePrincipalRecord

# user-1 can edit one knowledge base, view a second one, and is a member of
# nothing else.  The transport stub enforces the same scope+role matrix the
# real McpAuthorizationService applies per tool call.
KB_ROLES = {"kb-editor": "editor", "kb-viewer": "viewer"}
KB_SUMMARIES = [
    {"id": "kb-editor", "name": "Editable", "role": "editor", "owned": True},
    {"id": "kb-viewer", "name": "Read-only", "role": "viewer", "owned": False},
]

DOC_ID = "00000000-0000-0000-0000-000000000001"


def runtime_for(scopes: tuple[str, ...]) -> tuple[McpRuntime, object]:
    actor = McpActor(
        actor_type="human",
        user_id="user-1",
        scopes=scopes,
        correlationId="corr-1",
    )

    async def authorize_tool(
        call_actor: McpActor, tool_name: str, *, target_kb_id: str | None = None
    ) -> None:
        required = KNOWN_TOOLS.get(tool_name)
        if required is None or required not in call_actor.scopes:
            raise McpAuthorizationError("insufficient_scope", "Tool scope is not granted")
        if target_kb_id is not None:
            role = KB_ROLES.get(target_kb_id)
            if role is None:
                raise McpAuthorizationError("policy_denied", "Knowledge base is not accessible")
            if KB_ROLE_RANK[role] < KB_ROLE_RANK[TOOL_MIN_ROLE.get(tool_name, "viewer")]:
                raise McpAuthorizationError("policy_denied", "Knowledge base role is insufficient")

    async def effective_user_id(call_actor: McpActor) -> str:
        return "user-1" if call_actor.actor_type == "human" else "owner-1"

    authorization = SimpleNamespace(
        authenticate_bearer=AsyncMock(return_value=actor),
        authorize_tool=AsyncMock(side_effect=authorize_tool),
        effective_user_id=AsyncMock(side_effect=effective_user_id),
        acquire_tool_lease=AsyncMock(return_value=UUID("00000000-0000-0000-0000-000000000099")),
        release_tool_lease=AsyncMock(),
        repository=SimpleNamespace(append_audit=AsyncMock()),
    )
    kb = SimpleNamespace(
        list_knowledge_bases=AsyncMock(return_value=KB_SUMMARIES),
        create_folder=AsyncMock(),
        folder=AsyncMock(),
        breadcrumbs=AsyncMock(),
        folders=AsyncMock(),
    )
    knowledge = SimpleNamespace(
        list_contents=AsyncMock(),
        get_document=AsyncMock(),
        create_note=AsyncMock(),
        patch_document=AsyncMock(),
        move_document=AsyncMock(),
        delete_document=AsyncMock(),
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
            kb=kb,
            knowledge=knowledge,
            storage=storage,
            search=search,
        ),
        SimpleNamespace(
            authorization=authorization,
            kb=kb,
            knowledge=knowledge,
            storage=storage,
            search=search,
        ),
    )


@pytest.mark.asyncio
async def test_official_client_enumerates_all_user_knowledge_bases() -> None:
    runtime, calls = runtime_for(("mcp:knowledge-bases:read",))
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
                    assert [tool.name for tool in tools.tools] == ["kb_list_knowledge_bases"]
                    result = await session.call_tool("kb_list_knowledge_bases", {})
    assert result.is_error is False
    # Owned and shared knowledge bases are both visible at user level.
    assert result.structured_content == {"items": KB_SUMMARIES}
    calls.kb.list_knowledge_bases.assert_awaited_once_with("user-1")
    calls.knowledge.get_document.assert_not_awaited()
    assert calls.authorization.authenticate_bearer.await_count >= 3
    calls.authorization.acquire_tool_lease.assert_awaited_once()
    calls.authorization.release_tool_lease.assert_awaited_once()
    assert transport.actors == {}


@pytest.mark.asyncio
async def test_write_tool_allowed_on_editable_knowledge_base() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    calls.knowledge.create_note.return_value = {
        "id": DOC_ID,
        "kbId": "kb-editor",
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
                        {
                            "kb_id": "kb-editor",
                            "folder_id": "folder-1",
                            "title": "Title",
                            "markdown": "Body",
                        },
                    )
    assert result.is_error is False
    authorize_call = calls.authorization.authorize_tool.await_args
    assert authorize_call.args[1] == "kb_create_note"
    assert authorize_call.kwargs == {"target_kb_id": "kb-editor"}
    calls.knowledge.create_note.assert_awaited_once_with("user-1", "folder-1", "Title", "Body")
    calls.kb.create_folder.assert_not_awaited()


@pytest.mark.asyncio
async def test_write_tool_rejected_on_read_only_knowledge_base() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
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
                        {
                            "kb_id": "kb-viewer",
                            "folder_id": "folder-1",
                            "title": "Title",
                            "markdown": "Body",
                        },
                    )
    assert result.is_error is True
    calls.knowledge.create_note.assert_not_awaited()
    calls.authorization.acquire_tool_lease.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_tool_allowed_on_read_only_knowledge_base() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:read",))
    calls.knowledge.list_contents.return_value = {"items": [], "nextCursor": None}
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
                        "kb_list_dir", {"kb_id": "kb-viewer", "folder_id": "folder-1"}
                    )
    assert result.is_error is False
    calls.knowledge.list_contents.assert_awaited_once_with("user-1", "folder-1", None, 50, None)
    assert calls.authorization.authorize_tool.await_args.kwargs == {"target_kb_id": "kb-viewer"}


@pytest.mark.asyncio
async def test_tool_call_to_foreign_knowledge_base_is_denied() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:read",))
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
                        "kb_get_tree", {"kb_id": "kb-foreign", "folder_id": "folder-1"}
                    )
    assert result.is_error is True
    calls.kb.folder.assert_not_awaited()


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
                        {
                            "kb_id": "kb-editor",
                            "folder_id": "folder-1",
                            "title": "Title",
                            "markdown": "Body",
                        },
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
        task = asyncio.create_task(
            transport.adapter.create_note("kb-editor", "folder-1", "Title", "Body")
        )
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
                    result = await session.call_tool(
                        "kb_ask", {"kb_id": "kb-editor", "question": "Question?"}
                    )
    assert result.is_error is False
    calls.search.ask_bounded.assert_awaited_once()
    assert calls.search.ask_bounded.await_args.args[:3] == (
        "user-1",
        "kb-editor",
        "Question?",
    )
    calls.search.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_note_rechecks_knowledge_base_from_document() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    calls.knowledge.get_document.return_value = {
        "id": DOC_ID,
        "kbId": "kb-editor",
        "folderId": "folder-1",
        "kind": "note",
        "version": 7,
    }
    calls.knowledge.patch_document.return_value = {
        "id": DOC_ID,
        "kbId": "kb-editor",
        "folderId": "folder-1",
        "kind": "note",
        "version": 8,
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
                        "kb_update_note",
                        {
                            "document_id": DOC_ID,
                            "expected_version": 7,
                            "expected_content_version": 3,
                            "markdown": "New body",
                        },
                    )
    assert result.is_error is False
    calls.knowledge.patch_document.assert_awaited_once()
    patch_kwargs = calls.knowledge.patch_document.await_args.kwargs
    assert patch_kwargs["expected_version"] == 7
    assert patch_kwargs["expected_content_version"] == 3
    # The scope gate runs first, then the knowledge-base check from the document.
    assert calls.authorization.authorize_tool.await_args_list[-1].kwargs == {
        "target_kb_id": "kb-editor"
    }


@pytest.mark.asyncio
async def test_transport_rejects_missing_and_query_bearers_before_sdk() -> None:
    runtime, calls = runtime_for(("mcp:knowledge-bases:read",))
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
    runtime, calls = runtime_for(("mcp:knowledge-bases:read",))
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
    runtime, calls = runtime_for(("mcp:knowledge-bases:read",))
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
                    result = await session.call_tool("kb_get_note", {"document_id": DOC_ID})
    assert result.is_error is True
    calls.knowledge.get_document.assert_not_awaited()
    assert transport.actors == {}


@pytest.mark.asyncio
async def test_sdk_request_body_limit_runs_after_bearer_authentication() -> None:
    runtime, calls = runtime_for(("mcp:knowledge-bases:read",))
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
async def test_service_principal_acts_as_owner_user_identity() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:read",))
    principal_actor = McpActor(
        actor_type="service_principal",
        principal_id="11111111-1111-1111-1111-111111111111",
        scopes=("mcp:knowledge:read",),
    )
    calls.authorization.authenticate_bearer.return_value = principal_actor
    calls.knowledge.get_document.return_value = {
        "id": DOC_ID,
        "kbId": "kb-editor",
        "folderId": "folder-1",
        "kind": "note",
        "title": "Delegated",
        "markdown": "Visible through the owner's membership",
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
                    result = await session.call_tool("kb_get_note", {"document_id": DOC_ID})
    names = {tool.name for tool in tools.tools}
    assert "kb_get_note" in names
    # Tag tools are gone and write/ask scopes are not granted to this principal.
    assert "kb_list_tags" not in names
    assert "kb_set_tags" not in names
    assert "kb_create_note" not in names
    assert "kb_ask" not in names
    assert result.is_error is False
    # Target services receive the owner's user id, never the raw actor.
    assert calls.knowledge.get_document.await_count == 2
    assert all(call.args[0] == "owner-1" for call in calls.knowledge.get_document.await_args_list)
    calls.kb.list_knowledge_bases.assert_not_awaited()


@pytest.mark.asyncio
async def test_service_principal_write_follows_owner_role() -> None:
    runtime, calls = runtime_for(("mcp:knowledge:write",))
    principal_actor = McpActor(
        actor_type="service_principal",
        principal_id="11111111-1111-1111-1111-111111111111",
        scopes=("mcp:knowledge:write",),
    )
    calls.authorization.authenticate_bearer.return_value = principal_actor
    calls.knowledge.create_note.return_value = {"id": DOC_ID, "kbId": "kb-editor"}
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
                    allowed = await session.call_tool(
                        "kb_create_note",
                        {
                            "kb_id": "kb-editor",
                            "folder_id": "folder-1",
                            "title": "Title",
                            "markdown": "Body",
                        },
                    )
                    denied = await session.call_tool(
                        "kb_create_note",
                        {
                            "kb_id": "kb-viewer",
                            "folder_id": "folder-1",
                            "title": "Title",
                            "markdown": "Body",
                        },
                    )
    assert allowed.is_error is False
    assert denied.is_error is True
    calls.knowledge.create_note.assert_awaited_once_with("owner-1", "folder-1", "Title", "Body")


@pytest.mark.asyncio
async def test_authenticated_boundary_strips_raw_credentials_before_sdk_dispatch() -> None:
    runtime, calls = runtime_for(("mcp:knowledge-bases:read",))
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


CREDENTIAL_SECRET = "mcp-credential-secret"


def credential_runtime(cidr: tuple[str, ...] = ()) -> tuple[McpRuntime, Any]:
    """Real McpAuthorizationService over fakes: /mcp credential passthrough."""
    machine = ServicePrincipalRecord(
        id=UUID("00000000-0000-0000-0000-0000000000c1"),
        display_name="Connector key",
        purpose="One-click MCP config",
        owner_user_id="owner-1",
        scopes=("mcp:knowledge:read", "mcp:knowledge:write"),
        state="active",
        expires_at=datetime.now(UTC) + timedelta(days=90),
        rate_limit=300,
        concurrency_limit=10,
        cidr_allowlist=cidr,
    )
    credential = CredentialRecord(
        id=UUID("00000000-0000-0000-0000-0000000000d1"),
        principal_id=machine.id,
        credential_id="key-1",
        digest="digest",
        secret_prefix="mcpsc_123",
        expires_at=machine.expires_at,
        created_at=datetime.now(UTC),
    )

    async def resolve(raw: str, *, correlation_id: str | None = None) -> object:
        return (credential, machine) if raw == CREDENTIAL_SECRET else None

    repository = SimpleNamespace(
        resolve_credential_bearer=AsyncMock(side_effect=resolve),
        rate_allowed=AsyncMock(return_value=True),
        load_access_token=AsyncMock(return_value=None),
        load_service_principal=AsyncMock(return_value=machine),
        touch_access_token=AsyncMock(),
        append_audit=AsyncMock(),
        acquire_concurrency_lease=AsyncMock(
            return_value=UUID("00000000-0000-0000-0000-000000000099")
        ),
        release_concurrency_lease=AsyncMock(),
    )
    identity = SimpleNamespace(active_security_stamp=AsyncMock(return_value="stamp-1"))
    kb = SimpleNamespace(list_knowledge_bases=AsyncMock(return_value=KB_SUMMARIES))
    authorization = McpAuthorizationService(
        repository, identity, kb, Settings(environment="test", public_origin="http://testserver")
    )
    knowledge = SimpleNamespace(create_note=AsyncMock(), get_document=AsyncMock())
    runtime = McpRuntime(
        authorization=authorization,
        kb=kb,
        knowledge=knowledge,
        storage=SimpleNamespace(),
        search=SimpleNamespace(),
    )
    calls = SimpleNamespace(
        authorization=authorization,
        repository=repository,
        kb=kb,
        knowledge=knowledge,
    )
    return runtime, calls


@pytest.mark.asyncio
async def test_service_credential_secret_is_a_valid_mcp_bearer() -> None:
    runtime, calls = credential_runtime()
    calls.knowledge.create_note.return_value = {"id": DOC_ID, "title": "Title"}
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    http = httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {CREDENTIAL_SECRET}"},
    )
    async with transport.sdk_app.router.lifespan_context(transport.sdk_app):
        async with http:
            async with streamable_http_client("http://testserver/mcp", http_client=http) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool(
                        "kb_create_note",
                        {
                            "kb_id": "kb-editor",
                            "folder_id": "folder-1",
                            "title": "Title",
                            "markdown": "Body",
                        },
                    )
    assert result.is_error is False
    assert "kb_create_note" in {tool.name for tool in tools.tools}
    calls.knowledge.create_note.assert_awaited_once_with("owner-1", "folder-1", "Title", "Body")
    # The credential resolves through the credential path, never the token path.
    calls.repository.resolve_credential_bearer.assert_awaited()
    calls.repository.touch_access_token.assert_not_awaited()
    calls.repository.acquire_concurrency_lease.assert_awaited_once()


@pytest.mark.asyncio
async def test_unknown_credential_secret_gets_invalid_token_challenge() -> None:
    runtime, _ = credential_runtime()
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app), base_url="http://testserver"
    ) as http:
        response = await http.post(
            "/mcp", headers={"Authorization": "Bearer revoked-or-wrong"}, content=b"{}"
        )
    assert response.status_code == 401
    assert 'error="invalid_token"' in response.headers["www-authenticate"]


@pytest.mark.asyncio
async def test_credential_bearer_outside_cidr_allowlist_is_forbidden() -> None:
    runtime, calls = credential_runtime(cidr=("10.0.0.0/8",))
    settings = Settings(environment="test", public_origin="http://testserver")
    transport = McpTransport(lambda: runtime, settings)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=transport.app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {CREDENTIAL_SECRET}"},
    ) as http:
        response = await http.post("/mcp", content=b"{}")
    assert response.status_code == 403
    assert 'error="insufficient_scope"' in response.headers["www-authenticate"]
    audit = calls.repository.append_audit.await_args
    assert audit.args[1] == "mcp.network.denied"
    assert CREDENTIAL_SECRET not in str(audit)
