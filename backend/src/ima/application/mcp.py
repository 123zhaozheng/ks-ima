"""Official SDK Streamable HTTP transport and target-service MCP adapters."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import (
    TransportSecurityMiddleware,
    TransportSecuritySettings,
)
from mcp_types import ListToolsResult
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ima.application.authorization import WorkspaceError, WorkspaceService
from ima.application.knowledge import KnowledgeError, KnowledgeService
from ima.application.mcp_contracts import ALL_MCP_SCOPES, McpActor, tools_for_scopes
from ima.application.oauth import McpAuthorizationError, McpAuthorizationService
from ima.application.search import SearchError, SearchService
from ima.application.storage import StorageService
from ima.config import Settings

_current_actor: ContextVar[McpActor | None] = ContextVar("ima_mcp_actor", default=None)


@dataclass(frozen=True, slots=True)
class McpRuntime:
    authorization: McpAuthorizationService
    workspace: WorkspaceService
    knowledge: KnowledgeService
    storage: StorageService
    search: SearchService


class ScopeToolMiddleware:
    """Filter tools/list using the authenticated request actor's scope set."""

    def __init__(self, actors: dict[str, McpActor]) -> None:
        self.actors = actors

    async def __call__(
        self, ctx: ServerRequestContext[Any, Any], call_next: CallNext
    ) -> HandlerResult:
        request = ctx.request
        headers = getattr(request, "headers", None)
        key = headers.get("x-ima-mcp-request") if headers is not None else None
        actor = self.actors.get(str(key)) if key else None
        token = _current_actor.set(actor)
        try:
            result = await call_next(ctx)
            if ctx.method != "tools/list":
                return result
            if isinstance(result, dict):
                tools = result.get("tools")
                if not isinstance(tools, list):
                    return result
                allowed = self._allowed(actor)
                return {
                    **result,
                    "tools": [
                        tool
                        for tool in tools
                        if (
                            tool.get("name")
                            if isinstance(tool, dict)
                            else getattr(tool, "name", None)
                        )
                        in allowed
                    ],
                }
            if not isinstance(result, ListToolsResult):
                return result
            allowed = self._allowed(actor)
            return result.model_copy(
                update={"tools": [tool for tool in result.tools if tool.name in allowed]}
            )
        finally:
            _current_actor.reset(token)

    @staticmethod
    def _allowed(actor: McpActor | None) -> set[str]:
        if actor is None:
            return set()
        allowed = set(tools_for_scopes(actor.scopes))
        if actor.actor_type == "service_principal":
            allowed.difference_update(
                {
                    "kb_ask",
                    "kb_mkdir",
                    "kb_create_note",
                    "kb_update_note",
                    "kb_upload_file",
                    "kb_move",
                    "kb_set_tags",
                    "kb_delete",
                }
            )
        if actor.folder_root_id is not None:
            allowed.discard("kb_list_tags")
        return allowed


