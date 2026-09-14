"""Bounded, in-process tools used by the grounded Ask agent loop.

These tools deliberately do not use the MCP transport.  They execute with the
human actor attached to the Ask request, apply the pinned knowledge-base scope
before looking up content, and expose only bounded projections of target data.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text

from ima.application.authorization import KbError, KbService
from ima.application.knowledge import (
    KnowledgeError,
    KnowledgeService,
    effective_user_id,
    kb_membership,
    role_permits,
)
from ima.domain.authorization import KbAction, KbRole, role_allows

MAX_TOOL_RESULTS = 8
MAX_QUOTE_CHARS = 2000
MAX_TOOL_OUTPUT_CHARS = 32000
MAX_OUTLINE_HEADINGS = 64
MAX_OUTLINE_HEADING_CHARS = 240
SAFE_TOOL_ERROR_CODES = frozenset(
    {
        "ACCESS_REVOKED",
        "DOCUMENT_NOT_FOUND",
        "FOLDER_NOT_FOUND",
        "INVALID_ARGUMENT",
        "INVALID_MODE",
        "INVALID_QUERY",
        "INVALID_SCOPE",
        "INVALID_TOOL_RESULT",
        "KB_NOT_FOUND",
        "REINDEX_REQUIRED",
        "RESULT_TOO_LARGE",
        "SCOPE_FORBIDDEN",
        "TOOL_FAILED",
        "TOOL_TIMEOUT",
        "UNKNOWN_TOOL",
    }
)
EXPECTED_SEARCH_ERROR_CODES = frozenset(
    {
        "DOCUMENT_NOT_FOUND",
        "FOLDER_NOT_FOUND",
        "INVALID_MODE",
        "INVALID_QUERY",
        "INVALID_SCOPE",
        "KB_NOT_FOUND",
    }
)

# The gateway consumes the OpenAI-compatible function-tool shape.  Keep this
# value immutable at the call site so a model cannot add an unapproved tool.
ASK_TOOL_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "Search the current knowledge base for grounded source chunks.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "query": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "folderId": {"type": "string", "maxLength": 32},
                    "documentId": {"type": "string", "format": "uuid"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": (
                "List bounded folders and documents in the current knowledge-base directory."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"folderId": {"type": "string", "maxLength": 32}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_outline",
            "description": "Get the bounded heading outline for an accessible document.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"documentId": {"type": "string", "format": "uuid"}},
                "required": ["documentId"],
            },
        },
    },
)


@dataclass(frozen=True, slots=True)
class AskToolResult:
    """Safe tool payload plus the exact chunks made available to the model."""

    value: dict[str, object]
    citations: tuple[dict[str, object], ...] = ()
    hit_count: int = 0


class AskToolError(Exception):
    """A stable, non-sensitive tool failure returned to the model."""

    def __init__(self, code: str, detail: str = "Tool request was denied") -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _safe_error_code(value: object, fallback: str = "TOOL_FAILED") -> str:
    return value if isinstance(value, str) and value in SAFE_TOOL_ERROR_CODES else fallback


class AskToolExecutor:
    """Execute the three Ask tools inside the application process.

    ``search_service`` is intentionally duck typed here.  Keeping this module
    independent of ``SearchService`` avoids an application-layer import cycle
    and makes the authorization and scope invariants easy to unit test with a
    small fake service.
    """

    def __init__(
        self,
        search_service: Any,
        *,
        kb_service: KbService | None = None,
        knowledge_service: KnowledgeService | None = None,
        search_mode: str = "hybrid",
        score_threshold: float = 0.0,
        max_results: int = MAX_TOOL_RESULTS,
        max_quote_chars: int = MAX_QUOTE_CHARS,
    ) -> None:
        self.search_service = search_service
        self.engine = search_service.engine
        self.kb_service = kb_service
        self.knowledge_service = knowledge_service
        self.search_mode = (
            search_mode if search_mode in {"keyword", "vector", "hybrid"} else "hybrid"
        )
        self.score_threshold = max(0.0, min(float(score_threshold), 1.0))
        self.max_results = max(1, min(max_results, MAX_TOOL_RESULTS))
        self.max_quote_chars = max(128, min(max_quote_chars, MAX_QUOTE_CHARS))
        self.citations: list[dict[str, object]] = []

    async def _authorize_kb(self, actor: str, kb_id: str) -> None:
        """Run the live membership decision required by grounded Ask."""
        try:
            if self.kb_service is not None:
                role = await self.kb_service.require_membership(actor, kb_id)
                try:
                    allowed = role_allows(KbRole(role), KbAction.ASK)
                except (ValueError, TypeError):
                    allowed = False
                if not allowed:
                    raise AskToolError("KB_NOT_FOUND")
                return
            async with self.engine.connect() as conn:
                user_id = await effective_user_id(conn, actor)
                membership = await kb_membership(conn, user_id, kb_id) if user_id else None
                if not role_permits(membership[0] if membership else None, KbAction.ASK):
                    raise AskToolError("KB_NOT_FOUND")
        except (KbError, KnowledgeError) as exc:
            raise AskToolError(
                _safe_error_code(getattr(exc, "code", None), "KB_NOT_FOUND")
            ) from exc
        except AskToolError:
            raise

    @staticmethod
    def _uuid(value: object, name: str) -> UUID:
        if not isinstance(value, str) or not value:
            raise AskToolError("INVALID_ARGUMENT", f"{name} is invalid")
        try:
            return UUID(value)
        except ValueError as exc:
            raise AskToolError("INVALID_ARGUMENT", f"{name} is invalid") from exc

    @staticmethod
    def _string(value: object, name: str, *, max_length: int) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > max_length:
            raise AskToolError("INVALID_ARGUMENT", f"{name} is invalid")
        return value.strip()

    @staticmethod
    def _scope_value(scope: object | None, name: str) -> object | None:
        return getattr(scope, name, None) if scope is not None else None

    def _scoped_targets(
        self, arguments: dict[str, object], scope: object | None
    ) -> tuple[str | None, UUID | None]:
        requested_folder = arguments.get("folderId")
        requested_document = arguments.get("documentId")
        if requested_folder is not None:
            requested_folder = self._string(requested_folder, "folderId", max_length=32)
        if requested_document is not None:
            requested_document = self._uuid(requested_document, "documentId")
        scope_folder = self._scope_value(scope, "folder_id")
        scope_document = self._scope_value(scope, "document_id")
        if scope_folder:
            # A pinned folder is the non-bypassable boundary.  The model may
            # omit the argument, but may not replace it with another subtree.
            if requested_document is not None or (
                requested_folder is not None and requested_folder != scope_folder
            ):
                raise AskToolError("SCOPE_FORBIDDEN")
            return str(scope_folder), None
        if scope_document:
            if isinstance(scope_document, UUID):
                scoped_document_id = scope_document
            else:
                try:
                    scoped_document_id = UUID(str(scope_document))
                except (ValueError, TypeError) as exc:
                    raise AskToolError("SCOPE_FORBIDDEN") from exc
            if requested_folder is not None or (
                requested_document is not None and requested_document != scoped_document_id
            ):
                raise AskToolError("SCOPE_FORBIDDEN")
            return None, scoped_document_id
        return (
            str(requested_folder) if requested_folder is not None else None,
            requested_document,
        )

    def _citation(self, item: dict[str, object], *, rank: int) -> dict[str, object]:
        """Project one exact result identity and assign a loop-local rank."""
        required = (
            "documentId",
            "documentVersion",
            "fileGeneration",
            "chunkOrdinal",
            "chunkDigest",
            "quote",
            "score",
        )
        if any(key not in item for key in required):
            raise AskToolError("INVALID_TOOL_RESULT")
        quote = str(item["quote"])[: self.max_quote_chars]
        citation: dict[str, object] = {
            "documentId": str(item["documentId"]),
            "documentVersion": int(str(item["documentVersion"])),
            "fileGeneration": item["fileGeneration"],
            "chunkOrdinal": int(str(item["chunkOrdinal"])),
            "chunkDigest": str(item["chunkDigest"]),
            "title": str(item.get("title", ""))[:256],
            "quote": quote,
            "score": float(str(item["score"])),
            "rank": rank,
        }
        return citation

    @staticmethod
    def _citation_identity(item: dict[str, object]) -> tuple[object, ...]:
        return (
            item["documentId"],
            item["documentVersion"],
            item["fileGeneration"],
            item["chunkOrdinal"],
            item["chunkDigest"],
        )

    @staticmethod
    def _bounded(value: dict[str, object]) -> dict[str, object]:
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded) <= MAX_TOOL_OUTPUT_CHARS:
            return value
        # Tool results are already capped, but keep a second hard boundary if
        # a future projection adds metadata.
        return {"error": "RESULT_TOO_LARGE"}

    async def _search(
        self, actor: str, kb_id: str, arguments: dict[str, object], scope: object | None
    ) -> AskToolResult:
        query = self._string(arguments.get("query"), "query", max_length=4000)
        folder_id, document_id = self._scoped_targets(arguments, scope)
        await self._authorize_kb(actor, kb_id)
        try:
            result = await self.search_service.search(
                actor,
                kb_id,
                query,
                mode=self.search_mode,
                top_k=self.max_results,
                threshold=self.score_threshold,
                folder_id=folder_id,
                document_id=document_id,
                action=KbAction.ASK,
            )
        except (KbError, KnowledgeError) as exc:
            raise AskToolError(
                _safe_error_code(getattr(exc, "code", None), "KB_NOT_FOUND")
            ) from exc
        except Exception as exc:
            # SearchService owns this exception type, so import it only after
            # both application modules have finished initializing. Only its
            # bounded request/scope failures are business tool results;
            # configuration and dependency failures must reach the agent loop.
            from ima.application.search import SearchError

            if isinstance(exc, SearchError) and exc.code in EXPECTED_SEARCH_ERROR_CODES:
                raise AskToolError(exc.code) from exc
            raise
        raw_items = result.get("items", [])
        if not isinstance(raw_items, list):
            raise AskToolError("INVALID_TOOL_RESULT")
        items: list[dict[str, object]] = []
        known = {self._citation_identity(item) for item in self.citations}
        first_rank = len(self.citations) + 1
        for raw in raw_items[: self.max_results]:
            if not isinstance(raw, dict):
                continue
            citation = self._citation(raw, rank=first_rank + len(items))
            if self._citation_identity(citation) in known:
                continue
            # The model receives exactly the identity that may later be
            # persisted; no answer citation can refer to an unseen chunk.
            items.append(citation)
            known.add(self._citation_identity(citation))
        value = self._bounded({"items": items, "degraded": result.get("degraded")})
        if value.get("error"):
            return AskToolResult(value=value, hit_count=0)
        self.citations.extend(items)
        return AskToolResult(
            value=value,
            citations=tuple(items),
            hit_count=len(items),
        )

    async def _list_dir(
        self, actor: str, kb_id: str, arguments: dict[str, object], scope: object | None
    ) -> AskToolResult:
        folder_id, document_id = self._scoped_targets(arguments, scope)
        if document_id is not None:
            raise AskToolError("SCOPE_FORBIDDEN")
        effective_folder = folder_id or str(self._scope_value(scope, "folder_id") or kb_id)
        await self._authorize_kb(actor, kb_id)
        async with self.engine.connect() as conn:
            folder_exists = await conn.scalar(
                text(
                    """SELECT EXISTS(
                        SELECT 1 FROM ima.folders
                        WHERE id=:folder AND kb_id=:kb AND lifecycle='active'
                    )"""
                ),
                {"folder": effective_folder, "kb": kb_id},
            )
        if not folder_exists:
            raise AskToolError("FOLDER_NOT_FOUND")
        try:
            if self.knowledge_service is not None:
                result = await self.knowledge_service.list_contents(
                    actor, effective_folder, None, self.max_results
                )
            else:
                async with self.engine.connect() as conn:
                    rows = (
                        (
                            await conn.execute(
                                text(
                                    """SELECT id,kind,title,version,lifecycle,created_at
                                    FROM (
                                      SELECT id,'folder' AS kind,name AS title,version,lifecycle,
                                        created_at
                                      FROM ima.folders
                                      WHERE id<>:kb AND parent_id=:folder AND kb_id=:kb
                                        AND lifecycle='active'
                                      UNION ALL
                                      SELECT id,kind,title,version,lifecycle,created_at
                                      FROM ima.documents
                                      WHERE folder_id=:folder AND kb_id=:kb AND lifecycle='active'
                                    ) items ORDER BY kind,title,id LIMIT :limit"""
                                ),
                                {
                                    "kb": kb_id,
                                    "folder": effective_folder,
                                    "limit": self.max_results,
                                },
                            )
                        )
                        .mappings()
                        .all()
                    )
                result = {"items": [dict(row) for row in rows], "nextCursor": None}
        except (KbError, KnowledgeError) as exc:
            raise AskToolError(
                _safe_error_code(getattr(exc, "code", None), "FOLDER_NOT_FOUND")
            ) from exc
        items = result.get("items", []) if isinstance(result, dict) else []
        bounded_items = [
            {
                key: (str(value)[:256] if key in {"id", "title", "name"} else value)
                for key, value in row.items()
                if key in {"id", "kind", "title", "name", "version", "lifecycle", "fileState"}
            }
            for row in items[: self.max_results]
            if isinstance(row, dict)
        ]
        return AskToolResult(
            value=self._bounded({"items": bounded_items}), hit_count=len(bounded_items)
        )

    async def _document_outline(
        self, actor: str, kb_id: str, arguments: dict[str, object], scope: object | None
    ) -> AskToolResult:
        document_id = self._uuid(arguments.get("documentId"), "documentId")
        scoped_document = self._scope_value(scope, "document_id")
        if scoped_document is not None:
            try:
                scoped_document_id = (
                    scoped_document
                    if isinstance(scoped_document, UUID)
                    else UUID(str(scoped_document))
                )
            except (TypeError, ValueError) as exc:
                raise AskToolError("SCOPE_FORBIDDEN") from exc
            if document_id != scoped_document_id:
                raise AskToolError("SCOPE_FORBIDDEN")
        await self._authorize_kb(actor, kb_id)
        async with self.engine.connect() as conn:
            # Apply the knowledge-base boundary before loading document content
            # through KnowledgeService, not after a potentially broad lookup.
            document_exists = await conn.scalar(
                text(
                    """SELECT EXISTS(
                        SELECT 1 FROM ima.documents
                        WHERE id=:document AND kb_id=:kb AND lifecycle='active'
                    )"""
                ),
                {"document": document_id, "kb": kb_id},
            )
            if not document_exists:
                raise AskToolError("DOCUMENT_NOT_FOUND")
            if self._scope_value(scope, "folder_id"):
                inside = await conn.scalar(
                    text(
                        """SELECT EXISTS(
                            SELECT 1 FROM ima.documents d
                            JOIN ima.folder_closure c ON c.kb_id=d.kb_id
                              AND c.descendant_id=d.folder_id
                            WHERE d.id=:document AND d.kb_id=:kb AND d.lifecycle='active'
                              AND c.ancestor_id=:ancestor
                        )"""
                    ),
                    {
                        "document": document_id,
                        "kb": kb_id,
                        "ancestor": self._scope_value(scope, "folder_id"),
                    },
                )
                if not inside:
                    raise AskToolError("SCOPE_FORBIDDEN")
        document: dict[str, Any]
        try:
            if self.knowledge_service is not None:
                document = await self.knowledge_service.get_document(actor, document_id)
                if str(document.get("kbId")) != kb_id:
                    raise AskToolError("DOCUMENT_NOT_FOUND")
            else:
                async with self.engine.connect() as conn:
                    row = (
                        (
                            await conn.execute(
                                text(
                                    """SELECT d.id,d.kb_id,d.folder_id,d.kind,d.title,
                                    d.current_version,v.markdown
                                    FROM ima.documents d
                                    LEFT JOIN ima.document_versions v
                                      ON v.document_id=d.id AND v.version=d.current_version
                                    WHERE d.id=:document AND d.kb_id=:kb AND d.lifecycle='active'"""
                                ),
                                {"document": document_id, "kb": kb_id},
                            )
                        )
                        .mappings()
                        .first()
                    )
                if not row:
                    raise AskToolError("DOCUMENT_NOT_FOUND")
                document = {
                    "id": row["id"],
                    "kbId": row["kb_id"],
                    "folderId": row["folder_id"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "currentContentVersion": row["current_version"],
                    "markdown": row["markdown"],
                }
        except AskToolError:
            raise
        except (KbError, KnowledgeError) as exc:
            raise AskToolError(
                _safe_error_code(getattr(exc, "code", None), "DOCUMENT_NOT_FOUND")
            ) from exc
        markdown = str(document.get("markdown") or "")
        headings = [
            {
                "level": len(match.group(1)),
                "title": re.sub(r"\s+#+\s*$", "", match.group(2)).strip()[
                    :MAX_OUTLINE_HEADING_CHARS
                ],
            }
            for match in re.finditer(r"^(#{1,6})\s+(.+?)\s*$", markdown, re.MULTILINE)
        ][:MAX_OUTLINE_HEADINGS]
        return AskToolResult(
            value=self._bounded(
                {
                    "documentId": str(document_id),
                    "title": str(document.get("title", ""))[:256],
                    "kind": document.get("kind"),
                    "version": document.get("currentContentVersion"),
                    "headings": headings,
                }
            ),
            hit_count=1,
        )

    async def execute(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        actor: str,
        kb_id: str,
        scope: object | None,
    ) -> AskToolResult:
        if not isinstance(arguments, dict):
            raise AskToolError("INVALID_ARGUMENT")
        if name == "search_knowledge":
            return await self._search(actor, kb_id, arguments, scope)
        if name == "list_dir":
            return await self._list_dir(actor, kb_id, arguments, scope)
        if name == "get_document_outline":
            return await self._document_outline(actor, kb_id, arguments, scope)
        raise AskToolError("UNKNOWN_TOOL")


__all__ = [
    "ASK_TOOL_DEFINITIONS",
    "AskToolError",
    "AskToolExecutor",
    "AskToolResult",
    "MAX_QUOTE_CHARS",
    "MAX_TOOL_RESULTS",
]
