"""ACL-first target retrieval and private grounded conversations."""

# ruff: noqa: E501

from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.application.authorization import WorkspaceService
from ima.application.mcp_contracts import McpActor
from ima.application.model_governance import ModelGovernanceError, ModelGovernanceService
from ima.domain.authorization import AclAction
from ima.domain.model_governance import GroundedAskConfig, Workflow, parse_profile_config
from ima.infrastructure.db.authorization import accessible_folder_ids


class SearchError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code, self.code, self.detail = status_code, code, detail


@dataclass(frozen=True, slots=True)
class BoundedAskResult:
    conversation_id: UUID
    message_id: UUID
    status: str
    answer: str
    citations: tuple[dict[str, object], ...]


def now() -> datetime:
    return datetime.now(UTC)


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


class SearchService:
    def __init__(
        self, engine: AsyncEngine, workspace: WorkspaceService, models: ModelGovernanceService
    ) -> None:
        self.engine, self.workspace, self.models = engine, workspace, models

    async def _profile(self, conn: AsyncConnection, workspace_id: str) -> GroundedAskConfig:
        row = (
            (
                await conn.execute(
                    text("""SELECT v.config FROM ima.workspace_profile_assignments a
                    JOIN ima.capability_profile_versions v ON v.profile_id=a.profile_id AND v.version=a.profile_version
                    JOIN ima.capability_profiles p ON p.id=a.profile_id
                    WHERE a.workspace_id=:workspace AND a.workflow='grounded_ask'
                      AND p.lifecycle='active' AND v.state='published'"""),
                    {"workspace": workspace_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise SearchError(409, "NO_ASSIGNMENT", "No grounded Ask profile is assigned")
        return cast(GroundedAskConfig, parse_profile_config(row["config"], Workflow.GROUNDED_ASK))

    async def _folders(
        self,
        conn: AsyncConnection,
        actor: str | McpActor,
        workspace_id: str,
        action: AclAction,
    ) -> set[str]:
        if isinstance(actor, McpActor):
            folders = await self.workspace.delegated_folder_ids(conn, actor, workspace_id, action)
            if not folders:
                raise SearchError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            return folders
        subject = (await self.workspace._require_member(conn, actor, workspace_id))["subject"]
        folders = await accessible_folder_ids(conn, subject, action)
        if not folders:
            raise SearchError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
        return folders

    async def _vector_target(
        self, conn: AsyncConnection, workspace_id: str, config: GroundedAskConfig
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
                    WHERE i.workspace_id=:workspace AND i.model_id=CAST(:model AS uuid)
                      AND i.model_version=m.version AND i.embedding_dimension=m.embedding_dimension
                      AND i.status='active'"""),
                    {"workspace": workspace_id, "model": config.embedding_model_id},
                )
            )
            .mappings()
            .first()
        )
        if not row:
            raise SearchError(409, "REINDEX_REQUIRED", "An exact active vector index is required")
        return dict(row)

    async def build_vector_index(self, actor: str, workspace_id: str) -> dict[str, object]:
        """Build and atomically activate an exact-model HNSW index after source verification."""
        async with self.engine.begin() as conn:
            membership = await self.workspace._require_member(conn, actor, workspace_id)
            if membership["role"] != "workspace_admin":
                raise SearchError(404, "WORKSPACE_NOT_FOUND", "Workspace not found")
            config = await self._profile(conn, workspace_id)
            if not config.embedding_model_id:
                raise SearchError(
                    409, "REINDEX_REQUIRED", "The grounded profile has no embedding assignment"
                )
            model = (
                (
                    await conn.execute(
                        text("""SELECT id,version,embedding_dimension FROM ima.governed_models
                        WHERE id=CAST(:id AS uuid) AND capability='embedding' AND enabled AND validated"""),
                        {"id": config.embedding_model_id},
                    )
                )
                .mappings()
                .first()
            )
            if not model or not model["embedding_dimension"]:
                raise SearchError(409, "REINDEX_REQUIRED", "Embedding model is not ready")
            count = int(
                await conn.scalar(
                    text("""SELECT count(*) FROM ima.document_chunks c JOIN ima.documents d ON d.id=c.document_id
                    WHERE c.workspace_id=:workspace AND d.workspace_id=:workspace AND d.lifecycle='active' AND c.embedding_status='ready'
                      AND c.model_id=:model AND c.model_version=:version AND c.embedding_dimension=:dimension"""),
                    {
                        "workspace": workspace_id,
                        "model": model["id"],
                        "version": model["version"],
                        "dimension": model["embedding_dimension"],
                    },
                )
                or 0
            )
            if not count:
                raise SearchError(409, "REINDEX_REQUIRED", "No exact-model embeddings are ready")
            await conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {
                    "key": f"{workspace_id}:{model['id']}:{model['version']}:{model['embedding_dimension']}"
                },
            )
            building = await conn.scalar(
                text("""SELECT EXISTS(SELECT 1 FROM ima.chunk_search_indexes
                WHERE workspace_id=:workspace AND model_id=:model AND model_version=:version
                  AND embedding_dimension=:dimension AND status='building')"""),
                {
                    "workspace": workspace_id,
                    "model": model["id"],
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
                    WHERE workspace_id=:workspace AND model_id=:model AND model_version=:version AND embedding_dimension=:dimension"""),
                    {
                        "workspace": workspace_id,
                        "model": model["id"],
                        "version": model["version"],
                        "dimension": model["embedding_dimension"],
                    },
                )
                or 1
            )
            index_name = (
                f"ix_cv_{sha256(workspace_id.encode()).hexdigest()[:8]}_"
                f"{str(model['id']).replace('-', '')[:10]}_{model['version']}_"
                f"{model['embedding_dimension']}_{generation}"
            )
            index_id = uuid4()
            digest = sha256(
                f"{workspace_id}:{model['id']}:{model['version']}:{model['embedding_dimension']}:{count}".encode()
            ).hexdigest()
            await conn.execute(
                text("""INSERT INTO ima.chunk_search_indexes(id,workspace_id,model_id,model_version,embedding_dimension,generation,index_name,status,source_count,source_digest,created_at)
                VALUES (:id,:workspace,:model,:version,:dimension,:generation,:name,'building',:count,:digest,:now)"""),
                {
                    "id": index_id,
                    "workspace": workspace_id,
                    "model": model["id"],
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
        workspace_literal = workspace_id.replace("'", "''")
        statement = f"""CREATE INDEX IF NOT EXISTS {index_name} ON ima.document_chunks USING hnsw
          ((embedding::vector({int(model["embedding_dimension"])})) vector_cosine_ops)
          WHERE workspace_id='{workspace_literal}' AND embedding_status='ready' AND model_id='{model["id"]}'::uuid
            AND model_version={int(model["version"])} AND embedding_dimension={int(model["embedding_dimension"])}"""
        try:
            async with self.engine.connect() as raw_conn:
                autocommit_conn = await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
                await autocommit_conn.execute(text(statement))
            async with self.engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE ima.chunk_search_indexes SET status='retired',retired_at=:now WHERE workspace_id=:workspace AND model_id=:model AND model_version=:version AND embedding_dimension=:dimension AND status='active'"
                    ),
                    {
                        "workspace": workspace_id,
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
            "modelId": model["id"],
            "modelVersion": model["version"],
            "dimension": model["embedding_dimension"],
            "sourceCount": count,
            "status": "active",
        }

    async def _keyword_candidates(
        self,
        conn: AsyncConnection,
        workspace_id: str,
        folders: set[str],
        query: str,
        folder_id: str | None,
        tag_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        rows = (
            (
                await conn.execute(
                    text("""SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest,left(c.text_content,4000) quote,d.title,
          ts_rank(c.search_vector, websearch_to_tsquery('ima.mixed', :query)) score
          FROM ima.document_chunks c JOIN ima.documents d ON d.id=c.document_id
          WHERE c.workspace_id=:workspace AND d.workspace_id=:workspace AND d.lifecycle='active' AND d.folder_id=ANY(:folders)
            AND c.version=COALESCE(d.current_version,c.version) AND c.search_vector @@ websearch_to_tsquery('ima.mixed', :query)
            AND (:folder IS NULL OR d.folder_id=:folder) AND (CAST(:tag AS uuid) IS NULL OR EXISTS (SELECT 1 FROM ima.document_tags dt WHERE dt.document_id=d.id AND dt.tag_id=CAST(:tag AS uuid)))
          ORDER BY score DESC,d.id,c.version,c.generation,c.ordinal LIMIT :limit"""),
                    {
                        "query": query,
                        "workspace": workspace_id,
                        "folders": list(folders),
                        "folder": folder_id,
                        "tag": tag_id,
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
        workspace_id: str,
        folders: set[str],
        query_vector: tuple[float, ...],
        target: dict[str, Any],
        folder_id: str | None,
        tag_id: UUID | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        dimension = int(target["embedding_dimension"])
        vector_literal = "[" + ",".join(format(value, ".9g") for value in query_vector) + "]"
        statement = f"""SELECT c.document_id,c.version,c.generation,c.ordinal,c.content_digest,left(c.text_content,4000) quote,d.title,
          1-(c.embedding::vector({dimension}) <=> CAST(:vector AS vector({dimension}))) score
          FROM ima.document_chunks c JOIN ima.documents d ON d.id=c.document_id
          WHERE c.workspace_id=:workspace AND d.workspace_id=:workspace AND d.lifecycle='active' AND d.folder_id=ANY(:folders)
            AND c.version=COALESCE(d.current_version,c.version) AND c.embedding_status='ready' AND c.model_id=:model AND c.model_version=:version AND c.embedding_dimension=:dimension
            AND (:folder IS NULL OR d.folder_id=:folder) AND (CAST(:tag AS uuid) IS NULL OR EXISTS (SELECT 1 FROM ima.document_tags dt WHERE dt.document_id=d.id AND dt.tag_id=CAST(:tag AS uuid)))
          ORDER BY c.embedding::vector({dimension}) <=> CAST(:vector AS vector({dimension})),d.id,c.version,c.generation,c.ordinal LIMIT :limit"""
        rows = (
            (
                await conn.execute(
                    text(statement),
                    {
                        "vector": vector_literal,
                        "workspace": workspace_id,
                        "folders": list(folders),
                        "model": target["model_id"],
                        "version": target["model_version"],
                        "dimension": target["embedding_dimension"],
                        "folder": folder_id,
                        "tag": tag_id,
                        "limit": limit,
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
        workspace_id: str,
        query: str,
        *,
        mode: str = "keyword",
        top_k: int = 8,
        threshold: float = 0,
        folder_id: str | None = None,
        tag_id: UUID | None = None,
        action: AclAction = AclAction.VIEW_CONTENT,
    ) -> dict[str, object]:
        if not query.strip() or len(query) > 4000:
            raise SearchError(422, "INVALID_QUERY", "Query is invalid")
        if mode not in {"keyword", "vector", "hybrid"}:
            raise SearchError(422, "INVALID_MODE", "Search mode is invalid")
        top_k, threshold, pool = (
            max(1, min(top_k, 50)),
            max(0.0, min(threshold, 1.0)),
            min(max(top_k * 5, 20), 250),
        )
        async with self.engine.connect() as conn:
            await conn.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            config = await self._profile(conn, workspace_id)
            folders = await self._folders(conn, actor, workspace_id, action)
            if folder_id and folder_id not in folders:
                raise SearchError(404, "FOLDER_NOT_FOUND", "Folder not found")
            keyword_rows = (
                await self._keyword_candidates(
                    conn, workspace_id, folders, query, folder_id, tag_id, pool
                )
                if mode in {"keyword", "hybrid"}
                else []
            )
            vector_rows: list[dict[str, Any]] = []
            if mode in {"vector", "hybrid"}:
                target = await self._vector_target(conn, workspace_id, config)
                vectors = await self.models.managed_embeddings(workspace_id, [query])
                if (
                    len(vectors) != 1
                    or len(vectors[0]) != int(target["embedding_dimension"])
                    or not all(math.isfinite(item) for item in vectors[0])
                ):
                    raise SearchError(
                        503, "INVALID_EMBEDDING_RESPONSE", "Embedding response is invalid"
                    )
                vector_rows = await self._vector_candidates(
                    conn, workspace_id, folders, vectors[0], target, folder_id, tag_id, pool
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
                        workspace_id, query, [str(by_identity[key]["quote"]) for key in ordered]
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
            visible = await self._folders(conn, actor, workspace_id, action)
            items = [
                self._result(by_identity[key], scores[key], rank)
                for rank, key in enumerate(ordered, 1)
                if await self._document_visible(conn, cast(UUID, key[0]), visible)
            ][:top_k]
            return {"items": items, "degraded": degraded, "profileTopK": config.top_k}

    async def _document_visible(
        self, conn: AsyncConnection, document_id: UUID, folders: set[str]
    ) -> bool:
        folder = await conn.scalar(
            text("SELECT folder_id FROM ima.documents WHERE id=:id AND lifecycle='active'"),
            {"id": document_id},
        )
        return str(folder) in folders

    @staticmethod
    def _result(row: dict[str, Any], score: float, rank: int) -> dict[str, object]:
        return {
            "documentId": row["document_id"],
            "documentVersion": row["version"],
            "fileGeneration": row["generation"],
            "chunkOrdinal": row["ordinal"],
            "chunkDigest": row["content_digest"],
            "title": row["title"],
            "quote": row["quote"],
            "score": score,
            "rank": rank,
        }

    async def list_conversations(self, actor: str, workspace_id: str) -> list[dict[str, object]]:
        async with self.engine.connect() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.VIEW_METADATA)
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,workspace_id,title,lifecycle,version,created_at,updated_at FROM ima.conversations WHERE workspace_id=:workspace AND owner_user_id=:owner ORDER BY updated_at DESC,id"
                        ),
                        {"workspace": workspace_id, "owner": actor},
                    )
                )
                .mappings()
                .all()
            )
            return [self._conversation(dict(row)) for row in rows]

    async def get_conversation(
        self, actor: str, workspace_id: str, conversation_id: UUID
    ) -> dict[str, object]:
        async with self.engine.connect() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.VIEW_METADATA)
            conversation = await self._owned_conversation(
                conn, actor, workspace_id, conversation_id
            )
            rows = (
                (
                    await conn.execute(
                        text(
                            "SELECT id,role,status,content,sequence,version,created_at,updated_at,completed_at FROM ima.conversation_messages WHERE conversation_id=:id AND workspace_id=:workspace AND owner_user_id=:owner ORDER BY sequence"
                        ),
                        {"id": conversation_id, "workspace": workspace_id, "owner": actor},
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
        workspace_id: str,
        conversation_id: UUID,
        *,
        for_update: bool = False,
    ) -> dict[str, Any]:
        row = (
            (
                await conn.execute(
                    text(
                        "SELECT * FROM ima.conversations WHERE id=:id AND workspace_id=:workspace AND owner_user_id=:owner"
                        + (" FOR UPDATE" if for_update else "")
                    ),
                    {"id": conversation_id, "workspace": workspace_id, "owner": actor},
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
        workspace_id: str,
        conversation_id: UUID,
        title: str | None,
        archive: bool | None,
        expected_version: int,
    ) -> dict[str, object]:
        if title is not None and (not title.strip() or len(title) > 200):
            raise SearchError(422, "INVALID_TITLE", "Conversation title is invalid")
        async with self.engine.begin() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.VIEW_METADATA)
            row = await self._owned_conversation(
                conn, actor, workspace_id, conversation_id, for_update=True
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
        self, actor: str, workspace_id: str, conversation_id: UUID, expected_version: int
    ) -> None:
        async with self.engine.begin() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.VIEW_METADATA)
            row = await self._owned_conversation(
                conn, actor, workspace_id, conversation_id, for_update=True
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
        workspace_id: str,
        conversation_id: UUID,
        message_id: UUID,
        expected_version: int,
    ) -> AsyncIterator[bytes]:
        async with self.engine.connect() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.ASK)
            await self._owned_conversation(conn, actor, workspace_id, conversation_id)
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT content,version FROM ima.conversation_messages WHERE id=:id AND conversation_id=:conversation AND workspace_id=:workspace AND owner_user_id=:owner AND role='user'"
                        ),
                        {
                            "id": message_id,
                            "conversation": conversation_id,
                            "workspace": workspace_id,
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
        return await self.ask(actor, workspace_id, question, conversation_id)

    async def ask_bounded(
        self,
        actor: str,
        workspace_id: str,
        question: str,
        conversation_id: UUID | None = None,
        *,
        max_answer_chars: int = 20000,
        max_citations: int = 20,
        timeout_seconds: float = 30,
    ) -> BoundedAskResult:
        """Run grounded Ask without SSE while preserving target persistence and ACLs."""
        if not question.strip() or len(question) > 20000:
            raise SearchError(422, "INVALID_QUESTION", "Question is invalid")
        if (
            not 1 <= max_answer_chars <= 100000
            or not 1 <= max_citations <= 50
            or not 0 < timeout_seconds <= 60
        ):
            raise SearchError(422, "INVALID_BOUNDS", "Ask bounds are invalid")
        async with self.engine.begin() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.ASK)
            if conversation_id:
                conversation = await self._owned_conversation(
                    conn, actor, workspace_id, conversation_id
                )
                if conversation["lifecycle"] != "active":
                    raise SearchError(409, "CONVERSATION_ARCHIVED", "Conversation is archived")
            else:
                conversation = {
                    "id": uuid4(),
                    "workspace_id": workspace_id,
                    "owner_user_id": actor,
                    "title": question.strip()[:200],
                    "lifecycle": "active",
                    "version": 1,
                    "created_at": now(),
                    "updated_at": now(),
                }
                await conn.execute(
                    text(
                        "INSERT INTO ima.conversations(id,workspace_id,owner_user_id,title,lifecycle,version,created_at,updated_at) VALUES (:id,:workspace_id,:owner_user_id,:title,:lifecycle,:version,:created_at,:updated_at)"
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
                        "INSERT INTO ima.conversation_messages(id,conversation_id,workspace_id,owner_user_id,role,status,content,sequence,created_at,updated_at,completed_at) VALUES (:id,:conversation,:workspace,:owner,:role,:status,:content,:sequence,:now,:now,:completed)"
                    ),
                    {
                        "id": values[0],
                        "conversation": conversation["id"],
                        "workspace": workspace_id,
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
                    config = await self._profile(conn, workspace_id)
                results = await self.search(
                    actor,
                    workspace_id,
                    question,
                    mode=config.retrieval_mode,
                    top_k=min(config.top_k, max_citations),
                    action=AclAction.ASK,
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
                    workspace_id,
                    question,
                    mode=config.retrieval_mode,
                    top_k=min(config.top_k, max_citations),
                    action=AclAction.ASK,
                )
                checked_citations = cast(list[dict[str, object]], checked["items"])[:max_citations]
                if not checked_citations:
                    raise SearchError(403, "ACCESS_REVOKED", "Ask access was revoked")
                context = "\n\n".join(
                    f"[{item['rank']}] {str(item['quote'])[:2000]}" for item in checked_citations
                )[:50000]
                await self._persist_citations(assistant_id, checked_citations)
                await self._status(assistant_id, "streaming")
                response = await self.models.managed_chat(
                    workspace_id,
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
                    workspace_id,
                    question,
                    mode=config.retrieval_mode,
                    top_k=min(config.top_k, max_citations),
                    action=AclAction.ASK,
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

    async def ask(
        self, actor: str, workspace_id: str, question: str, conversation_id: UUID | None
    ) -> AsyncIterator[bytes]:
        if not question.strip() or len(question) > 20000:
            raise SearchError(422, "INVALID_QUESTION", "Question is invalid")
        async with self.engine.begin() as conn:
            await self._folders(conn, actor, workspace_id, AclAction.ASK)
            if conversation_id:
                conversation = await self._owned_conversation(
                    conn, actor, workspace_id, conversation_id
                )
                if conversation["lifecycle"] != "active":
                    raise SearchError(409, "CONVERSATION_ARCHIVED", "Conversation is archived")
            else:
                conversation = {
                    "id": uuid4(),
                    "workspace_id": workspace_id,
                    "owner_user_id": actor,
                    "title": question.strip()[:200],
                    "lifecycle": "active",
                    "version": 1,
                    "created_at": now(),
                    "updated_at": now(),
                }
                await conn.execute(
                    text(
                        "INSERT INTO ima.conversations(id,workspace_id,owner_user_id,title,lifecycle,version,created_at,updated_at) VALUES (:id,:workspace_id,:owner_user_id,:title,:lifecycle,:version,:created_at,:updated_at)"
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
                        "INSERT INTO ima.conversation_messages(id,conversation_id,workspace_id,owner_user_id,role,status,content,sequence,created_at,updated_at,completed_at) VALUES (:id,:conversation,:workspace,:owner,:role,:status,:content,:sequence,:now,:now,:completed)"
                    ),
                    {
                        "id": values[0],
                        "conversation": conversation["id"],
                        "workspace": workspace_id,
                        "owner": actor,
                        "role": values[1],
                        "status": values[2],
                        "content": values[3],
                        "sequence": values[4],
                        "now": timestamp,
                        "completed": timestamp if values[1] == "user" else None,
                    },
                )
        async with self.engine.connect() as conn:
            ask_config = await self._profile(conn, workspace_id)
        retrieval_mode = ask_config.retrieval_mode
        results = await self.search(
            actor,
            workspace_id,
            question,
            mode=retrieval_mode,
            top_k=ask_config.top_k,
            action=AclAction.ASK,
        )
        citations = cast(list[dict[str, object]], results["items"])

        async def stream() -> AsyncIterator[bytes]:
            event_sequence, base = (
                1,
                {"conversationId": str(conversation["id"]), "messageId": str(assistant_id)},
            )
            yield sse(
                "conversation",
                event_sequence,
                {**base, "conversation": self._conversation(conversation)},
            )
            event_sequence += 1
            yield sse("message", event_sequence, {**base, "status": "pending"})
            event_sequence += 1
            if not citations:
                answer = "I could not find relevant information in your accessible knowledge."
                await self._complete(assistant_id, "knowledge_gap", answer)
                yield sse(
                    "knowledge_gap", event_sequence, {**base, "answer": answer, "citations": []}
                )
                return
            checked = await self.search(
                actor,
                workspace_id,
                question,
                mode=retrieval_mode,
                top_k=ask_config.top_k,
                action=AclAction.ASK,
            )
            checked_citations = cast(list[dict[str, object]], checked["items"])
            if not checked_citations:
                await self._complete(assistant_id, "cancelled", "")
                yield sse("cancelled", event_sequence, {**base, "code": "ACCESS_REVOKED"})
                return
            await self._persist_citations(assistant_id, checked_citations)
            yield sse("citations", event_sequence, {**base, "citations": checked_citations})
            event_sequence += 1
            try:
                await self._status(assistant_id, "streaming")
                context = "\n\n".join(
                    f"[{item['rank']}] {item['quote']}" for item in checked_citations
                )
                answer = ""
                async for raw in self.models.managed_chat_stream(
                    workspace_id,
                    Workflow.GROUNDED_ASK,
                    [
                        {
                            "role": "user",
                            "content": f"Answer only from these sources:\n{context}\n\nQuestion: {question}",
                        }
                    ],
                ):
                    for delta in self._deltas(raw):
                        answer += delta
                        yield sse("delta", event_sequence, {**base, "delta": delta})
                        event_sequence += 1
                await self._complete(assistant_id, "completed", answer)
                yield sse("completed", event_sequence, {**base, "status": "completed"})
            except asyncio.CancelledError:
                await self._complete(assistant_id, "cancelled", "")
                raise
            except ModelGovernanceError as exc:
                await self._complete(assistant_id, "failed", "")
                yield sse("error", event_sequence, {**base, "code": exc.code})
            except Exception:
                await self._complete(assistant_id, "failed", "")
                yield sse("error", event_sequence, {**base, "code": "STREAM_FAILED"})

        return stream()

    @staticmethod
    def _deltas(raw: bytes) -> tuple[str, ...]:
        values: list[str] = []
        for line in raw.decode("utf-8", "ignore").splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            try:
                value = json.loads(line[6:])["choices"][0].get("delta", {}).get("content")
            except (IndexError, KeyError, TypeError, json.JSONDecodeError):
                continue
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
                        "INSERT INTO ima.message_citations(message_id,ordinal,document_id,document_version,file_generation,chunk_ordinal,chunk_digest,quote,rank,score,created_at) VALUES (:message,:ordinal,:document,:version,:generation,:chunk,:digest,:quote,:rank,:score,:now)"
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
        self, actor: str, workspace_id: str, message_id: UUID, ordinal: int
    ) -> dict[str, object]:
        async with self.engine.connect() as conn:
            folders = await self._folders(conn, actor, workspace_id, AclAction.VIEW_CONTENT)
            row = (
                (
                    await conn.execute(
                        text("""SELECT c.* FROM ima.message_citations c JOIN ima.conversation_messages m ON m.id=c.message_id
                JOIN ima.document_chunks chunk ON chunk.document_id=c.document_id AND chunk.version=c.document_version AND chunk.generation=c.file_generation AND chunk.ordinal=c.chunk_ordinal AND chunk.content_digest=c.chunk_digest
                WHERE c.message_id=:message AND c.ordinal=:ordinal AND m.workspace_id=:workspace AND m.owner_user_id=:owner"""),
                        {
                            "message": message_id,
                            "ordinal": ordinal,
                            "workspace": workspace_id,
                            "owner": actor,
                        },
                    )
                )
                .mappings()
                .first()
            )
            if not row or not await self._document_visible(conn, row["document_id"], folders):
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

    @staticmethod
    def _conversation(row: dict[str, Any]) -> dict[str, object]:
        return {
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "title": row["title"],
            "lifecycle": row["lifecycle"],
            "version": row["version"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

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