class McpToolAdapter:
    """Bounded MCP functions that call only public target application services."""

    def __init__(self, runtime: Callable[[], McpRuntime], settings: Settings) -> None:
        self._runtime = runtime
        self._settings = settings

    def _actor(self, *, human_only: bool = False) -> McpActor:
        actor = _current_actor.get()
        if actor is None:
            raise ToolError("UNAUTHENTICATED: Bearer authentication is required")
        if human_only and (actor.actor_type != "human" or actor.user_id is None):
            raise ToolError("POLICY_DENIED: delegated target adapter is not available")
        return actor

    def _bounded(self, value: Any) -> Any:
        encoded = json.dumps(value, default=str, ensure_ascii=True).encode("utf-8")
        if len(encoded) > self._settings.mcp_body_max_bytes:
            raise ToolError("RESULT_TOO_LARGE: MCP result exceeds the configured limit")
        return value

    async def _execute(
        self,
        tool_name: str,
        operation: Callable[[Any], Awaitable[Any]],
        *,
        target_folder_id: str | None = None,
        human_only: bool = False,
        timeout_seconds: float = 15,
    ) -> Any:
        actor = self._actor(human_only=human_only)
        runtime = self._runtime()
        lease_id: UUID | None = None
        try:
            await runtime.authorization.authorize_tool(
                actor, tool_name, target_folder_id=target_folder_id
            )
            lease_id = await runtime.authorization.acquire_tool_lease(
                actor, secrets.token_urlsafe(18)
            )
            # Stay below the repository's 60-second cross-replica lease TTL so a
            # timed-out operation still releases its lease itself.
            async with asyncio.timeout(timeout_seconds):
                result = await operation(actor.user_id if actor.user_id is not None else actor)
            return self._bounded(result)
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise ToolError("TIMEOUT: target operation timed out") from exc
        except (McpAuthorizationError, WorkspaceError, KnowledgeError, SearchError) as exc:
            code = getattr(exc, "code", None) or getattr(exc, "reason", "POLICY_DENIED")
            detail = getattr(exc, "detail", "Target operation denied")
            raise ToolError(f"{code}: {detail}") from exc
        except Exception:
            raise ToolError("INTERNAL_ERROR: target operation failed") from None
        finally:
            if lease_id is not None:
                await runtime.authorization.release_tool_lease(lease_id)

    async def _document(
        self,
        tool_name: str,
        document_id: UUID,
        operation: Callable[[Any], Awaitable[Any]],
        *,
        human_only: bool = False,
    ) -> Any:
        actor = self._actor(human_only=human_only)
        runtime = self._runtime()
        lease_id: UUID | None = None
        try:
            # Enforce OAuth scope and current grant lifecycle before loading any
            # protected document metadata needed for the folder-level check.
            await runtime.authorization.authorize_tool(actor, tool_name)
            lease_id = await runtime.authorization.acquire_tool_lease(
                actor, secrets.token_urlsafe(18)
            )
            # Keep the complete post-acquisition path below the repository's
            # 60-second cross-replica lease recovery TTL.
            async with asyncio.timeout(45):
                document = await runtime.knowledge.get_document(
                    actor.user_id if actor.user_id is not None else actor, document_id
                )
                await runtime.authorization.authorize_tool(
                    actor, tool_name, target_folder_id=str(document["folderId"])
                )
                result = await operation(actor.user_id if actor.user_id is not None else actor)
                return self._bounded(result)
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise ToolError("TIMEOUT: target operation timed out") from exc
        except (McpAuthorizationError, WorkspaceError, KnowledgeError, SearchError) as exc:
            code = getattr(exc, "code", None) or getattr(exc, "reason", "POLICY_DENIED")
            detail = getattr(exc, "detail", "Target operation denied")
            raise ToolError(f"{code}: {detail}") from exc
        except Exception:
            raise ToolError("INTERNAL_ERROR: target operation failed") from None
        finally:
            if lease_id is not None:
                await runtime.authorization.release_tool_lease(lease_id)

    async def list_workspaces(self) -> dict[str, Any]:
        actor = self._actor()

        async def run(identity: Any) -> Any:
            if isinstance(identity, McpActor):
                value = await self._runtime().workspace.delegated_workspace(identity)
                return {"items": [value]}
            values = await self._runtime().workspace.list_workspaces(identity)
            return {"items": [item for item in values if item["id"] == actor.workspace_id]}

        return cast(dict[str, Any], await self._execute("kb_list_workspaces", run))

    async def list_dir(
        self,
        folder_id: str,
        cursor: str | None = None,
        limit: int = 50,
        kind: str | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._execute(
                "kb_list_dir",
                lambda user: self._runtime().knowledge.list_contents(
                    user, folder_id, cursor, min(max(limit, 1), 100), kind
                ),
                target_folder_id=folder_id,
            ),
        )

    async def get_tree(self, folder_id: str) -> dict[str, Any]:
        actor = self._actor()

        async def run(user: str) -> Any:
            workspace = actor.workspace_id
            if actor.actor_type == "service_principal":
                folder = await self._runtime().workspace.delegated_folder(actor, folder_id)
                breadcrumbs = await self._runtime().workspace.delegated_breadcrumbs(
                    actor, folder_id
                )
                children = await self._runtime().workspace.delegated_folders(actor, folder_id)
            else:
                folder = await self._runtime().workspace.folder(user, workspace, folder_id)
                breadcrumbs = await self._runtime().workspace.breadcrumbs(
                    user, workspace, folder_id
                )
                children = await self._runtime().workspace.folders(user, workspace, folder_id)
            return {"folder": folder, "breadcrumbs": breadcrumbs, "children": children}

        return cast(
            dict[str, Any],
            await self._execute("kb_get_tree", run, target_folder_id=folder_id),
        )

    async def get_note(self, document_id: UUID) -> dict[str, Any]:
        async def run(user: str) -> Any:
            value = await self._runtime().knowledge.get_document(user, document_id)
            if value["kind"] != "note":
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            return value

        return cast(dict[str, Any], await self._document("kb_get_note", document_id, run))

    async def get_file(self, document_id: UUID) -> dict[str, Any]:
        async def run(user: str) -> Any:
            value = await self._runtime().knowledge.get_document(user, document_id)
            if value["kind"] != "file":
                raise KnowledgeError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            download = await self._runtime().storage.download(user, document_id)
            return {"document": value, "download": download}

        return cast(dict[str, Any], await self._document("kb_get_file", document_id, run))

    async def list_tags(self) -> dict[str, Any]:
        actor = self._actor()
        if actor.folder_root_id is not None:
            raise ToolError("POLICY_DENIED: folder-scoped grants cannot list workspace tags")
        return cast(
            dict[str, Any],
            await self._execute(
                "kb_list_tags",
                lambda user: self._list_tags(user, actor.workspace_id),
            ),
        )

    async def _list_tags(self, user: str, workspace_id: str) -> dict[str, Any]:
        return {"items": await self._runtime().knowledge.list_tags(user, workspace_id)}

    async def search(
        self,
        query: str,
        mode: str = "keyword",
        top_k: int = 8,
        threshold: float = 0,
        folder_id: str | None = None,
        tag_id: UUID | None = None,
    ) -> dict[str, Any]:
        actor = self._actor()
        effective_folder = folder_id or actor.folder_root_id
        return cast(
            dict[str, Any],
            await self._execute(
                "kb_search",
                lambda user: self._runtime().search.search(
                    user,
                    actor.workspace_id,
                    query,
                    mode=mode,
                    top_k=min(max(top_k, 1), 50),
                    threshold=min(max(threshold, 0), 1),
                    folder_id=effective_folder,
                    tag_id=tag_id,
                ),
                target_folder_id=effective_folder,
            ),
        )

    async def ask(self, question: str, conversation_id: UUID | None = None) -> dict[str, Any]:
        actor = self._actor(human_only=True)

        async def run(user: str) -> Any:
            result = await self._runtime().search.ask_bounded(
                user,
                actor.workspace_id,
                question,
                conversation_id,
                max_answer_chars=max(1, min(self._settings.mcp_body_max_bytes // 4, 100000)),
                max_citations=20,
                timeout_seconds=30,
            )
            return {
                "conversationId": result.conversation_id,
                "messageId": result.message_id,
                "status": result.status,
                "answer": result.answer,
                "citations": result.citations,
            }

        return cast(
            dict[str, Any],
            await self._execute("kb_ask", run, human_only=True, timeout_seconds=45),
        )

    async def mkdir(self, parent_id: str, name: str) -> dict[str, Any]:
        actor = self._actor()
        return cast(
            dict[str, Any],
            await self._execute(
                "kb_mkdir",
                lambda user: self._runtime().workspace.create_folder(
                    user, actor.workspace_id, parent_id, name
                ),
                target_folder_id=parent_id,
                human_only=True,
            ),
        )

    async def create_note(self, folder_id: str, title: str, markdown: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._execute(
                "kb_create_note",
                lambda user: self._runtime().knowledge.create_note(
                    user, folder_id, title, markdown
                ),
                target_folder_id=folder_id,
                human_only=True,
            ),
        )

    async def upload_file(
        self,
        folder_id: str,
        title: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        checksum: str,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._execute(
                "kb_upload_file",
                lambda user: self._runtime().storage.upload_ticket(
                    user,
                    folder_id,
                    title,
                    filename,
                    mime_type,
                    size_bytes,
                    checksum,
                ),
                target_folder_id=folder_id,
                human_only=True,
            ),
        )

    async def update_note(
        self,
        document_id: UUID,
        expected_version: int,
        expected_content_version: int,
        title: str | None = None,
        markdown: str | None = None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._document(
                "kb_update_note",
                document_id,
                lambda user: self._runtime().knowledge.patch_document(
                    user,
                    document_id,
                    title=title,
                    markdown=markdown,
                    expected_version=expected_version,
                    expected_content_version=expected_content_version,
                ),
                human_only=True,
            ),
        )

    async def move(
        self, document_id: UUID, destination_folder_id: str, expected_version: int
    ) -> dict[str, Any]:
        actor = self._actor(human_only=True)
        await self._runtime().authorization.authorize_tool(
            actor, "kb_move", target_folder_id=destination_folder_id
        )
        return cast(
            dict[str, Any],
            await self._document(
                "kb_move",
                document_id,
                lambda user: self._runtime().knowledge.move_document(
                    user, document_id, destination_folder_id, expected_version
                ),
                human_only=True,
            ),
        )

    async def set_tags(
        self, document_id: UUID, tag_ids: tuple[UUID, ...], expected_version: int
    ) -> dict[str, bool]:
        async def run(user: str) -> Any:
            await self._runtime().knowledge.assign_tags(
                user, document_id, tag_ids, expected_version
            )
            return {"updated": True}

        return cast(
            dict[str, bool],
            await self._document("kb_set_tags", document_id, run, human_only=True),
        )

    async def delete(self, document_id: UUID, expected_version: int) -> dict[str, bool]:
        async def run(user: str) -> Any:
            await self._runtime().knowledge.trash_document(user, document_id, expected_version)
            return {"trashed": True}

        return cast(
            dict[str, bool],
            await self._document("kb_delete", document_id, run, human_only=True),
        )


class AuthenticatedMcpApp:
    """Authenticate canonical/alias HTTP before any SDK JSON-RPC dispatch."""

    def __init__(
        self,
        app: ASGIApp,
        runtime: Callable[[], McpRuntime],
        settings: Settings,
        actors: dict[str, McpActor],
        transport_security: TransportSecuritySettings,
    ) -> None:
        self.app = app
        self.runtime = runtime
        self.settings = settings
        self.actors = actors
        self.transport_security = TransportSecurityMiddleware(transport_security)

    async def _response(
        self, send: Send, status: int, headers: list[tuple[bytes, bytes]] | None = None
    ) -> None:
        safe_headers = [
            *(headers or []),
            (b"cache-control", b"no-store"),
            (b"pragma", b"no-cache"),
        ]
        await send({"type": "http.response.start", "status": status, "headers": safe_headers})
        await send({"type": "http.response.body", "body": b""})

    def _challenge(self, error: str | None = None) -> bytes:
        metadata = f"{self.settings.public_origin}/.well-known/oauth-protected-resource/mcp"
        value = f'Bearer resource_metadata="{metadata}"'
        value += f', scope="{" ".join(scope.value for scope in ALL_MCP_SCOPES)}"'
        if error:
            value += f', error="{error}"'
        return value.encode("ascii")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path", ""))
        if path not in {"/mcp", "/api/mcp"}:
            await self._response(send, 404)
            return
        if path == "/api/mcp" and not self.settings.mcp_legacy_alias_enabled:
            await self._response(send, 404)
            return
        security_failure = await self.transport_security.validate_request(
            Request(scope, receive), is_post=False
        )
        if security_failure is not None:
            security_failure.headers.update({"Cache-Control": "no-store", "Pragma": "no-cache"})
            await security_failure(scope, receive, send)
            return
        query = bytes(scope.get("query_string", b"")).decode("utf-8", "replace")
        query_names = {name.casefold() for name, _ in parse_qsl(query, keep_blank_values=True)}
        if query_names.intersection({"access_token", "token", "authorization", "bearer_token"}):
            await self._response(
                send, 401, [(b"www-authenticate", self._challenge("invalid_token"))]
            )
            return
        raw_headers = cast(list[tuple[bytes, bytes]], scope.get("headers", []))
        authorization_headers = [
            bytes(value) for key, value in raw_headers if bytes(key).lower() == b"authorization"
        ]
        if len(authorization_headers) != 1:
            await self._response(send, 401, [(b"www-authenticate", self._challenge())])
            return
        authorization = authorization_headers[0].decode("ascii", "ignore")
        scheme, separator, raw = authorization.partition(" ")
        if not separator or scheme.lower() != "bearer" or not raw or " " in raw:
            await self._response(send, 401, [(b"www-authenticate", self._challenge())])
            return
        client = cast(tuple[str, int] | None, scope.get("client"))
        source_ip = client[0] if client else "unknown"
        try:
            actor = await self.runtime().authorization.authenticate_bearer(
                raw,
                source_ip=source_ip,
                correlation_id=(
                    str(scope.get("ima.correlation_id"))
                    if scope.get("ima.correlation_id")
                    else None
                ),
            )
        except McpAuthorizationError as exc:
            if exc.reason == "rate_limited":
                await self._response(send, 429, [(b"retry-after", b"60")])
                return
            if exc.reason in {"insufficient_scope", "policy_denied", "network_denied"}:
                await self._response(
                    send,
                    403,
                    [(b"www-authenticate", self._challenge("insufficient_scope"))],
                )
                return
            await self._response(
                send, 401, [(b"www-authenticate", self._challenge("invalid_token"))]
            )
            return
        if path == "/api/mcp":
            await self.runtime().authorization.repository.append_audit(
                actor.user_id,
                "legacy.mcp.alias_used",
                "success",
                target_type="service_principal" if actor.principal_id else "user",
                target_id=actor.principal_id or actor.user_id,
                metadata={"canonicalResource": "/mcp"},
                correlation_id=actor.correlation_id or None,
            )
        rewritten = dict(scope)
        rewritten["path"] = "/mcp"
        rewritten["raw_path"] = b"/mcp"
        request_key = secrets.token_urlsafe(18)
        self.actors[request_key] = actor
        sensitive_headers = {
            b"authorization",
            b"proxy-authorization",
            b"cookie",
            b"x-ima-mcp-request",
        }
        forwarded_headers = [
            (key, value) for key, value in raw_headers if key.lower() not in sensitive_headers
        ]
        rewritten["headers"] = [
            *forwarded_headers,
            (b"x-ima-mcp-request", request_key.encode("ascii")),
        ]

        async def no_store_send(message: Message) -> None:
            if message.get("type") == "http.response.start":
                response_headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"pragma"}
                ]
                message = {
                    **message,
                    "headers": [
                        *response_headers,
                        (b"cache-control", b"no-store"),
                        (b"pragma", b"no-cache"),
                    ],
                }
            await send(message)

        try:
            await self.app(cast(Scope, rewritten), receive, no_store_send)
        finally:
            self.actors.pop(request_key, None)


