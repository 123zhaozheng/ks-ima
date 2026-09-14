"""Membership-gated target retrieval and private grounded conversations."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.application.ask_tools import (
    ASK_TOOL_DEFINITIONS,
    AskToolError,
    AskToolExecutor,
)
from ima.application.knowledge import effective_user_id, kb_membership, role_permits
from ima.application.mcp_contracts import McpActor
from ima.application.model_governance import ModelGovernanceError, ModelGovernanceService
from ima.domain.authorization import KbAction, KbRole
from ima.domain.model_governance import (
    EmbeddingConfig,
    GroundedAskConfig,
    RerankingConfig,
    Workflow,
    parse_profile_config,
)

logger = logging.getLogger(__name__)


class SearchError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code, self.code, self.detail = status_code, code, detail


@dataclass(frozen=True, slots=True)
class AskScope:
    """Retrieval scope for grounded Ask: one folder subtree or one document."""

    folder_id: str | None = None
    document_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class BoundedAskResult:
    conversation_id: UUID
    message_id: UUID
    status: str
    answer: str
    citations: tuple[dict[str, object], ...]


MAX_AGENT_ROUNDS = 6
MAX_AGENT_HISTORY_CHARS = 12000
MAX_AGENT_CONTEXT_CHARS = 60000
MAX_AGENT_ARGUMENT_CHARS = 8000
MAX_AGENT_TOOL_SECONDS = 15
MAX_AGENT_TOOL_CALLS_PER_ROUND = 4
MAX_AGENT_TOOL_CALLS = 12
MAX_AGENT_TOOL_SECONDS_TOTAL = 45
MAX_AGENT_DELTA_CHARS = 512
MAX_CITATION_PENDING_CHARS = 256
# The search pool is already up to 5x the requested top-k; double it before
# application-side stable ordering so HNSW ties near that cutoff are retained.
VECTOR_CANDIDATE_OVERFETCH_FACTOR = 2
AGENT_SYSTEM_PROMPT = """You are the grounded knowledge-base assistant.
Use the provided knowledge tools for factual claims. Treat tool output as the
only source of truth, cite source chunks with their supplied [rank] markers,
and never invent a citation or use a chunk that a tool did not return. The
request's knowledge-base and folder/document scope is immutable. If a tool is
denied or returns no results, say so plainly instead of trying to work around
the boundary. Directory outlines describe structure, not source evidence.
"""

# Citation syntax is deliberately kept small and ASCII-canonical at the
# boundary. The accepted input variants are plain/nested brackets, full-width
# digits, bracket HTML entities, and a numeric Markdown link (with optional
# whitespace before the URL). Every accepted marker is emitted as ``[n]``.
_CITATION_MARKER_RE = re.compile(r"\[(?:\[([0-9０-９]+)\]|([0-9０-９]+))\]")
_CITATION_BRACKET_ENTITY_RE = re.compile(
    r"&(?:#(?:91|93);|#x(?:5b|5d);|(?:lbrack|rbrack|lsqb|rsqb);)", re.IGNORECASE
)
_CITATION_NUMERIC_ENTITY_RE = re.compile(r"&#(?:x([0-9a-f]+)|([0-9]+));", re.IGNORECASE)
_CITATION_ENTITY_PREFIXES = (
    "&#91;",
    "&#93;",
    "&#x5b;",
    "&#x5d;",
    "&lbrack;",
    "&rbrack;",
    "&lsqb;",
    "&rsqb;",
)


def _canonical_digits(value: str) -> str:
    return "".join(
        chr(ord(char) - ord("０") + ord("0")) if "０" <= char <= "９" else char for char in value
    )


def _decode_citation_syntax(value: str) -> tuple[str, tuple[int, ...]]:
    """Decode only citation syntax and retain source offsets for streaming."""
    decoded: list[str] = []
    origins: list[int] = []
    cursor = 0
    while cursor < len(value):
        char = value[cursor]
        if char == "\\" and cursor + 1 < len(value) and value[cursor + 1] in "[]":
            decoded.append(value[cursor + 1])
            origins.append(cursor)
            cursor += 2
            continue
        entity = _CITATION_BRACKET_ENTITY_RE.match(value, cursor)
        if entity:
            token = entity.group(0).lower()
            decoded.append("[" if token in {"&#91;", "&#x5b;", "&lbrack;", "&lsqb;"} else "]")
            origins.append(cursor)
            cursor = entity.end()
            continue
        numeric = _CITATION_NUMERIC_ENTITY_RE.match(value, cursor)
        if numeric:
            codepoint = int(numeric.group(1), 16) if numeric.group(1) else int(numeric.group(2))
            if 48 <= codepoint <= 57 or 0xFF10 <= codepoint <= 0xFF19:
                decoded.append(chr(codepoint))
                origins.append(cursor)
                cursor = numeric.end()
                continue
        decoded.append(char)
        origins.append(cursor)
        cursor += 1
    return "".join(decoded), tuple(origins)


def _optional_citation_link_end(value: str, marker_end: int) -> int | None:
    cursor = marker_end
    while cursor < len(value) and value[cursor] in " \t\r\n":
        cursor += 1
    if cursor >= len(value) or value[cursor] != "(":
        return marker_end
    depth = 0
    while cursor < len(value):
        char = value[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return cursor + 1
        cursor += 1
    return None


def _ground_answer_text(answer: str, citations: list[dict[str, object]]) -> str:
    allowed = {rank for item in citations if isinstance(rank := item.get("rank"), int)}
    normalized, _ = _decode_citation_syntax(answer)
    result: list[str] = []
    cursor = 0
    for match in _CITATION_MARKER_RE.finditer(normalized):
        result.append(normalized[cursor : match.start()])
        rank = int(_canonical_digits(match.group(1) or match.group(2)))
        link_end = _optional_citation_link_end(normalized, match.end())
        end = match.end() if link_end is None else link_end
        if rank in allowed:
            result.append(f"[{rank}]")
        cursor = end
    result.append(normalized[cursor:])
    return "".join(result)


def _incomplete_citation_start(normalized: str) -> int | None:
    """Find a suffix that must wait for another upstream content chunk."""
    if normalized.endswith("\\"):
        return len(normalized) - 1
    for start in range(len(normalized) - 1, -1, -1):
        if normalized[start] != "[":
            continue
        match = _CITATION_MARKER_RE.match(normalized, start)
        if match:
            tail = normalized[match.end() :]
            if (not tail or tail.strip(" \t\r\n") == "") or (
                tail.lstrip(" \t\r\n").startswith("(")
                and (_optional_citation_link_end(normalized, match.end()) is None)
            ):
                while start > 0 and normalized[start - 1] == "[":
                    start -= 1
                return start
            continue
        if normalized.find("]", start + 1) == -1:
            while start > 0 and normalized[start - 1] == "[":
                start -= 1
            return start
    return None


def _incomplete_citation_entity_start(value: str) -> int | None:
    ampersand = value.rfind("&")
    if ampersand < 0:
        return None
    suffix = value[ampersand:].lower()
    if ";" in suffix:
        return None
    if any(entity.startswith(suffix) for entity in _CITATION_ENTITY_PREFIXES):
        return ampersand
    if re.fullmatch(r"&#(?:x[0-9a-f]*|[0-9]*)", suffix, re.IGNORECASE):
        return ampersand
    return None


class _CitationStreamFilter:
    """Filter grounded markers without waiting for the whole model response."""

    def __init__(self, citations: list[dict[str, object]]) -> None:
        self.citations = citations
        self._pending_chunks: deque[str] = deque()
        self._pending_length = 0

    @property
    def pending(self) -> str:
        """Expose the bounded suffix for diagnostics without using it internally."""
        return "".join(self._pending_chunks)

    def _clear_pending(self) -> None:
        self._pending_chunks.clear()
        self._pending_length = 0

    def _set_pending(self, value: str) -> None:
        self._clear_pending()
        if value:
            self._pending_chunks.append(value)
            self._pending_length = len(value)

    def _fallback_text(self, raw: str) -> str:
        """Flush an overlong candidate as ordinary text instead of retaining it."""
        normalized, _ = _decode_citation_syntax(raw)
        return _ground_answer_text(normalized, self.citations)

    def feed(self, content: str, *, final: bool = False) -> str:
        pending = "".join(self._pending_chunks)
        raw = pending + content if pending else content
        self._clear_pending()
        safe_end = len(raw)
        if not final:
            entity_start = _incomplete_citation_entity_start(raw)
            if entity_start is not None:
                safe_end = entity_start
        safe_raw = raw[:safe_end]
        normalized, origins = _decode_citation_syntax(safe_raw)
        if not final:
            incomplete = _incomplete_citation_start(normalized)
            if incomplete is not None:
                raw_start = origins[incomplete] if incomplete < len(origins) else safe_end
                candidate = raw[raw_start:]
                if len(candidate) > MAX_CITATION_PENDING_CHARS:
                    return self._fallback_text(raw)
                self._set_pending(candidate)
                normalized = normalized[:incomplete]
            else:
                trailing = raw[safe_end:]
                if len(trailing) > MAX_CITATION_PENDING_CHARS:
                    return self._fallback_text(raw)
                self._set_pending(trailing)
        return _ground_answer_text(normalized, self.citations)


def now() -> datetime:
    return datetime.now(UTC)


def _iso(value: object) -> object:
    """ISO 8601 for datetimes inside SSE payloads; anything else passes through."""
    return value.isoformat() if isinstance(value, datetime) else value


def sse(event: str, sequence: int, payload: dict[str, object]) -> bytes:
    data = json.dumps(payload, separators=(",", ":"))
    return f"id: {sequence}\nevent: {event}\ndata: {data}\n\n".encode()


def fuse_scores(
    keyword: dict[tuple[object, ...], float], vector: dict[tuple[object, ...], float], weight: float
) -> dict[tuple[object, ...], float]:
    """Normalize bounded candidate ranks and fuse them deterministically."""
    keys = set(keyword) | set(vector)
    if not keys:
        return {}
    maximum_keyword = max(keyword.values(), default=0.0)
    maximum_vector = max(vector.values(), default=0.0)
    result: dict[tuple[object, ...], float] = {}
    for key in keys:
        keyword_score = keyword.get(key, 0.0) / maximum_keyword if maximum_keyword else 0.0
        vector_score = vector.get(key, 0.0) / maximum_vector if maximum_vector else 0.0
        result[key] = (1.0 - weight) * keyword_score + weight * vector_score
    return result


def _index_source_digest(kb_id: str, model: Mapping[str, Any], source_rows: Sequence[Any]) -> str:
    source_material = "|".join(
        f"{row['document_id']}:{row['version']}:{row['generation']}:{row['ordinal']}:{row['content_digest']}"
        for row in source_rows
    )
    return sha256(
        f"{kb_id}:{model['id']}:{model['version']}:{model['embedding_dimension']}:{source_material}".encode()
    ).hexdigest()


def _validated_model_uuid(value: object) -> UUID:
    """Validate model metadata before it is interpolated into index DDL."""
    try:
        return UUID(str(value))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SearchError(
            503, "INVALID_MODEL_METADATA", "Embedding model metadata is invalid"
        ) from exc


class SearchService:
    def __init__(
        self,
        engine: AsyncEngine,
        models: ModelGovernanceService,
        kb_service: Any | None = None,
        knowledge_service: Any | None = None,
    ) -> None:
        self.engine, self.models = engine, models
        self.kb_service = kb_service
        self.knowledge_service = knowledge_service

    async def _profile(self, conn: AsyncConnection, kb_id: str) -> GroundedAskConfig:
        # Scene-only resolution: the knowledge base parameter is retained for
        # callers and audit context, but the platform scene defaults are the
        # sole source for every workflow's model.
        return await self._scene_profile()

    async def _scene_profile(self) -> GroundedAskConfig:
        """Compose a grounded profile from the platform scene defaults."""
        scene = await self.models.scene_default_config(Workflow.GROUNDED_ASK)
        if not scene:
            raise SearchError(409, "NO_ASSIGNMENT", "No grounded Ask profile is assigned")
        config = cast(GroundedAskConfig, parse_profile_config(scene, Workflow.GROUNDED_ASK))
        if not config.embedding_model_id:
            embedding = await self.models.scene_default_config(Workflow.EMBEDDING)
            if embedding:
                embedding_config = cast(
                    EmbeddingConfig, parse_profile_config(embedding, Workflow.EMBEDDING)
                )
                config = config.model_copy(
                    update={"embedding_model_id": embedding_config.embedding_model_id}
                )
        if not config.rerank_model_id:
            reranking = await self.models.scene_default_config(Workflow.RERANKING)
            if reranking:
                rerank_config = cast(
                    RerankingConfig, parse_profile_config(reranking, Workflow.RERANKING)
                )
                config = config.model_copy(
                    update={"rerank_model_id": rerank_config.rerank_model_id}
                )
        return config

    async def _require_kb(
        self,
        conn: AsyncConnection,
        actor: str | McpActor,
        kb_id: str,
        action: KbAction,
    ) -> str:
        """Require the actor's membership role to grant the action; return the kb name."""
        user_id = await effective_user_id(conn, actor)
        membership = await kb_membership(conn, user_id, kb_id) if user_id else None
        if not role_permits(membership[0] if membership else None, action):
            raise SearchError(404, "KB_NOT_FOUND", "Knowledge base not found")
        assert membership is not None
        return membership[1]

    async def _vector_target(
        self, conn: AsyncConnection, kb_id: str, config: GroundedAskConfig
    ) -> dict[str, Any]:
        if not config.embedding_model_id:
            raise SearchError(
                409, "REINDEX_REQUIRED", "The grounded profile has no embedding assignment"
            )
        row = (
            (
                await conn.execute(
                    text("""SELECT i.*,m.embedding_dimension FROM ima.chunk_search_indexes i
                    JOIN ima.governed_models m ON m.id=i.model_id
                    WHERE i.kb_id=:kb AND i.model_id=CAST(:model AS uuid)
                      AND i.model_version=m.version AND i.embedding_dimension=m.embedding_dimension
                      AND i.status='active'"""),
                    {"kb": kb_id, "model": config.embedding_model_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise SearchError(409, "REINDEX_REQUIRED", "An exact active vector index is required")
        return dict(row)

    async def _embedding_model(self, conn: AsyncConnection) -> dict[str, Any] | None:
        """Resolve the scene-default embedding model used to build vector indexes."""
        row = (
            (
                await conn.execute(
                    text("""SELECT m.id,m.version,m.embedding_dimension FROM ima.scene_defaults d
                    JOIN ima.capability_profiles p ON p.id=d.profile_id
                    JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=p.current_version AND v.state='published'
                    JOIN ima.governed_models m ON m.id=CAST(v.config->>'embeddingModelId' AS uuid)
                    WHERE d.workflow='embedding' AND p.lifecycle='active'
                      AND m.capability='embedding' AND m.enabled AND m.validated""")
                )
            )
            .mappings()
            .first()
        )
        if not row or not row["embedding_dimension"]:
            return None
        return dict(row)

    async def build_vector_index(self, actor: str, kb_id: str) -> dict[str, object]:
        """Build and atomically activate an exact-model HNSW index after owner checks."""
        async with self.engine.begin() as conn:
            user_id = await effective_user_id(conn, actor)
            membership = await kb_membership(conn, user_id, kb_id) if user_id else None
            if not membership or membership[0] != KbRole.OWNER.value:
                raise SearchError(404, "KB_NOT_FOUND", "Knowledge base not found")
            model = await self._embedding_model(conn)
        if not model:
            raise SearchError(409, "REINDEX_REQUIRED", "Embedding model is not ready")
        return await self._build_index_core(kb_id, model)

    async def maintain_vector_index(self, kb_id: str) -> dict[str, object] | None:
        """Authorization-free, idempotent index maintenance for ingestion/reconcile.

        Returns the activated (or already active) exact-model index, or ``None``
        when the KB has no scene-default embedding model or no exact-model ready
        chunks to index.
        """
        async with self.engine.connect() as conn:
            model = await self._embedding_model(conn)
            if not model:
                return None
            existing = (
                (
                    await conn.execute(
                        text("""SELECT id,source_count,source_digest FROM ima.chunk_search_indexes
                WHERE kb_id=:kb AND model_id=:model AND model_version=:version
                  AND embedding_dimension=:dimension AND status='active'"""),
                        {
                            "kb": kb_id,
                            "model": model["id"],
                            "version": model["version"],
                            "dimension": model["embedding_dimension"],
                        },
                    )
                )
                .mappings()
                .first()
            )
            source_rows = (
                (
                    await conn.execute(
                        text("""SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest
                        FROM ima.document_chunks c
                        JOIN ima.documents d ON d.id=c.document_id AND d.kb_id=c.kb_id
                        JOIN ima.document_file_versions fv
                          ON fv.document_id=d.id AND fv.version=d.current_version
                        WHERE c.kb_id=:kb AND d.lifecycle='active'
                          AND fv.object_state='verified' AND c.version=fv.version
                          AND c.generation=fv.generation AND c.embedding_status='ready'
                          AND c.model_id=:model AND c.model_version=:version
                          AND c.embedding_dimension=:dimension
                        ORDER BY c.document_id,c.version,c.generation,c.ordinal"""),
                        {
                            "kb": kb_id,
                            "model": model["id"],
                            "version": model["version"],
                            "dimension": model["embedding_dimension"],
                        },
                    )
                )
                .mappings()
                .all()
            )
            ready = len(source_rows)
            source_digest = _index_source_digest(kb_id, model, source_rows)
            if (
                existing
                and int(existing["source_count"] or 0) == ready
                and existing["source_digest"] == source_digest
            ):
                return {
                    "id": existing["id"],
                    "modelId": model["id"],
                    "modelVersion": model["version"],
                    "dimension": model["embedding_dimension"],
                    "status": "active",
                }
        if not ready:
            return None
        try:
            return await self._build_index_core(kb_id, model)
        except SearchError as exc:
            if exc.code == "INDEX_BUILD_IN_PROGRESS":
                return None
            raise

    async def kbs_missing_vector_index(self) -> list[str]:
        """Knowledge bases whose exact-model ready chunks lack a current index.

        Only KBs whose persisted embeddings already match the current
        scene-default embedding model are returned, so a stale scene-default
        switch surfaces as ``REINDEX_REQUIRED`` rather than an unbuildable loop.
        """
        async with self.engine.connect() as conn:
            details = (
                (
                    await conn.execute(
                        text("""SELECT c.kb_id,c.document_id,c.version,c.generation,c.ordinal,c.content_digest,
                            m.id AS model_id,m.version AS model_version,m.embedding_dimension
                        FROM ima.document_chunks c
                        JOIN ima.documents d ON d.id=c.document_id AND d.kb_id=c.kb_id AND d.lifecycle='active'
                        JOIN ima.document_file_versions fv ON fv.document_id=d.id AND fv.version=d.current_version
                        JOIN ima.scene_defaults sd ON sd.workflow='embedding'
                        JOIN ima.capability_profiles p ON p.id=sd.profile_id AND p.lifecycle='active'
                        JOIN ima.capability_profile_versions v ON v.profile_id=p.id AND v.version=p.current_version AND v.state='published'
                        JOIN ima.governed_models m ON m.id=CAST(v.config->>'embeddingModelId' AS uuid)
                        WHERE m.capability='embedding' AND m.enabled AND m.validated
                          AND fv.object_state='verified' AND c.version=fv.version
                          AND c.generation=fv.generation AND c.embedding_status='ready'
                          AND c.model_id=m.id AND c.model_version=m.version AND c.embedding_dimension=m.embedding_dimension
                        ORDER BY c.kb_id,c.document_id,c.version,c.generation,c.ordinal""")
                    )
                )
                .mappings()
                .all()
            )
            active_rows = (
                (
                    await conn.execute(
                        text("""SELECT kb_id,model_id,model_version,embedding_dimension,source_count,source_digest
                        FROM ima.chunk_search_indexes WHERE status='active'""")
                    )
                )
                .mappings()
                .all()
            )

        grouped: dict[str, list[dict[str, Any]]] = {}
        models: dict[str, dict[str, Any]] = {}
        for row in details:
            value = dict(row)
            key = str(value["kb_id"])
            grouped.setdefault(key, []).append(value)
            models[key] = {
                "id": value["model_id"],
                "version": value["model_version"],
                "embedding_dimension": value["embedding_dimension"],
            }
        active_by_model = {
            (
                str(row["kb_id"]),
                str(row["model_id"]),
                int(row["model_version"]),
                int(row["embedding_dimension"]),
            ): dict(row)
            for row in active_rows
        }
        missing: list[str] = []
        for kb_id, rows in grouped.items():
            model = models.get(kb_id)
            if not rows or model is None:
                continue
            active = active_by_model.get(
                (
                    kb_id,
                    str(model["id"]),
                    int(model["version"]),
                    int(model["embedding_dimension"]),
                )
            )
            expected_digest = _index_source_digest(kb_id, model, rows)
            current = (
                active is not None
                and str(active["model_id"]) == str(model["id"])
                and int(active["model_version"]) == int(model["version"])
                and int(active["embedding_dimension"]) == int(model["embedding_dimension"])
                and int(active["source_count"] or 0) == len(rows)
                and active["source_digest"] == expected_digest
            )
            if not current:
                missing.append(kb_id)
        return sorted(set(missing))

    async def _build_index_core(self, kb_id: str, model: dict[str, Any]) -> dict[str, object]:
        """Build and activate an exact-model HNSW index for a database-validated model.

        Shared by the owner-authorized HTTP route and the authorization-free
        ingestion/reconciliation path; all values come from persisted model
        metadata, never request data.
        """
        model_id = _validated_model_uuid(model["id"])
        async with self.engine.begin() as conn:
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"{kb_id}:{model_id}:{model['version']}:{model['embedding_dimension']}"},
            )
            source_rows = (
                (
                    await conn.execute(
                        text("""SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest
                        FROM ima.document_chunks c
                        JOIN ima.documents d ON d.id=c.document_id AND d.kb_id=c.kb_id
                        JOIN ima.document_file_versions fv
                          ON fv.document_id=d.id AND fv.version=d.current_version
                        WHERE c.kb_id=:kb AND d.lifecycle='active'
                          AND c.version=fv.version AND c.generation=fv.generation
                          AND fv.object_state='verified' AND c.embedding_status='ready'
                          AND c.model_id=:model AND c.model_version=:version
                          AND c.embedding_dimension=:dimension
                        ORDER BY c.document_id,c.version,c.generation,c.ordinal"""),
                        {
                            "kb": kb_id,
                            "model": model_id,
                            "version": model["version"],
                            "dimension": model["embedding_dimension"],
                        },
                    )
                )
                .mappings()
                .all()
            )
            count = len(source_rows)
            if not count:
                raise SearchError(409, "REINDEX_REQUIRED", "No exact-model embeddings are ready")
            building = await conn.scalar(
                text("""SELECT EXISTS(SELECT 1 FROM ima.chunk_search_indexes
                WHERE kb_id=:kb AND model_id=:model AND model_version=:version
                  AND embedding_dimension=:dimension AND status='building')"""),
                {
                    "kb": kb_id,
                    "model": model_id,
                    "version": model["version"],
                    "dimension": model["embedding_dimension"],
                },
            )
            if building:
                raise SearchError(
                    409, "INDEX_BUILD_IN_PROGRESS", "Vector index build is already running"
                )
            generation = int(
                await conn.scalar(
                    text("""SELECT COALESCE(max(generation),0)+1 FROM ima.chunk_search_indexes
                    WHERE kb_id=:kb AND model_id=:model AND model_version=:version AND embedding_dimension=:dimension"""),
                    {
                        "kb": kb_id,
                        "model": model_id,
                        "version": model["version"],
                        "dimension": model["embedding_dimension"],
                    },
                )
                or 1
            )
            index_name = (
                f"ix_cv_{sha256(kb_id.encode()).hexdigest()[:8]}_"
                f"{model_id.hex[:10]}_{model['version']}_"
                f"{model['embedding_dimension']}_{generation}"
            )
            index_id = uuid4()
            digest = _index_source_digest(kb_id, model, source_rows)
            current_pairs = sorted(
                {(int(row["version"]), int(row["generation"])) for row in source_rows}
            )
            await conn.execute(
                text("""INSERT INTO ima.chunk_search_indexes(id,kb_id,model_id,model_version,embedding_dimension,generation,index_name,status,source_count,source_digest,created_at)
                VALUES (:id,:kb,:model,:version,:dimension,:generation,:name,'building',:count,:digest,:now)"""),
                {
                    "id": index_id,
                    "kb": kb_id,
                    "model": model_id,
                    "version": model["version"],
                    "dimension": model["embedding_dimension"],
                    "generation": generation,
                    "name": index_name,
                    "count": count,
                    "digest": digest,
                    "now": now(),
                },
            )
        # Dimension and identifier originate from database-validated model metadata, never request data.
        kb_literal = kb_id.replace("'", "''")
        generation_predicate = " OR ".join(
            f"(version={version} AND generation={generation})"
            for version, generation in current_pairs
        )
        statement = f"""CREATE INDEX IF NOT EXISTS {index_name} ON ima.document_chunks USING hnsw
          ((embedding::vector({int(model["embedding_dimension"])})) vector_cosine_ops)
          WHERE kb_id='{kb_literal}' AND embedding_status='ready' AND model_id='{model_id}'::uuid
            AND model_version={int(model["version"])} AND embedding_dimension={int(model["embedding_dimension"])}
            AND ({generation_predicate})"""
        try:
            async with self.engine.connect() as raw_conn:
                autocommit_conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
                await autocommit_conn.execute(text(statement))
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE ima.chunk_search_indexes SET status='retired',retired_at=:now WHERE kb_id=:kb AND model_id=:model AND model_version=:version AND embedding_dimension=:dimension AND status='active'"
                    ),
                    {
                        "kb": kb_id,
                        "model": model["id"],
                        "version": model["version"],
                        "dimension": model["embedding_dimension"],
                        "now": now(),
                    },
                )
                await conn.execute(
                    text(
                        "UPDATE ima.chunk_search_indexes SET status='active',activated_at=:now WHERE id=:id AND status='building'"
                    ),
                    {"id": index_id, "now": now()},
                )
        except Exception as exc:
            async with self.engine.begin() as conn:
                await conn.execute(
                    text("UPDATE ima.chunk_search_indexes SET status='failed' WHERE id=:id"),
                    {"id": index_id},
                )
            raise SearchError(503, "INDEX_BUILD_FAILED", "Vector index build failed") from exc
        return {
            "id": index_id,
            "modelId": model_id,
            "modelVersion": model["version"],
            "dimension": model["embedding_dimension"],
            "sourceCount": count,
            "status": "active",
        }

    async def _keyword_candidates(
        self,
        conn: AsyncConnection,
        kb_id: str,
        query: str,
        folder_id: str | None,
        document_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = (
            (
                await conn.execute(
                    text("""SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest,left(c.text_content,4000) quote,d.title,
          ts_rank(c.search_vector, websearch_to_tsquery('ima.mixed', :query)) score
          FROM ima.document_chunks c JOIN ima.documents d ON d.id=c.document_id
            JOIN ima.document_file_versions fv ON fv.document_id=d.id AND fv.version=d.current_version
          WHERE c.kb_id=:kb AND d.kb_id=:kb AND d.lifecycle='active'
            AND fv.object_state='verified' AND c.version=fv.version AND c.generation=fv.generation
            AND EXISTS(SELECT 1 FROM ima.folders fd
              WHERE fd.id=d.folder_id AND fd.kb_id=d.kb_id AND fd.lifecycle='active')
            AND c.search_vector @@ websearch_to_tsquery('ima.mixed', :query)
            AND (CAST(:folder AS varchar(32)) IS NULL OR d.folder_id IN (
              SELECT descendant_id FROM ima.folder_closure
              WHERE kb_id=:kb AND ancestor_id=CAST(:folder AS varchar(32))))
            AND (CAST(:document AS uuid) IS NULL OR c.document_id=CAST(:document AS uuid))
          ORDER BY score DESC,d.id,c.version,c.generation,c.ordinal LIMIT :limit"""),
                    {
                        "query": query,
                        "kb": kb_id,
                        "folder": folder_id,
                        "document": document_id,
                        "limit": limit,
                    },
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def _vector_candidates(
        self,
        conn: AsyncConnection,
        kb_id: str,
        query_vector: tuple[float, ...],
        target: dict[str, Any],
        folder_id: str | None,
        document_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        dimension = int(target["embedding_dimension"])
        vector_literal = "[" + ",".join(format(value, ".9g") for value in query_vector) + "]"
        generation_rows = (
            (
                await conn.execute(
                    text("""SELECT DISTINCT c.version,c.generation
                    FROM ima.document_chunks c
                    JOIN ima.documents d ON d.id=c.document_id AND d.kb_id=c.kb_id
                    JOIN ima.document_file_versions fv
                      ON fv.document_id=d.id AND fv.version=d.current_version
                    WHERE c.kb_id=:kb AND d.kb_id=:kb AND d.lifecycle='active'
                      AND fv.object_state='verified' AND c.version=fv.version
                      AND c.generation=fv.generation AND c.embedding_status='ready'
                      AND c.model_id=:model AND c.model_version=:version
                      AND c.embedding_dimension=:dimension
                    ORDER BY c.version,c.generation"""),
                    {
                        "kb": kb_id,
                        "model": target["model_id"],
                        "version": target["model_version"],
                        "dimension": target["embedding_dimension"],
                    },
                )
            )
            .mappings()
            .all()
        )
        if not generation_rows:
            return []
        # These values are database materialized (and the KB is membership
        # checked by the caller), so literalizing them lets PostgreSQL prove
        # the HNSW partial-index predicate instead of treating them as join
        # parameters. Folder/document scope remains bound below.
        kb_literal = kb_id.replace("'", "''")
        model_literal = str(target["model_id"]).replace("'", "''")
        generation_predicate = " OR ".join(
            f"(c.version={int(row['version'])} AND c.generation={int(row['generation'])})"
            for row in generation_rows
        )
        candidate_limit = limit * VECTOR_CANDIDATE_OVERFETCH_FACTOR
        statement = f"""SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest,left(c.text_content,4000) quote,d.title,
          1-(c.embedding::vector({dimension}) <=> CAST(:vector AS vector({dimension}))) score
          FROM ima.document_chunks c JOIN ima.documents d ON d.id=c.document_id
            JOIN ima.document_file_versions fv ON fv.document_id=d.id AND fv.version=d.current_version
          WHERE c.kb_id='{kb_literal}' AND d.kb_id='{kb_literal}' AND d.lifecycle='active'
            AND fv.object_state='verified' AND c.version=fv.version AND c.generation=fv.generation
            AND EXISTS(SELECT 1 FROM ima.folders fd
              WHERE fd.id=d.folder_id AND fd.kb_id=d.kb_id AND fd.lifecycle='active')
            AND c.embedding_status='ready' AND c.model_id='{model_literal}'::uuid
            AND c.model_version={int(target["model_version"])}
            AND c.embedding_dimension={dimension} AND ({generation_predicate})
            AND (CAST(:folder AS varchar(32)) IS NULL OR d.folder_id IN (
              SELECT descendant_id FROM ima.folder_closure
              WHERE kb_id='{kb_literal}' AND ancestor_id=CAST(:folder AS varchar(32))))
            AND (CAST(:document AS uuid) IS NULL OR c.document_id=CAST(:document AS uuid))
          ORDER BY c.embedding::vector({dimension}) <=> CAST(:vector AS vector({dimension})) LIMIT :limit"""
        rows = (
            (
                await conn.execute(
                    text(statement),
                    {
                        "vector": vector_literal,
                        "folder": folder_id,
                        "document": document_id,
                        "limit": candidate_limit,
                    },
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def search(
        self,
        actor: str | McpActor,
        kb_id: str,
        query: str,
        *,
        mode: str = "keyword",
        top_k: int = 8,
        threshold: float = 0,
        folder_id: str | None = None,
        document_id: UUID | None = None,
        action: KbAction = KbAction.VIEW_CONTENT,
    ) -> dict[str, object]:
        if not query.strip() or len(query) > 4000:
            raise SearchError(422, "INVALID_QUERY", "Query is invalid")
        if mode not in {"keyword", "vector", "hybrid"}:
            raise SearchError(422, "INVALID_MODE", "Search mode is invalid")
        if folder_id and document_id:
            raise SearchError(422, "INVALID_SCOPE", "Scope accepts either folderId or documentId")
        top_k, threshold, pool = (
            max(1, min(top_k, 50)),
            max(0.0, min(threshold, 1.0)),
            min(max(top_k * 5, 20), 250),
        )
        async with self.engine.connect() as conn:
            await conn.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            config = await self._profile(conn, kb_id)
            await self._require_kb(conn, actor, kb_id, action)
            if folder_id:
                folder_exists = await conn.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ima.folders WHERE id=:folder AND kb_id=:kb AND lifecycle='active')"
                    ),
                    {"folder": folder_id, "kb": kb_id},
                )
                if not folder_exists:
                    raise SearchError(404, "FOLDER_NOT_FOUND", "Folder not found")
            if document_id:
                document_exists = await conn.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ima.documents WHERE id=CAST(:document AS uuid) AND kb_id=:kb AND lifecycle='active')"
                    ),
                    {"document": document_id, "kb": kb_id},
                )
                if not document_exists:
                    raise SearchError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            keyword_rows = (
                await self._keyword_candidates(conn, kb_id, query, folder_id, document_id, pool)
                if mode in {"keyword", "hybrid"}
                else []
            )
            vector_rows: list[dict[str, Any]] = []
            if mode in {"vector", "hybrid"}:
                target = await self._vector_target(conn, kb_id, config)
                vectors = await self.models.managed_embeddings(kb_id, [query])
                if (
                    len(vectors) != 1
                    or len(vectors[0]) != int(target["embedding_dimension"])
                    or not all(math.isfinite(item) for item in vectors[0])
                ):
                    raise SearchError(
                        503, "INVALID_EMBEDDING_RESPONSE", "Embedding response is invalid"
                    )
                vector_rows = await self._vector_candidates(
                    conn, kb_id, vectors[0], target, folder_id, document_id, pool
                )
            by_identity: dict[tuple[object, ...], dict[str, Any]] = {}
            keyword_scores: dict[tuple[object, ...], float] = {}
            vector_scores: dict[tuple[object, ...], float] = {}
            for row in keyword_rows:
                key = (
                    row["document_id"],
                    row["version"],
                    row["generation"],
                    row["ordinal"],
                    row["content_digest"],
                )
                by_identity[key] = row
                keyword_scores[key] = float(row["score"])
            for row in vector_rows:
                key = (
                    row["document_id"],
                    row["version"],
                    row["generation"],
                    row["ordinal"],
                    row["content_digest"],
                )
                by_identity[key] = row
                vector_scores[key] = float(row["score"])
            scores = (
                fuse_scores(keyword_scores, vector_scores, config.vector_weight)
                if mode == "hybrid"
                else keyword_scores or vector_scores
            )
            ordered = sorted(
                (key for key, value in scores.items() if value >= threshold),
                key=lambda key: (
                    -scores[key],
                    str(key[0]),
                    int(cast(int, key[1])),
                    int(cast(int, key[2])),
                    int(cast(int, key[3])),
                    str(key[4]),
                ),
            )[:pool]
            degraded: str | None = None
            if config.rerank_model_id and ordered:
                try:
                    reranked = await self.models.managed_rerank(
                        kb_id, query, [str(by_identity[key]["quote"]) for key in ordered]
                    )
                    values: dict[int, float] = {}
                    for index, score in reranked:
                        if (
                            index < 0
                            or index >= len(ordered)
                            or not math.isfinite(score)
                            or index in values
                        ):
                            raise ValueError
                        values[index] = score
                    if values:
                        ordered = sorted(
                            ordered,
                            key=lambda key: (
                                -values.get(ordered.index(key), float("-inf")),
                                -scores[key],
                                str(key[0]),
                                int(cast(int, key[1])),
                                int(cast(int, key[2])),
                                int(cast(int, key[3])),
                            ),
                        )
                except (ModelGovernanceError, ValueError):
                    degraded = "RERANK_UNAVAILABLE"
            # Membership already grants the whole tree; retrieval re-ran the
            # authorization check above, so ranked candidates stay visible.
            items = [
                self._result(by_identity[key], scores[key], rank)
                for rank, key in enumerate(ordered, 1)
            ][:top_k]
            return {"items": items, "degraded": degraded, "profileTopK": config.top_k}

    @staticmethod
    def _result(row: dict[str, Any], score: float, rank: int) -> dict[str, object]:
        return {
            "documentId": str(row["document_id"]),
            "documentVersion": row["version"],
            "fileGeneration": row["generation"],
            "chunkOrdinal": row["ordinal"],
            "chunkDigest": row["content_digest"],
            "title": row["title"],
            "quote": row["quote"],
            "score": score,
            "rank": rank,
        }

    async def list_conversations(self, actor: str) -> list[dict[str, object]]:
        """All conversations owned by the user, aggregated across knowledge bases."""
        async with self.engine.connect() as conn:
            rows = (
                (
                    await conn.execute(
                        text(
                            """SELECT c.id,c.kb_id,c.title,c.lifecycle,c.version,c.scope,c.created_at,c.updated_at,kb.name AS kb_name,
                            COALESCE(f.name,d.title) AS scope_title
                            FROM ima.conversations c JOIN ima.knowledge_bases kb ON kb.id=c.kb_id
                            LEFT JOIN ima.folders f ON f.kb_id=c.kb_id AND f.id=c.scope->>'folderId'
                            LEFT JOIN ima.documents d ON d.kb_id=c.kb_id AND d.id=CAST(c.scope->>'documentId' AS uuid)
                            WHERE c.owner_user_id=:owner ORDER BY c.updated_at DESC,c.id"""
                        ),
                        {"owner": actor},
                    )
                )
                .mappings()
                .all()
            )
            return [self._conversation(dict(row)) for row in rows]

    async def get_conversation(
        self, actor: str, kb_id: str, conversation_id: UUID
    ) -> dict[str, object]:
        async with self.engine.connect() as conn:
            await self._require_kb(conn, actor, kb_id, KbAction.VIEW_METADATA)
            conversation = await self._owned_conversation(conn, actor, kb_id, conversation_id)
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,role,status,content,sequence,version,created_at,updated_at,completed_at FROM ima.conversation_messages WHERE conversation_id=:id AND kb_id=:kb AND owner_user_id=:owner ORDER BY sequence"
                        ),
                        {"id": conversation_id, "kb": kb_id, "owner": actor},
                    )
                )
                .mappings()
                .all()
            )
            return {
                **self._conversation(conversation),
                "messages": [self._message(dict(row)) for row in rows],
            }

    async def _owned_conversation(
        self,
        conn: AsyncConnection,
        actor: str,
        kb_id: str,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text(
                        """SELECT c.*,kb.name AS kb_name,COALESCE(f.name,d.title) AS scope_title
                        FROM ima.conversations c
                        JOIN ima.knowledge_bases kb ON kb.id=c.kb_id
                        LEFT JOIN ima.folders f ON f.kb_id=c.kb_id AND f.id=c.scope->>'folderId'
                        LEFT JOIN ima.documents d ON d.kb_id=c.kb_id AND d.id=CAST(c.scope->>'documentId' AS uuid)
                        WHERE c.id=:id AND c.kb_id=:kb AND c.owner_user_id=:owner"""
                        + (" FOR UPDATE" if for_update else "")
                    ),
                    {"id": conversation_id, "kb": kb_id, "owner": actor},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise SearchError(404, "CONVERSATION_NOT_FOUND", "Conversation not found")
        return dict(row)

    async def update_conversation(
        self,
        actor: str,
        kb_id: str,
        conversation_id: UUID,
        title: str | None,
        archive: bool | None,
        expected_version: int,
    ) -> dict[str, object]:
        if title is not None and (not title.strip() or len(title) > 200):
            raise SearchError(422, "INVALID_TITLE", "Conversation title is invalid")
        async with self.engine.begin() as conn:
            await self._require_kb(conn, actor, kb_id, KbAction.VIEW_METADATA)
            row = await self._owned_conversation(
                conn, actor, kb_id, conversation_id, for_update=True
            )
            if int(row["version"]) != expected_version:
                raise SearchError(409, "VERSION_CONFLICT", "Conversation has changed")
            values = {
                "id": conversation_id,
                "title": title.strip() if title is not None else row["title"],
                "lifecycle": "archived"
                if archive
                else "active"
                if archive is not None
                else row["lifecycle"],
                "now": now(),
            }
            await conn.execute(
                text(
                    "UPDATE ima.conversations SET title=:title,lifecycle=:lifecycle,version=version+1,updated_at=:now WHERE id=:id"
                ),
                values,
            )
            row.update(values, version=int(row["version"]) + 1, updated_at=values["now"])
            return self._conversation(row)

    async def delete_conversation(
        self, actor: str, kb_id: str, conversation_id: UUID, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            await self._require_kb(conn, actor, kb_id, KbAction.VIEW_METADATA)
            row = await self._owned_conversation(
                conn, actor, kb_id, conversation_id, for_update=True
            )
            if int(row["version"]) != expected_version:
                raise SearchError(409, "VERSION_CONFLICT", "Conversation has changed")
            await conn.execute(
                text(
                    "DELETE FROM ima.message_citations WHERE message_id IN (SELECT id FROM ima.conversation_messages WHERE conversation_id=:id)"
                ),
                {"id": conversation_id},
            )
            await conn.execute(
                text("DELETE FROM ima.conversation_messages WHERE conversation_id=:id"),
                {"id": conversation_id},
            )
            await conn.execute(
                text("DELETE FROM ima.conversations WHERE id=:id AND owner_user_id=:owner"),
                {"id": conversation_id, "owner": actor},
            )

    async def retry(
        self,
        actor: str,
        kb_id: str,
        conversation_id: UUID,
        message_id: UUID,
        expected_version: int,
        scope: AskScope | None = None,
        agent: bool = False,
    ) -> AsyncIterator[bytes]:
        async with self.engine.connect() as conn:
            await self._require_kb(conn, actor, kb_id, KbAction.ASK)
            await self._owned_conversation(conn, actor, kb_id, conversation_id)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT content,version FROM ima.conversation_messages WHERE id=:id AND conversation_id=:conversation AND kb_id=:kb AND owner_user_id=:owner AND role='user'"
                        ),
                        {
                            "id": message_id,
                            "conversation": conversation_id,
                            "kb": kb_id,
                            "owner": actor,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row or int(row["version"]) != expected_version:
                raise SearchError(
                    409 if row else 404,
                    "VERSION_CONFLICT" if row else "MESSAGE_NOT_FOUND",
                    "Message is unavailable",
                )
            question = str(row["content"])
        # Scope validation against the pinned conversation scope happens in ask.
        if agent:
            return await self.ask(actor, kb_id, question, conversation_id, scope=scope, agent=True)
        return await self.ask(actor, kb_id, question, conversation_id, scope=scope)

    async def ask_bounded(
        self,
        actor: str,
        kb_id: str,
        question: str,
        conversation_id: UUID | None = None,
        *,
        max_answer_chars: int = 20000,
        max_citations: int = 20,
        timeout_seconds: float = 30,
    ) -> BoundedAskResult:
        """Run grounded Ask without SSE while preserving target persistence and membership."""
        if not question.strip() or len(question) > 20000:
            raise SearchError(422, "INVALID_QUESTION", "Question is invalid")
        if (
            not 1 <= max_answer_chars <= 100000
            or not 1 <= max_citations <= 50
            or not 0 < timeout_seconds <= 60
        ):
            raise SearchError(422, "INVALID_BOUNDS", "Ask bounds are invalid")
        async with self.engine.begin() as conn:
            kb_name = await self._require_kb(conn, actor, kb_id, KbAction.ASK)
            if conversation_id:
                conversation = await self._owned_conversation(conn, actor, kb_id, conversation_id)
                if conversation["lifecycle"] != "active":
                    raise SearchError(409, "CONVERSATION_ARCHIVED", "Conversation is archived")
            else:
                conversation = {
                    "id": uuid4(),
                    "kb_id": kb_id,
                    "kb_name": kb_name,
                    "owner_user_id": actor,
                    "title": question.strip()[:200],
                    "lifecycle": "active",
                    "version": 1,
                    "created_at": now(),
                    "updated_at": now(),
                }
                await conn.execute(
                    text(
                        "INSERT INTO ima.conversations(id,kb_id,owner_user_id,title,lifecycle,version,created_at,updated_at) VALUES (:id,:kb_id,:owner_user_id,:title,:lifecycle,:version,:created_at,:updated_at)"
                    ),
                    conversation,
                )
            sequence = int(
                await conn.scalar(
                    text(
                        "SELECT COALESCE(MAX(sequence),0)+1 FROM ima.conversation_messages WHERE conversation_id=:id"
                    ),
                    {"id": conversation["id"]},
                )
                or 1
            )
            user_id, assistant_id, timestamp = uuid4(), uuid4(), now()
            for values in (
                (user_id, "user", "completed", question, sequence),
                (assistant_id, "assistant", "pending", "", sequence + 1),
            ):
                await conn.execute(
                    text(
                        "INSERT INTO ima.conversation_messages(id,conversation_id,kb_id,owner_user_id,role,status,content,sequence,created_at,updated_at,completed_at) VALUES (:id,:conversation,:kb,:owner,:role,:status,:content,:sequence,:now,:now,:completed)"
                    ),
                    {
                        "id": values[0],
                        "conversation": conversation["id"],
                        "kb": kb_id,
                        "owner": actor,
                        "role": values[1],
                        "status": values[2],
                        "content": values[3],
                        "sequence": values[4],
                        "now": timestamp,
                        "completed": timestamp if values[1] == "user" else None,
                    },
                )
        try:
            async with asyncio.timeout(timeout_seconds):
                async with self.engine.connect() as conn:
                    config = await self._profile(conn, kb_id)
                results = await self.search(
                    actor,
                    kb_id,
                    question,
                    mode=config.retrieval_mode,
                    top_k=min(config.top_k, max_citations),
                    threshold=getattr(config, "score_threshold", 0.0),
                    action=KbAction.ASK,
                )
                citations = cast(list[dict[str, object]], results["items"])[:max_citations]
                if not citations:
                    answer = "I could not find relevant information in your accessible knowledge."
                    await self._complete(assistant_id, "knowledge_gap", answer)
                    return BoundedAskResult(
                        conversation_id=cast(UUID, conversation["id"]),
                        message_id=assistant_id,
                        status="knowledge_gap",
                        answer=answer,
                        citations=(),
                    )
                checked = await self.search(
                    actor,
                    kb_id,
                    question,
                    mode=config.retrieval_mode,
                    top_k=min(config.top_k, max_citations),
                    threshold=getattr(config, "score_threshold", 0.0),
                    action=KbAction.ASK,
                )
                checked_citations = cast(list[dict[str, object]], checked["items"])[:max_citations]
                if not checked_citations:
                    raise SearchError(403, "ACCESS_REVOKED", "Ask access was revoked")
                context = "\n\n".join(
                    f"[{item['rank']}] {str(item['quote'])[:2000]}" for item in checked_citations
                )[: getattr(config, "max_context_chars", 50000)]
                await self._persist_citations(assistant_id, checked_citations)
                await self._status(assistant_id, "streaming")
                response = await self.models.managed_chat(
                    kb_id,
                    Workflow.GROUNDED_ASK,
                    [
                        {
                            "role": "user",
                            "content": f"Answer only from these sources:\n{context}\n\nQuestion: {question}",
                        }
                    ],
                )
                choices = response.get("choices") if isinstance(response, dict) else None
                first = choices[0] if isinstance(choices, list) and choices else None
                message = first.get("message") if isinstance(first, dict) else None
                model_answer = message.get("content") if isinstance(message, dict) else None
                if (
                    not isinstance(model_answer, str)
                    or not model_answer.strip()
                    or len(model_answer) > max_answer_chars
                ):
                    raise SearchError(502, "INVALID_MODEL_RESPONSE", "Model response is invalid")
                final_check = await self.search(
                    actor,
                    kb_id,
                    question,
                    mode=config.retrieval_mode,
                    top_k=min(config.top_k, max_citations),
                    threshold=getattr(config, "score_threshold", 0.0),
                    action=KbAction.ASK,
                )
                final_ids = {
                    (item["documentId"], item["chunkDigest"])
                    for item in cast(list[dict[str, object]], final_check["items"])
                }
                if any(
                    (item["documentId"], item["chunkDigest"]) not in final_ids
                    for item in checked_citations
                ):
                    raise SearchError(403, "ACCESS_REVOKED", "Ask access was revoked")
                await self._complete(assistant_id, "completed", model_answer)
                return BoundedAskResult(
                    conversation_id=cast(UUID, conversation["id"]),
                    message_id=assistant_id,
                    status="completed",
                    answer=model_answer,
                    citations=tuple(checked_citations),
                )
        except asyncio.CancelledError:
            await asyncio.shield(self._complete(assistant_id, "cancelled", ""))
            raise
        except TimeoutError as exc:
            await self._complete(assistant_id, "failed", "")
            raise SearchError(504, "ASK_TIMEOUT", "Ask timed out") from exc
        except SearchError as exc:
            await self._complete(
                assistant_id, "cancelled" if exc.code == "ACCESS_REVOKED" else "failed", ""
            )
            raise
        except Exception:
            await self._complete(assistant_id, "failed", "")
            raise

    @staticmethod
    def _scope_row(scope: AskScope | None) -> dict[str, str] | None:
        """The persisted jsonb shape for a scope: exactly one target key."""
        if scope is None:
            return None
        if scope.folder_id:
            return {"folderId": scope.folder_id}
        if scope.document_id:
            return {"documentId": str(scope.document_id)}
        return None

    async def _conversation_history(
        self,
        conn: AsyncConnection,
        conversation_id: UUID,
        *,
        actor: str,
        kb_id: str,
    ) -> list[dict[str, str]]:
        """Return the newest bounded user/assistant turns for an agent request."""
        rows = (
            (
                await conn.execute(
                    text(
                        """SELECT role,content FROM ima.conversation_messages
                        WHERE conversation_id=:conversation AND role IN ('user','assistant')
                          AND owner_user_id=:owner AND kb_id=:kb
                          AND status IN ('completed','knowledge_gap')
                        ORDER BY sequence"""
                    ),
                    {"conversation": conversation_id, "owner": actor, "kb": kb_id},
                )
            )
            .mappings()
            .all()
        )
        result: list[dict[str, str]] = []
        used = 0
        for row in reversed(rows):
            content = str(row["content"] or "").strip()
            role = str(row["role"])
            if role not in {"user", "assistant"} or not content:
                continue
            remaining = MAX_AGENT_HISTORY_CHARS - used
            if remaining <= 0:
                break
            content = content[-remaining:]
            result.append({"role": role, "content": content})
            used += len(content)
        result.reverse()
        return result

    @staticmethod
    def _bounded_agent_messages(
        messages: list[dict[str, Any]], budget: int
    ) -> list[dict[str, Any]]:
        """Keep valid model messages within a budget without splitting tool exchanges."""
        if not messages:
            return []
        budget = max(1024, min(int(budget), MAX_AGENT_CONTEXT_CHARS))
        system = dict(messages[0]) if messages[0].get("role") == "system" else None

        def bounded_copy(
            message: dict[str, Any], remaining: int
        ) -> tuple[dict[str, Any], int] | None:
            value = dict(message)
            content = value.get("content")
            overhead = len(
                json.dumps(
                    {key: item for key, item in value.items() if key != "content"},
                    ensure_ascii=True,
                    default=str,
                )
            )
            if remaining <= overhead:
                return None
            if isinstance(content, str):
                value["content"] = content[-(remaining - overhead) :]
                return value, overhead + len(value["content"])
            return value, overhead

        def full_cost(message: dict[str, Any]) -> int:
            content = message.get("content")
            return len(
                json.dumps(
                    {key: item for key, item in message.items() if key != "content"},
                    ensure_ascii=True,
                    default=str,
                )
            ) + (len(content) if isinstance(content, str) else 0)

        def tool_exchange(index: int) -> tuple[int, list[dict[str, Any]]] | None:
            """Return one complete assistant-tool group, or skip malformed groups."""
            assistant = messages[index]
            if assistant.get("role") != "assistant":
                return None
            raw_calls = assistant.get("tool_calls")
            if not isinstance(raw_calls, list) or not raw_calls:
                return None
            call_ids = {
                str(call.get("id"))
                for call in raw_calls
                if isinstance(call, dict) and call.get("id")
            }
            if len(call_ids) != len(raw_calls):
                return None
            group = [assistant]
            seen: set[str] = set()
            cursor = index + 1
            while cursor < len(messages) and messages[cursor].get("role") == "tool":
                tool_message = messages[cursor]
                tool_id = tool_message.get("tool_call_id")
                if not isinstance(tool_id, str) or tool_id not in call_ids or tool_id in seen:
                    break
                seen.add(tool_id)
                group.append(tool_message)
                cursor += 1
            if seen != call_ids:
                return None
            return cursor, group

        # Build atomic units first. A tool message that is not part of a
        # complete exchange is deliberately discarded rather than sent to the
        # gateway as an orphaned role=tool message.
        units: list[tuple[int, int, list[dict[str, Any]], bool]] = []
        index = 1 if system is not None else 0
        while index < len(messages):
            message = messages[index]
            if message.get("role") == "tool":
                index += 1
                continue
            exchange = tool_exchange(index)
            if exchange is not None:
                end, group = exchange
                units.append((index, end, group, True))
                index = end
                continue
            if message.get("role") == "assistant" and message.get("tool_calls"):
                # Malformed/incomplete tool groups are not valid standalone
                # assistant context either.
                index += 1
                continue
            units.append((index, index + 1, [message], False))
            index += 1

        result: list[dict[str, Any]] = []
        used = 0
        if system is not None:
            bounded_system = bounded_copy(system, budget)
            if bounded_system is not None:
                system, system_cost = bounded_system
                result.append(system)
                used += system_cost

        # The current question is not optional context.  Reserve space for the
        # newest user turn before filling the remainder with tool responses and
        # older history; otherwise a large tool result could evict the question
        # that the next model round is meant to answer.
        current_user_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if messages[index].get("role") == "user"
            ),
            None,
        )
        bounded_by_index: dict[int, dict[str, Any]] = {}
        if current_user_index is not None:
            remaining = budget - used
            current_user = bounded_copy(messages[current_user_index], remaining)
            if current_user is not None:
                value, cost = current_user
                bounded_by_index[current_user_index] = value
                used += cost

        bounded_tail: list[tuple[int, dict[str, Any]]] = []
        for start, _end, unit, atomic in reversed(units):
            if (
                start
                <= (current_user_index if current_user_index is not None else -1)
                < start + len(unit)
            ):
                continue
            remaining = budget - used
            if remaining <= 0:
                break
            if atomic and sum(full_cost(message) for message in unit) > remaining:
                # Do not retain only the assistant or only some of its tool
                # results. The exchange is useful only when structurally whole.
                continue
            if atomic:
                copies = [dict(message) for message in unit]
                cost = sum(full_cost(message) for message in copies)
                bounded_tail.extend((start + offset, value) for offset, value in enumerate(copies))
                used += cost
                continue
            item = bounded_copy(unit[0], remaining)
            if item is None:
                continue
            value, cost = item
            bounded_tail.append((start, value))
            used += cost
        bounded_by_index.update(dict(bounded_tail))
        result.extend(value for index, value in sorted(bounded_by_index.items()))
        return result

    @staticmethod
    def _tool_argument_summary(arguments: str) -> dict[str, object]:
        """Expose a small, safe trace projection rather than raw JSON arguments."""
        try:
            parsed = json.loads(arguments)
        except (TypeError, json.JSONDecodeError):
            return {"invalid": True}
        if not isinstance(parsed, dict):
            return {"invalid": True}
        summary: dict[str, object] = {}
        for key, value in list(parsed.items())[:8]:
            if isinstance(value, str):
                summary[str(key)] = value[:160]
            elif isinstance(value, int | float | bool) or value is None:
                summary[str(key)] = value
            else:
                summary[str(key)] = "[bounded]"
        return summary

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
    def _ground_answer(answer: str, citations: list[dict[str, object]]) -> str:
        """Keep only canonical citation markers backed by tool evidence."""
        return _ground_answer_text(answer, citations)

    @staticmethod
    def _answer_chunks(answer: str) -> tuple[str, ...]:
        return tuple(
            answer[index : index + MAX_AGENT_DELTA_CHARS]
            for index in range(0, len(answer), MAX_AGENT_DELTA_CHARS)
        )

    async def ask(
        self,
        actor: str,
        kb_id: str,
        question: str,
        conversation_id: UUID | None,
        scope: AskScope | None = None,
        agent: bool = False,
    ) -> AsyncIterator[bytes]:
        if not question.strip() or len(question) > 20000:
            raise SearchError(422, "INVALID_QUESTION", "Question is invalid")
        # An empty scope object means the whole knowledge base, same as no scope.
        requested = scope if scope and (scope.folder_id or scope.document_id) else None
        history: list[dict[str, str]] = []
        async with self.engine.begin() as conn:
            kb_name = await self._require_kb(conn, actor, kb_id, KbAction.ASK)
            if conversation_id:
                conversation = await self._owned_conversation(conn, actor, kb_id, conversation_id)
                if conversation["lifecycle"] != "active":
                    raise SearchError(409, "CONVERSATION_ARCHIVED", "Conversation is archived")
                effective_scope = self._persisted_scope(conversation)
                if requested is not None and requested != effective_scope:
                    raise SearchError(409, "SCOPE_MISMATCH", "The conversation scope cannot change")
                # Scope targets can be deleted after creation; revalidate before
                # any message is written so a stale scope fails without partial state.
                if effective_scope is not None:
                    await self._resolve_scope_title(conn, kb_id, effective_scope)
            else:
                scope_title = (
                    await self._resolve_scope_title(conn, kb_id, requested) if requested else None
                )
                conversation = {
                    "id": uuid4(),
                    "kb_id": kb_id,
                    "kb_name": kb_name,
                    "owner_user_id": actor,
                    "title": question.strip()[:200],
                    "lifecycle": "active",
                    "version": 1,
                    "scope": self._scope_row(requested),
                    "scope_title": scope_title,
                    "created_at": now(),
                    "updated_at": now(),
                }
                await conn.execute(
                    text(
                        "INSERT INTO ima.conversations(id,kb_id,owner_user_id,title,lifecycle,version,created_at,updated_at,scope) VALUES (:id,:kb_id,:owner_user_id,:title,:lifecycle,:version,:created_at,:updated_at,CAST(:scope AS jsonb))"
                    ),
                    {
                        **conversation,
                        "scope": (
                            json.dumps(conversation["scope"]) if conversation["scope"] else None
                        ),
                    },
                )
                effective_scope = requested
            if agent:
                history = await self._conversation_history(
                    conn,
                    cast(UUID, conversation["id"]),
                    actor=actor,
                    kb_id=kb_id,
                )
            sequence = int(
                await conn.scalar(
                    text(
                        "SELECT COALESCE(MAX(sequence),0)+1 FROM ima.conversation_messages WHERE conversation_id=:id"
                    ),
                    {"id": conversation["id"]},
                )
                or 1
            )
            user_id, assistant_id, timestamp = uuid4(), uuid4(), now()
            for values in (
                (user_id, "user", "completed", question, sequence),
                (assistant_id, "assistant", "pending", "", sequence + 1),
            ):
                await conn.execute(
                    text(
                        "INSERT INTO ima.conversation_messages(id,conversation_id,kb_id,owner_user_id,role,status,content,sequence,created_at,updated_at,completed_at) VALUES (:id,:conversation,:kb,:owner,:role,:status,:content,:sequence,:now,:now,:completed)"
                    ),
                    {
                        "id": values[0],
                        "conversation": conversation["id"],
                        "kb": kb_id,
                        "owner": actor,
                        "role": values[1],
                        "status": values[2],
                        "content": values[3],
                        "sequence": values[4],
                        "now": timestamp,
                        "completed": timestamp if values[1] == "user" else None,
                    },
                )
        scope_folder = effective_scope.folder_id if effective_scope else None
        scope_document = effective_scope.document_id if effective_scope else None

        async def stream() -> AsyncIterator[bytes]:
            event_sequence = 1
            base: dict[str, object] = {
                "conversationId": str(conversation["id"]),
                "messageId": str(assistant_id),
            }
            yield sse(
                "conversation",
                event_sequence,
                {**base, "conversation": self._conversation(conversation)},
            )
            event_sequence += 1
            yield sse("message", event_sequence, {**base, "status": "pending"})
            event_sequence += 1
            if agent:
                yield sse("retrieving", event_sequence, {**base, "status": "retrieving"})
                event_sequence += 1
            agent_event_sequence = [event_sequence]
            agent_terminal = ["completed"]
            try:
                # Keep all retrieval work in the generator so the conversation,
                # message, and progress frames reach the client first.
                async with self.engine.connect() as conn:
                    ask_config = await self._profile(conn, kb_id)
                if agent:
                    async for frame in self._agent_loop(
                        actor,
                        kb_id,
                        question,
                        effective_scope,
                        assistant_id,
                        history,
                        ask_config,
                        base,
                        agent_event_sequence,
                        agent_terminal,
                    ):
                        yield frame
                    event_sequence = agent_event_sequence[0]
                    if agent_terminal[0] != "completed":
                        return
                    yield sse("completed", event_sequence, {**base, "status": "completed"})
                    return
                retrieval_mode = ask_config.retrieval_mode
                score_threshold = getattr(ask_config, "score_threshold", 0.0)
                results = await self.search(
                    actor,
                    kb_id,
                    question,
                    mode=retrieval_mode,
                    top_k=ask_config.top_k,
                    threshold=score_threshold,
                    folder_id=scope_folder,
                    document_id=scope_document,
                    action=KbAction.ASK,
                )
                citations = cast(list[dict[str, object]], results["items"])
                if not citations:
                    answer = (
                        "该范围下未找到相关内容。"
                        if effective_scope
                        else "I could not find relevant information in your accessible knowledge."
                    )
                    await self._complete(assistant_id, "knowledge_gap", answer)
                    yield sse(
                        "knowledge_gap", event_sequence, {**base, "answer": answer, "citations": []}
                    )
                    return
                checked = await self.search(
                    actor,
                    kb_id,
                    question,
                    mode=retrieval_mode,
                    top_k=ask_config.top_k,
                    threshold=score_threshold,
                    folder_id=scope_folder,
                    document_id=scope_document,
                    action=KbAction.ASK,
                )
                checked_citations = cast(list[dict[str, object]], checked["items"])
                if not checked_citations:
                    await self._complete(assistant_id, "cancelled", "")
                    yield sse("cancelled", event_sequence, {**base, "code": "ACCESS_REVOKED"})
                    return
                await self._persist_citations(assistant_id, checked_citations)
                yield sse("citations", event_sequence, {**base, "citations": checked_citations})
                event_sequence += 1
                await self._status(assistant_id, "streaming")
                context = "\n\n".join(
                    f"[{item['rank']}] {item['quote']}" for item in checked_citations
                )[: getattr(ask_config, "max_context_chars", 50000)]
                answer = ""
                delta_buffer = bytearray()
                async for raw in self.models.managed_chat_stream(
                    kb_id,
                    Workflow.GROUNDED_ASK,
                    [
                        {
                            "role": "user",
                            "content": f"Answer only from these sources:\n{context}\n\nQuestion: {question}",
                        }
                    ],
                ):
                    for delta in self._deltas(raw, delta_buffer):
                        answer += delta
                        yield sse("delta", event_sequence, {**base, "delta": delta})
                        event_sequence += 1
                for delta in self._deltas(b"", delta_buffer, final=True):
                    answer += delta
                    yield sse("delta", event_sequence, {**base, "delta": delta})
                    event_sequence += 1
                await self._complete(assistant_id, "completed", answer)
                yield sse("completed", event_sequence, {**base, "status": "completed"})
            except asyncio.CancelledError:
                if agent:
                    await asyncio.shield(self._complete(assistant_id, "cancelled", ""))
                else:
                    await self._complete(assistant_id, "cancelled", "")
                raise
            except ModelGovernanceError as exc:
                await self._complete(assistant_id, "failed", "")
                yield sse(
                    "error",
                    agent_event_sequence[0] if agent else event_sequence,
                    {**base, "code": exc.code},
                )
            except SearchError as exc:
                await self._complete(assistant_id, "failed", "")
                yield sse(
                    "error",
                    agent_event_sequence[0] if agent else event_sequence,
                    {**base, "code": exc.code if agent else "STREAM_FAILED"},
                )
            except Exception:
                logger.exception(
                    "ask_stream_system_error",
                    extra={
                        "conversation_id": str(conversation["id"]),
                        "message_id": str(assistant_id),
                    },
                )
                await self._complete(assistant_id, "failed", "")
                yield sse(
                    "error",
                    agent_event_sequence[0] if agent else event_sequence,
                    {**base, "code": "STREAM_FAILED"},
                )

        return stream()

    @staticmethod
    def _agent_events(
        raw: bytes, buffer: bytearray, *, final: bool = False
    ) -> tuple[dict[str, object], ...]:
        """Decode content and incremental tool-call deltas from gateway SSE."""
        events: list[dict[str, object]] = []
        buffer.extend(raw)
        lines: list[bytes] = []
        while b"\n" in buffer:
            chunk_line, _, remainder = buffer.partition(b"\n")
            buffer[:] = remainder
            lines.append(bytes(chunk_line.rstrip(b"\r")))
        if final and buffer:
            lines.append(bytes(buffer).rstrip(b"\r"))
            buffer.clear()
        for line_bytes in lines:
            decoded_line = line_bytes.decode("utf-8", "ignore")
            if not decoded_line.startswith("data:"):
                continue
            data = decoded_line[5:].lstrip()
            if data == "[DONE]":
                continue
            try:
                payload = json.loads(data)
                choice = payload["choices"][0]
                delta = choice.get("delta") or {}
            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                continue
            content = delta.get("content")
            calls: list[dict[str, object]] = []
            raw_calls = delta.get("tool_calls") or []
            if isinstance(raw_calls, list):
                for raw_call in raw_calls:
                    if not isinstance(raw_call, dict):
                        continue
                    function = raw_call.get("function")
                    function = function if isinstance(function, dict) else {}
                    calls.append(
                        {
                            "index": raw_call.get("index", 0),
                            "id": raw_call.get("id"),
                            "name": function.get("name"),
                            "arguments": function.get("arguments", ""),
                        }
                    )
            if isinstance(content, str) or calls:
                events.append(
                    {
                        "content": content if isinstance(content, str) else "",
                        "toolCalls": tuple(calls),
                    }
                )
        return tuple(events)

    async def _final_authorize_citations(
        self,
        actor: str,
        kb_id: str,
        scope: AskScope | None,
        citations: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Re-check every tool citation immediately before persistence."""
        async with self.engine.connect() as conn:
            await self._require_kb(conn, actor, kb_id, KbAction.ASK)
            approved: list[dict[str, object]] = []
            for item in citations:
                row = (
                    (
                        await conn.execute(
                            text(
                                """SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest
                                FROM ima.document_chunks c
                                JOIN ima.documents d ON d.id=c.document_id AND d.kb_id=c.kb_id
                                JOIN ima.document_file_versions fv
                                  ON fv.document_id=d.id AND fv.version=d.current_version
                                LEFT JOIN ima.folders f
                                  ON f.id=d.folder_id AND f.kb_id=d.kb_id
                                WHERE c.kb_id=:kb AND d.lifecycle='active'
                                  AND fv.object_state='verified'
                                  AND c.version=fv.version AND c.generation=fv.generation
                                  AND f.lifecycle='active'
                                  AND c.document_id=CAST(:document AS uuid)
                                  AND c.version=:version AND c.generation IS NOT DISTINCT FROM :generation
                                  AND c.ordinal=:ordinal AND c.content_digest=:digest
                                  AND (CAST(:folder AS varchar(32)) IS NULL OR d.folder_id IN (
                                    SELECT descendant_id FROM ima.folder_closure
                                    WHERE kb_id=:kb AND ancestor_id=CAST(:folder AS varchar(32))))
                                  AND (CAST(:scoped_document AS uuid) IS NULL OR c.document_id=CAST(:scoped_document AS uuid))
                                LIMIT 1"""
                            ),
                            {
                                "kb": kb_id,
                                "document": item["documentId"],
                                "version": item["documentVersion"],
                                "generation": item["fileGeneration"],
                                "ordinal": item["chunkOrdinal"],
                                "digest": item["chunkDigest"],
                                "folder": scope.folder_id if scope else None,
                                "scoped_document": scope.document_id if scope else None,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if row:
                    approved.append({**item, "rank": len(approved) + 1})
            return approved

    async def _agent_loop(
        self,
        actor: str,
        kb_id: str,
        question: str,
        scope: AskScope | None,
        assistant_id: UUID,
        history: list[dict[str, str]],
        ask_config: object,
        base: dict[str, object],
        event_sequence: list[int],
        terminal_status: list[str] | None = None,
    ) -> AsyncIterator[bytes]:
        """Run bounded model → tool → model rounds and yield final SSE frames."""
        executor = AskToolExecutor(
            self,
            kb_service=getattr(self, "kb_service", None),
            knowledge_service=getattr(self, "knowledge_service", None),
            search_mode=str(getattr(ask_config, "retrieval_mode", "hybrid")),
            score_threshold=float(getattr(ask_config, "score_threshold", 0.0)),
        )
        context_limit = int(getattr(ask_config, "context_limit", 8192)) * 4
        context_limit = min(
            context_limit,
            int(getattr(ask_config, "max_context_chars", MAX_AGENT_CONTEXT_CHARS)),
        )
        budget = max(1024, min(context_limit, MAX_AGENT_CONTEXT_CHARS))
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": question},
        ]
        messages = self._bounded_agent_messages(messages, budget)
        total_tool_calls = 0
        total_tool_seconds = 0.0
        persisted_identities: set[tuple[object, ...]] = set()
        citations_sent = False

        async def authorize_and_emit_citations() -> list[dict[str, object]]:
            """Authorize current evidence and emit it before answer deltas."""
            nonlocal citations_sent
            citations = await self._final_authorize_citations(
                actor, kb_id, scope, executor.citations
            )
            if len(citations) != len(executor.citations):
                raise SearchError(403, "ACCESS_REVOKED", "Ask source access was revoked")
            if not citations:
                return []
            new_citations = [
                item
                for item in citations
                if self._citation_identity(item) not in persisted_identities
            ]
            if new_citations:
                await self._persist_citations(assistant_id, new_citations)
                persisted_identities.update(self._citation_identity(item) for item in new_citations)
            if not citations_sent or new_citations:
                yield_frame = sse("citations", event_sequence[0], {**base, "citations": citations})
                event_sequence[0] += 1
                # An async helper cannot yield directly to its caller, so stash
                # the frame in the local queue consumed immediately below.
                pending_citation_frames.append(yield_frame)
                citations_sent = True
            return citations

        pending_citation_frames: list[bytes] = []

        for round_number in range(1, MAX_AGENT_ROUNDS + 1):
            tool_calls: dict[int, dict[str, str]] = {}
            response_content: list[str] = []
            delta_buffer = bytearray()
            citations_for_round: list[dict[str, object]] = []
            if executor.citations:
                citations_for_round = await authorize_and_emit_citations()
                while pending_citation_frames:
                    yield pending_citation_frames.pop(0)
            stream_filter = (
                _CitationStreamFilter(citations_for_round) if citations_for_round else None
            )
            if stream_filter is not None:
                await self._status(assistant_id, "streaming")
            upstream = self.models.managed_chat_stream(
                kb_id,
                Workflow.GROUNDED_ASK,
                messages,
                tools=[dict(tool) for tool in ASK_TOOL_DEFINITIONS],
            )
            try:
                async for raw in upstream:
                    for event in self._agent_events(raw, delta_buffer):
                        content = event.get("content")
                        if isinstance(content, str) and content:
                            response_content.append(content)
                            if stream_filter is not None:
                                delta = stream_filter.feed(content)
                                if delta:
                                    yield sse(
                                        "delta",
                                        event_sequence[0],
                                        {**base, "delta": delta},
                                    )
                                    event_sequence[0] += 1
                        for raw_call in cast(tuple[dict[str, object], ...], event["toolCalls"]):
                            try:
                                index = int(str(raw_call.get("index", 0) or 0))
                            except (TypeError, ValueError):
                                index = 0
                            call = tool_calls.setdefault(
                                index,
                                {"id": "", "name": "", "arguments": ""},
                            )
                            if isinstance(raw_call.get("id"), str) and raw_call["id"]:
                                call["id"] = str(raw_call["id"])
                            if isinstance(raw_call.get("name"), str) and raw_call["name"]:
                                call["name"] = str(raw_call["name"])
                            arguments = raw_call.get("arguments")
                            if isinstance(arguments, str):
                                call["arguments"] = (call["arguments"] + arguments)[
                                    :MAX_AGENT_ARGUMENT_CHARS
                                ]
                for event in self._agent_events(b"", delta_buffer, final=True):
                    content = event.get("content")
                    if isinstance(content, str) and content:
                        response_content.append(content)
                        if stream_filter is not None:
                            delta = stream_filter.feed(content)
                            if delta:
                                yield sse(
                                    "delta",
                                    event_sequence[0],
                                    {**base, "delta": delta},
                                )
                                event_sequence[0] += 1
                        for raw_call in cast(tuple[dict[str, object], ...], event["toolCalls"]):
                            try:
                                index = int(str(raw_call.get("index", 0) or 0))
                            except (TypeError, ValueError):
                                index = 0
                            call = tool_calls.setdefault(
                                index, {"id": "", "name": "", "arguments": ""}
                            )
                            if isinstance(raw_call.get("id"), str) and raw_call["id"]:
                                call["id"] = str(raw_call["id"])
                            if isinstance(raw_call.get("name"), str) and raw_call["name"]:
                                call["name"] = str(raw_call["name"])
                            arguments = raw_call.get("arguments")
                            if isinstance(arguments, str):
                                call["arguments"] = (call["arguments"] + arguments)[
                                    :MAX_AGENT_ARGUMENT_CHARS
                                ]
            finally:
                close = getattr(upstream, "aclose", None)
                if close is not None:
                    await close()

            if not tool_calls:
                citations = await authorize_and_emit_citations()
                while pending_citation_frames:
                    yield pending_citation_frames.pop(0)
                if not citations:
                    answer = (
                        "该范围下未找到相关内容。"
                        if scope
                        else "I could not find relevant information in your accessible knowledge."
                    )
                    await self._complete(assistant_id, "knowledge_gap", answer)
                    if terminal_status is not None:
                        terminal_status[0] = "knowledge_gap"
                    yield sse(
                        "knowledge_gap",
                        event_sequence[0],
                        {**base, "answer": answer, "citations": []},
                    )
                    event_sequence[0] += 1
                    return
                if stream_filter is not None:
                    delta = stream_filter.feed("", final=True)
                    if delta:
                        yield sse(
                            "delta",
                            event_sequence[0],
                            {**base, "delta": delta},
                        )
                        event_sequence[0] += 1
                answer = self._ground_answer("".join(response_content), citations)
                await self._complete(
                    assistant_id,
                    "completed",
                    answer,
                )
                return

            if len(tool_calls) > MAX_AGENT_TOOL_CALLS_PER_ROUND:
                raise SearchError(
                    429,
                    "AGENT_TOOL_LIMIT",
                    "Ask tool loop exceeded its per-round call limit",
                )
            if total_tool_calls + len(tool_calls) > MAX_AGENT_TOOL_CALLS:
                raise SearchError(
                    429,
                    "AGENT_TOOL_LIMIT",
                    "Ask tool loop exceeded its request call limit",
                )
            total_tool_calls += len(tool_calls)
            assistant_tool_calls: list[dict[str, object]] = []
            tool_messages: list[dict[str, object]] = []
            for index in sorted(tool_calls):
                call = tool_calls[index]
                call_id = call["id"] or f"ask-tool-{round_number}-{index}"
                name = call["name"] or "unknown"
                arguments_text = call["arguments"][:MAX_AGENT_ARGUMENT_CHARS]
                try:
                    arguments = json.loads(arguments_text) if arguments_text else {}
                except json.JSONDecodeError:
                    arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                loop = asyncio.get_running_loop()
                started = loop.time()
                remaining_seconds = MAX_AGENT_TOOL_SECONDS_TOTAL - total_tool_seconds
                if remaining_seconds <= 0:
                    raise SearchError(
                        429,
                        "AGENT_TOOL_TIMEOUT",
                        "Ask tool loop exceeded its total tool time limit",
                    )
                try:
                    async with asyncio.timeout(min(MAX_AGENT_TOOL_SECONDS, remaining_seconds)):
                        result = await executor.execute(
                            name,
                            arguments,
                            actor=actor,
                            kb_id=kb_id,
                            scope=scope,
                        )
                    tool_payload = result.value
                    hit_count = result.hit_count
                except AskToolError as exc:
                    tool_payload = {"error": exc.code}
                    hit_count = 0
                except TimeoutError:
                    logger.exception(
                        "ask_tool_timeout",
                        extra={"tool_name": name, "round": round_number},
                    )
                    await self._complete(assistant_id, "failed", "")
                    if terminal_status is not None:
                        terminal_status[0] = "failed"
                    yield sse(
                        "error",
                        event_sequence[0],
                        {**base, "code": "TOOL_TIMEOUT"},
                    )
                    return
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "ask_tool_system_error",
                        extra={"tool_name": name, "round": round_number},
                    )
                    await self._complete(assistant_id, "failed", "")
                    if terminal_status is not None:
                        terminal_status[0] = "failed"
                    yield sse(
                        "error",
                        event_sequence[0],
                        {**base, "code": "TOOL_FAILED"},
                    )
                    return
                finally:
                    total_tool_seconds += loop.time() - started
                assistant_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arguments_text},
                    }
                )
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": json.dumps(tool_payload, ensure_ascii=True, default=str),
                    }
                )
                yield sse(
                    "tool_call",
                    event_sequence[0],
                    {
                        **base,
                        "name": name,
                        "arguments": self._tool_argument_summary(arguments_text),
                        "argumentsSummary": self._tool_argument_summary(arguments_text),
                        "hitCount": hit_count,
                        "round": round_number,
                    },
                )
                event_sequence[0] += 1
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(response_content) or None,
                    "tool_calls": assistant_tool_calls,
                }
            )
            messages.extend(tool_messages)
            await authorize_and_emit_citations()
            while pending_citation_frames:
                yield pending_citation_frames.pop(0)
            messages = self._bounded_agent_messages(messages, budget)
            if round_number == MAX_AGENT_ROUNDS:
                # A loop that only produced tool errors or structural results
                # has no source evidence from which a grounded answer could be
                # made. Treat the cap as a knowledge gap, not an internal error.
                citations = await authorize_and_emit_citations()
                while pending_citation_frames:
                    yield pending_citation_frames.pop(0)
                if not citations:
                    answer = (
                        "该范围下未找到相关内容。"
                        if scope
                        else "I could not find relevant information in your accessible knowledge."
                    )
                    await self._complete(assistant_id, "knowledge_gap", answer)
                    if terminal_status is not None:
                        terminal_status[0] = "knowledge_gap"
                    yield sse(
                        "knowledge_gap",
                        event_sequence[0],
                        {**base, "answer": answer, "citations": []},
                    )
                    event_sequence[0] += 1
                    return
                raise SearchError(502, "AGENT_MAX_ROUNDS", "Ask tool loop reached its round limit")

    async def _agent_error_completion(
        self, assistant_id: UUID, base: dict[str, object], event_sequence: int, code: str
    ) -> bytes:
        await self._complete(assistant_id, "failed", "")
        return sse("error", event_sequence, {**base, "code": code})

    @staticmethod
    def _deltas(
        raw: bytes, buffer: bytearray | None = None, *, final: bool = False
    ) -> tuple[str, ...]:
        """Decode complete upstream SSE data lines without losing split chunks."""
        values: list[str] = []
        pending = buffer if buffer is not None else bytearray()
        pending.extend(raw)
        while b"\n" in pending:
            line_bytes, _, remainder = pending.partition(b"\n")
            pending[:] = remainder
            line = line_bytes.rstrip(b"\r").decode("utf-8", "ignore")
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                value = json.loads(line[6:])["choices"][0].get("delta", {}).get("content")
            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, str) and value:
                values.append(value)
        if final and pending:
            line = bytes(pending).rstrip(b"\r").decode("utf-8", "ignore")
            pending.clear()
            if not line.startswith("data: ") or line == "data: [DONE]":
                return tuple(values)
            try:
                value = json.loads(line[6:])["choices"][0].get("delta", {}).get("content")
            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                return tuple(values)
            if isinstance(value, str) and value:
                values.append(value)
        return tuple(values)

    async def _status(self, message_id: UUID, status: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.conversation_messages SET status=:status,version=version+1,updated_at=:now WHERE id=:id"
                ),
                {"id": message_id, "status": status, "now": now()},
            )

    async def _complete(self, message_id: UUID, status: str, content: str) -> None:
        async with self.engine.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE ima.conversation_messages SET status=:status,content=:content,version=version+1,updated_at=:now,completed_at=:now WHERE id=:id"
                ),
                {"id": message_id, "status": status, "content": content, "now": now()},
            )

    async def _persist_citations(
        self, message_id: UUID, citations: list[dict[str, object]]
    ) -> None:
        async with self.engine.begin() as conn:
            for item in citations:
                await conn.execute(
                    text(
                        "INSERT INTO ima.message_citations(message_id,ordinal,document_id,document_version,file_generation,chunk_ordinal,chunk_digest,quote,rank,score,created_at) VALUES (:message,:ordinal,CAST(:document AS uuid),:version,:generation,:chunk,:digest,:quote,:rank,:score,:now)"
                    ),
                    {
                        "message": message_id,
                        "ordinal": item["rank"],
                        "document": item["documentId"],
                        "version": item["documentVersion"],
                        "generation": item["fileGeneration"],
                        "chunk": item["chunkOrdinal"],
                        "digest": item["chunkDigest"],
                        "quote": item["quote"],
                        "rank": item["rank"],
                        "score": item["score"],
                        "now": now(),
                    },
                )

    async def resolve_citation(
        self, actor: str, kb_id: str, message_id: UUID, ordinal: int
    ) -> dict[str, object]:
        async with self.engine.connect() as conn:
            await self._require_kb(conn, actor, kb_id, KbAction.VIEW_CONTENT)
            row = (
                (
                    await conn.execute(
                        text("""SELECT c.* FROM ima.message_citations c JOIN ima.conversation_messages m ON m.id=c.message_id
                JOIN ima.document_chunks chunk ON chunk.document_id=c.document_id AND chunk.version=c.document_version AND chunk.generation=c.file_generation AND chunk.ordinal=c.chunk_ordinal AND chunk.content_digest=c.chunk_digest
                WHERE c.message_id=:message AND c.ordinal=:ordinal AND m.kb_id=:kb AND m.owner_user_id=:owner"""),
                        {
                            "message": message_id,
                            "ordinal": ordinal,
                            "kb": kb_id,
                            "owner": actor,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row:
                raise SearchError(404, "CITATION_NOT_FOUND", "Citation not found")
            return {
                "documentId": row["document_id"],
                "documentVersion": row["document_version"],
                "fileGeneration": row["file_generation"],
                "chunkOrdinal": row["chunk_ordinal"],
                "chunkDigest": row["chunk_digest"],
                "quote": row["quote"],
                "rank": row["rank"],
                "score": row["score"],
            }

    async def _resolve_scope_title(
        self, conn: AsyncConnection, kb_id: str, scope: AskScope
    ) -> str | None:
        """Validate the scope target inside the knowledge base and return its title.

        Membership already grants the whole tree, so existence in this
        knowledge base is the authorization boundary for a scope target.
        """
        if scope.folder_id:
            title = await conn.scalar(
                text(
                    "SELECT name FROM ima.folders WHERE id=:folder AND kb_id=:kb AND lifecycle='active'"
                ),
                {"folder": scope.folder_id, "kb": kb_id},
            )
            if title is None:
                raise SearchError(404, "FOLDER_NOT_FOUND", "Folder not found")
            return str(title)
        if scope.document_id:
            title = await conn.scalar(
                text(
                    "SELECT title FROM ima.documents WHERE id=:document AND kb_id=:kb AND lifecycle='active'"
                ),
                {"document": scope.document_id, "kb": kb_id},
            )
            if title is None:
                raise SearchError(404, "DOCUMENT_NOT_FOUND", "Document not found")
            return str(title)
        return None

    @staticmethod
    def _persisted_scope(conversation: dict[str, Any]) -> AskScope | None:
        raw = conversation.get("scope")
        if isinstance(raw, str):
            raw = json.loads(raw) if raw else None
        if not isinstance(raw, dict):
            return None
        if raw.get("folderId"):
            return AskScope(folder_id=str(raw["folderId"]))
        if raw.get("documentId"):
            return AskScope(document_id=UUID(str(raw["documentId"])))
        return None

    @staticmethod
    def _scope_payload(row: dict[str, Any]) -> dict[str, object] | None:
        scope = SearchService._persisted_scope(row)
        if scope is None:
            return None
        payload: dict[str, object] = {}
        if scope.folder_id:
            payload["folderId"] = scope.folder_id
        if scope.document_id:
            payload["documentId"] = str(scope.document_id)
        title = row.get("scope_title")
        if title:
            payload["title"] = str(title)
        return payload

    @staticmethod
    def _conversation(row: dict[str, Any]) -> dict[str, object]:
        # SSE payloads go through plain json.dumps; emit the same string forms
        # the REST contract produces (uuid as str, timestamptz as ISO 8601).
        result: dict[str, object] = {
            "id": str(row["id"]),
            "kbId": row["kb_id"],
            "kbName": row.get("kb_name"),
            "title": row["title"],
            "lifecycle": row["lifecycle"],
            "version": row["version"],
            "createdAt": _iso(row["created_at"]),
            "updatedAt": _iso(row["updated_at"]),
        }
        # Scope stays absent (not null) on unscoped conversations so the
        # default ask flow keeps its exact pre-scope event payload.
        scope = SearchService._scope_payload(row)
        if scope is not None:
            result["scope"] = scope
        return result

    @staticmethod
    def _message(row: dict[str, Any]) -> dict[str, object]:
        return {
            "id": row["id"],
            "role": row["role"],
            "status": row["status"],
            "content": row["content"],
            "sequence": row["sequence"],
            "version": row["version"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "completedAt": row["completed_at"],
        }