class McpTransport:
    """Configured SDK server plus authenticated ASGI application."""

    def __init__(self, runtime: Callable[[], McpRuntime], settings: Settings) -> None:
        self.adapter = McpToolAdapter(runtime, settings)
        self.actors: dict[str, McpActor] = {}
        self.server = MCPServer(
            name="intranet-ima",
            title="Intranet IMA",
            version=settings.build_version,
            middleware=(ScopeToolMiddleware(self.actors),),
        )
        self._register_tools()
        parsed = urlsplit(settings.public_origin)
        transport_security = TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[parsed.netloc, f"{parsed.hostname}:*"],
            allowed_origins=[settings.public_origin, *settings.cors_origins],
        )
        sdk_app = self.server.streamable_http_app(
            streamable_http_path="/mcp",
            json_response=True,
            stateless_http=True,
            max_request_body_size=settings.mcp_request_max_bytes,
            transport_security=transport_security,
            host=parsed.hostname or "localhost",
        )
        self.sdk_app = sdk_app
        self.app = AuthenticatedMcpApp(sdk_app, runtime, settings, self.actors, transport_security)

    def _register_tools(self) -> None:
        tools: tuple[tuple[str, Callable[..., Awaitable[Any]]], ...] = (
            ("kb_list_workspaces", self.adapter.list_workspaces),
            ("kb_list_dir", self.adapter.list_dir),
            ("kb_get_tree", self.adapter.get_tree),
            ("kb_get_note", self.adapter.get_note),
            ("kb_get_file", self.adapter.get_file),
            ("kb_list_tags", self.adapter.list_tags),
            ("kb_search", self.adapter.search),
            ("kb_ask", self.adapter.ask),
            ("kb_mkdir", self.adapter.mkdir),
            ("kb_create_note", self.adapter.create_note),
            ("kb_upload_file", self.adapter.upload_file),
            ("kb_update_note", self.adapter.update_note),
            ("kb_move", self.adapter.move),
            ("kb_set_tags", self.adapter.set_tags),
            ("kb_delete", self.adapter.delete),
        )
        for name, function in tools:
            self.server.add_tool(function, name=name, structured_output=True)
