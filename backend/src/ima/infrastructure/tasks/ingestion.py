"""Durable, idempotent file ingestion task registration."""

# ruff: noqa: E501

from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from procrastinate import App
from sqlalchemy import text

from ima.application.ingestion import (
    CHUNKER_VERSION,
    ParseError,
    Parser,
    blocks_from_ir,
    chunker_config_digest,
    estimate_tokens,
    structure_aware_chunks,
)
from ima.application.model_governance import ModelGovernanceError, ModelGovernanceService
from ima.config import Settings
from ima.domain.model_governance import Workflow, parse_profile_config
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.model_gateway.egress import GatewayError
from ima.infrastructure.storage import ObjectStorageClient, StorageClientError

LEASE = timedelta(minutes=10)
MAX_ATTEMPTS = 3


async def mark_document_terminal(conn: Any, document_id: UUID | str) -> None:
    """Reflect a failed/cancelled ingestion on the document without clobbering ready."""
    await conn.execute(
        text(
            "UPDATE ima.documents SET file_state='failed',updated_at=:now WHERE id=:id AND file_state <> 'ready'"
        ),
        {"id": document_id, "now": datetime.now(UTC)},
    )


async def finalize_cancel_requested(conn: Any, job_id: UUID) -> bool:
    """Cooperatively close a running job a user asked to cancel."""
    row = (
        (
            await conn.execute(
                text(
                    "SELECT status='cancel_requested' AS requested,document_id FROM ima.ingestion_jobs WHERE id=:id"
                ),
                {"id": job_id},
            )
        )
        .mappings()
        .first()
    )
    if row and row["requested"]:
        await conn.execute(
            text(
                "UPDATE ima.ingestion_jobs SET status='cancelled',lease_expires_at=NULL,updated_at=:now WHERE id=:id"
            ),
            {"id": job_id, "now": datetime.now(UTC)},
        )
        await mark_document_terminal(conn, row["document_id"])
        return True
    return False


def register_ingestion_tasks(app: App, settings: Settings) -> dict[str, Any]:
    async def claim(conn: Any, document_id: UUID, version: int, generation: int, stage: str) -> Any:
        now = datetime.now(UTC)
        row = (
            (
                await conn.execute(
                    text(
                        """UPDATE ima.ingestion_jobs SET status='running',attempts=attempts+1,
                    lease_expires_at=:lease,updated_at=:now WHERE document_id=:document_id
                    AND version=:version AND generation=:generation AND stage=:stage
                    AND (status IN ('queued','retryable') OR (status='running' AND lease_expires_at < :now))
                    AND (retry_at IS NULL OR retry_at <= :now) RETURNING *"""
                    ),
                    {
                        "document_id": document_id,
                        "version": version,
                        "generation": generation,
                        "stage": stage,
                        "now": now,
                        "lease": now + LEASE,
                    },
                )
            )
            .mappings()
            .first()
        )
        return row

    async def finish(conn: Any, job_id: UUID, *, total: int = 1) -> None:
        await conn.execute(
            text(
                "UPDATE ima.ingestion_jobs SET status='succeeded',completed_units=:total,total_units=:total,lease_expires_at=NULL,error_code=NULL,updated_at=:now WHERE id=:id"
            ),
            {"id": job_id, "total": total, "now": datetime.now(UTC)},
        )

    async def cancelled(conn: Any, job_id: UUID) -> bool:
        return await finalize_cancel_requested(conn, job_id)

    async def failed(conn: Any, job: Any, code: str, *, retryable: bool) -> None:
        attempts = int(job["attempts"])
        now = datetime.now(UTC)
        if retryable and attempts < MAX_ATTEMPTS:
            await conn.execute(
                text(
                    "UPDATE ima.ingestion_jobs SET status='retryable',retry_at=:retry,lease_expires_at=NULL,error_code=:code,updated_at=:now WHERE id=:id"
                ),
                {
                    "id": job["id"],
                    "code": code,
                    "now": now,
                    "retry": now + timedelta(seconds=2**attempts),
                },
            )
        else:
            await conn.execute(
                text(
                    "UPDATE ima.ingestion_jobs SET status=:status,lease_expires_at=NULL,error_code=:code,updated_at=:now WHERE id=:id"
                ),
                {
                    "id": job["id"],
                    "code": code,
                    "status": "dead_letter" if retryable else "failed",
                    "now": now,
                },
            )
            await mark_document_terminal(conn, job["document_id"])

    @app.task(
        name="ima.ingestion.parse", queue=settings.ingestion_queue, retry=0, pass_context=True
    )
    async def parse(context: object, document_id: str, version: int, generation: int) -> None:
        engine = create_engine(settings)
        identifier = UUID(document_id)
        try:
            async with engine.begin() as conn:
                job = await claim(conn, identifier, version, generation, "parse")
                if not job or await cancelled(conn, job["id"]):
                    return
                file_row = (
                    (
                        await conn.execute(
                            text(
                                "SELECT object_key,checksum,mime_type,original_filename FROM ima.document_file_versions WHERE document_id=:id AND version=:version AND object_state='verified'"
                            ),
                            {"id": identifier, "version": version},
                        )
                    )
                    .mappings()
                    .first()
                )
                if not file_row:
                    await failed(conn, job, "OBJECT_MISSING", retryable=False)
                    return
            try:
                body = ObjectStorageClient(settings).read(file_row["object_key"])
                data = body.read(settings.storage_max_object_bytes + 1)
                parsed = Parser(settings).parse(
                    data, file_row["original_filename"], file_row["mime_type"]
                )
            except ParseError as exc:
                async with engine.begin() as conn:
                    await failed(conn, job, exc.code, retryable=exc.retryable)
                return
            except StorageClientError as exc:
                async with engine.begin() as conn:
                    await failed(conn, job, exc.code, retryable=True)
                return
            async with engine.begin() as conn:
                if await cancelled(conn, job["id"]):
                    return
                await conn.execute(
                    text(
                        """INSERT INTO ima.document_derived_text(document_id,version,generation,parser_name,parser_version,source_checksum,text_digest,text_content,ir,status,created_at) VALUES (:id,:version,:generation,:parser,:parser_version,:checksum,:digest,:content,CAST(:ir AS jsonb),'ready',:now) ON CONFLICT(document_id,version,generation) DO UPDATE SET parser_name=EXCLUDED.parser_name,parser_version=EXCLUDED.parser_version,source_checksum=EXCLUDED.source_checksum,text_digest=EXCLUDED.text_digest,text_content=EXCLUDED.text_content,ir=EXCLUDED.ir,status='ready'"""
                    ),
                    {
                        "id": identifier,
                        "version": version,
                        "generation": generation,
                        "parser": parsed.parser,
                        "parser_version": parsed.parser_version,
                        "checksum": file_row["checksum"],
                        "digest": parsed.digest,
                        "content": parsed.text,
                        "ir": json.dumps(parsed.ir, ensure_ascii=False),
                        "now": datetime.now(UTC),
                    },
                )
                await finish(conn, job["id"])
                await conn.execute(
                    text(
                        "UPDATE ima.ingestion_jobs SET status='queued',retry_at=NULL,updated_at=:now WHERE document_id=:id AND version=:version AND generation=:generation AND stage='chunk' AND status='blocked'"
                    ),
                    {
                        "id": identifier,
                        "version": version,
                        "generation": generation,
                        "now": datetime.now(UTC),
                    },
                )
            await chunk.defer_async(document_id=document_id, version=version, generation=generation)
        finally:
            await engine.dispose()

    @app.task(
        name="ima.ingestion.chunk", queue=settings.ingestion_queue, retry=0, pass_context=True
    )
    async def chunk(context: object, document_id: str, version: int, generation: int) -> None:
        engine = create_engine(settings)
        identifier = UUID(document_id)
        try:
            async with engine.begin() as conn:
                job = await claim(conn, identifier, version, generation, "chunk")
                if not job or await cancelled(conn, job["id"]):
                    return
                derived = (
                    (
                        await conn.execute(
                            text(
                                "SELECT text_content,ir FROM ima.document_derived_text WHERE document_id=:id AND version=:version AND generation=:generation AND status='ready'"
                            ),
                            {"id": identifier, "version": version, "generation": generation},
                        )
                    )
                    .mappings()
                    .first()
                )
                if not derived:
                    await failed(conn, job, "DERIVED_TEXT_MISSING", retryable=False)
                    return
                try:
                    chunker_version = settings.ingestion_chunker_version or CHUNKER_VERSION
                    overlap_blocks = settings.ingestion_chunk_overlap_blocks
                    config_digest = chunker_config_digest(
                        settings.ingestion_chunk_size,
                        overlap_blocks,
                        settings.ingestion_max_chunks,
                        chunker_version,
                    )
                    records = structure_aware_chunks(
                        blocks_from_ir(derived["ir"], derived["text_content"]),
                        settings.ingestion_chunk_size,
                        overlap_blocks,
                        settings.ingestion_max_chunks,
                        chunker_version=chunker_version,
                        config_digest=config_digest,
                    )
                except ParseError as exc:
                    await failed(conn, job, exc.code, retryable=False)
                    return
                if not records:
                    await failed(conn, job, "NO_CHUNKS", retryable=False)
                    return
                if await cancelled(conn, job["id"]):
                    return
                kb_id = await conn.scalar(
                    text("SELECT kb_id FROM ima.documents WHERE id=:id"), {"id": identifier}
                )
                if not kb_id:
                    await failed(conn, job, "DOCUMENT_NOT_FOUND", retryable=False)
                    return
                previous_generation = generation
                existing = (
                    (
                        await conn.execute(
                            text(
                                "SELECT chunker_version,metadata->>'chunker_config_digest' AS config_digest FROM ima.document_chunks WHERE document_id=:id AND version=:version AND generation=:generation ORDER BY ordinal LIMIT 1"
                            ),
                            {
                                "id": identifier,
                                "version": version,
                                "generation": generation,
                            },
                        )
                    )
                    .mappings()
                    .first()
                )
                if existing and (
                    existing["chunker_version"] != chunker_version
                    or existing["config_digest"] != config_digest
                ):
                    generation = int(
                        await conn.scalar(
                            text(
                                "SELECT COALESCE(MAX(generation),:generation)+1 FROM ima.document_derived_text WHERE document_id=:id AND version=:version"
                            ),
                            {
                                "id": identifier,
                                "version": version,
                                "generation": generation,
                            },
                        )
                    )
                    now_value = datetime.now(UTC)
                    await conn.execute(
                        text(
                            """INSERT INTO ima.document_derived_text(document_id,version,generation,parser_name,parser_version,source_checksum,text_digest,text_content,ir,status,created_at)
                            SELECT document_id,version,:new_generation,parser_name,parser_version,source_checksum,text_digest,text_content,ir,status,created_at
                            FROM ima.document_derived_text WHERE document_id=:id AND version=:version AND generation=:old_generation
                            ON CONFLICT(document_id,version,generation) DO NOTHING"""
                        ),
                        {
                            "id": identifier,
                            "version": version,
                            "old_generation": previous_generation,
                            "new_generation": generation,
                        },
                    )
                    await conn.execute(
                        text(
                            """INSERT INTO ima.ingestion_jobs(id,idempotency_key,document_id,version,generation,stage,status,completed_units,total_units,attempts,created_at,updated_at)
                            VALUES (:job_id,:key,:id,:version,:generation,'parse','succeeded',1,1,1,:now,:now)
                            ON CONFLICT(document_id,version,generation,stage) DO NOTHING"""
                        ),
                        {
                            "job_id": uuid4(),
                            "key": f"{identifier}:{version}:{generation}:parse",
                            "id": identifier,
                            "version": version,
                            "generation": generation,
                            "now": now_value,
                        },
                    )
                    await conn.execute(
                        text(
                            "UPDATE ima.ingestion_jobs SET generation=:new_generation,idempotency_key=:new_key WHERE id=:job_id"
                        ),
                        {
                            "new_generation": generation,
                            "new_key": f"{identifier}:{version}:{generation}:chunk",
                            "job_id": job["id"],
                        },
                    )
                    updated_embed = await conn.execute(
                        text(
                            "UPDATE ima.ingestion_jobs SET generation=:new_generation,idempotency_key=:new_key WHERE document_id=:id AND version=:version AND generation=:old_generation AND stage='embed' AND status='blocked'"
                        ),
                        {
                            "id": identifier,
                            "version": version,
                            "old_generation": previous_generation,
                            "new_generation": generation,
                            "new_key": f"{identifier}:{version}:{generation}:embed",
                        },
                    )
                    if updated_embed.rowcount == 0:
                        await conn.execute(
                            text(
                                """INSERT INTO ima.ingestion_jobs(id,idempotency_key,document_id,version,generation,stage,status,created_at,updated_at)
                                VALUES (:id,:key,:document_id,:version,:generation,'embed','blocked',:now,:now)
                                ON CONFLICT(document_id,version,generation,stage) DO NOTHING"""
                            ),
                            {
                                "id": uuid4(),
                                "key": f"{identifier}:{version}:{generation}:embed",
                                "document_id": identifier,
                                "version": version,
                                "generation": generation,
                                "now": now_value,
                            },
                        )
                    await conn.execute(
                        text(
                            "UPDATE ima.document_file_versions SET generation=:generation WHERE document_id=:id AND version=:version"
                        ),
                        {"id": identifier, "version": version, "generation": generation},
                    )
                for record in records:
                    await conn.execute(
                        text(
                            """INSERT INTO ima.document_chunks(kb_id,document_id,version,generation,ordinal,text_content,content_digest,metadata,heading_path,page_start,page_end,sheet_name,chunk_type,token_count,chunker_version,created_at,updated_at)
                            VALUES (:kb,:id,:version,:generation,:ordinal,:content,:digest,CAST(:metadata AS jsonb),CAST(:heading_path AS text[]),:page_start,:page_end,:sheet_name,:chunk_type,:token_count,:chunker_version,:now,:now)
                            ON CONFLICT(document_id,version,generation,ordinal) DO UPDATE SET
                              kb_id=EXCLUDED.kb_id,text_content=EXCLUDED.text_content,content_digest=EXCLUDED.content_digest,metadata=EXCLUDED.metadata,heading_path=EXCLUDED.heading_path,page_start=EXCLUDED.page_start,page_end=EXCLUDED.page_end,sheet_name=EXCLUDED.sheet_name,chunk_type=EXCLUDED.chunk_type,token_count=EXCLUDED.token_count,chunker_version=EXCLUDED.chunker_version,updated_at=EXCLUDED.updated_at"""
                        ),
                        {
                            "kb": kb_id,
                            "id": identifier,
                            "version": version,
                            "generation": generation,
                            "ordinal": record.ordinal,
                            "content": record.text_content,
                            "digest": record.content_digest,
                            "metadata": json.dumps(record.metadata, ensure_ascii=False),
                            "heading_path": list(record.heading_path),
                            "page_start": record.page_start,
                            "page_end": record.page_end,
                            "sheet_name": record.sheet_name,
                            "chunk_type": record.chunk_type,
                            "token_count": record.token_count,
                            "chunker_version": record.chunker_version,
                            "now": datetime.now(UTC),
                        },
                    )
                if await cancelled(conn, job["id"]):
                    return
                await conn.execute(
                    text(
                        "UPDATE ima.ingestion_jobs SET status='queued',retry_at=NULL,updated_at=:now WHERE document_id=:id AND version=:version AND generation=:generation AND stage='embed' AND status='blocked'"
                    ),
                    {
                        "id": identifier,
                        "version": version,
                        "generation": generation,
                        "now": datetime.now(UTC),
                    },
                )
                await finish(conn, job["id"], total=len(records))
            await embed.defer_async(document_id=document_id, version=version, generation=generation)
        finally:
            await engine.dispose()

    @app.task(
        name="ima.ingestion.embed", queue=settings.ingestion_queue, retry=0, pass_context=True
    )
    async def embed(context: object, document_id: str, version: int, generation: int) -> None:
        engine = create_engine(settings)
        identifier = UUID(document_id)
        try:
            async with engine.begin() as conn:
                job = await claim(conn, identifier, version, generation, "embed")
                if not job or await cancelled(conn, job["id"]):
                    return
                kb_id = await conn.scalar(
                    text("SELECT kb_id FROM ima.documents WHERE id=:id"), {"id": identifier}
                )
                chunks = (
                    (
                        await conn.execute(
                            text(
                                "SELECT ordinal,text_content,embedding_status FROM ima.document_chunks WHERE document_id=:id AND version=:version AND generation=:generation ORDER BY ordinal"
                            ),
                            {"id": identifier, "version": version, "generation": generation},
                        )
                    )
                    .mappings()
                    .all()
                )
                # Two distinct failures share one guard today; report them
                # accurately so operators can tell a missing document from a KB
                # that has no embedding model assigned.
                if not kb_id:
                    await failed(conn, job, "DOCUMENT_NOT_FOUND", retryable=False)
                    return
                if not chunks:
                    await failed(conn, job, "NO_CHUNKS", retryable=False)
                    return
                pending_chunks = [row for row in chunks if row["embedding_status"] != "ready"]
                completed = len(chunks) - len(pending_chunks)
                await conn.execute(
                    text(
                        "UPDATE ima.ingestion_jobs SET completed_units=:completed,total_units=:total,updated_at=:now WHERE id=:id"
                    ),
                    {
                        "id": job["id"],
                        "completed": completed,
                        "total": len(chunks),
                        "now": datetime.now(UTC),
                    },
                )
                if not pending_chunks:
                    await finish(conn, job["id"], total=len(chunks))
                    await conn.execute(
                        text(
                            "UPDATE ima.documents SET file_state='ready',updated_at=:now WHERE id=:id"
                        ),
                        {"id": identifier, "now": datetime.now(UTC)},
                    )
            # Resolve the embedding target through the governed service so the
            # ingestion stage shares the exact assignment/scene-default
            # precedence (and denial semantics) used by retrieval.  This runs
            # outside the ingest transaction; the service owns its connections.
            if not pending_chunks:
                await index.defer_async(kb_id=str(kb_id))
                return
            service = ModelGovernanceService(engine, settings)
            try:
                target = await service.embedding_target(str(kb_id))
            except ModelGovernanceError as exc:
                async with engine.begin() as conn:
                    await failed(conn, job, exc.code, retryable=exc.status_code >= 500)
                return
            if target is None:
                async with engine.begin() as conn:
                    await failed(conn, job, "NO_ASSIGNMENT", retryable=False)
                return
            if target.get("reason"):
                async with engine.begin() as conn:
                    await failed(conn, job, str(target["reason"]), retryable=False)
                return
            model_id = target["model_id"]
            model_version = target["model_version"]
            dimension = target["embedding_dimension"]
            embedding_config = parse_profile_config(target["config"], Workflow.EMBEDDING)
            batch_size = int(getattr(embedding_config, "batch_size", 32))
            max_tokens = int(getattr(embedding_config, "max_tokens", 8192))
            batches: list[list[Any]] = []
            current_batch: list[Any] = []
            current_tokens = 0
            for row in pending_chunks:
                row_tokens = estimate_tokens(row["text_content"])
                if row_tokens > max_tokens:
                    async with engine.begin() as conn:
                        await failed(conn, job, "EMBEDDING_INPUT_TOO_LARGE", retryable=False)
                    return
                if current_batch and (
                    len(current_batch) >= batch_size or current_tokens + row_tokens > max_tokens
                ):
                    batches.append(current_batch)
                    current_batch = []
                    current_tokens = 0
                current_batch.append(row)
                current_tokens += row_tokens
            if current_batch:
                batches.append(current_batch)
            try:
                for batch in batches:
                    vectors = await service.managed_embeddings(
                        str(kb_id), [row["text_content"] for row in batch]
                    )
                    if (
                        len(vectors) != len(batch)
                        or any(
                            not vector or any(not math.isfinite(value) for value in vector)
                            for vector in vectors
                        )
                        or any(len(vector) != int(dimension) for vector in vectors)
                    ):
                        raise ValueError
                    dimensions = {len(vector) for vector in vectors}
                    if len(dimensions) != 1:
                        raise ValueError
                    async with engine.begin() as conn:
                        if await cancelled(conn, job["id"]):
                            return
                        for row, vector in zip(batch, vectors, strict=True):
                            await conn.execute(
                                text(
                                    "UPDATE ima.document_chunks SET kb_id=:kb,embedding=CAST(:embedding AS vector),model_id=:model,model_version=:model_version,embedding_dimension=:dimension,embedding_status='ready',updated_at=:now WHERE document_id=:id AND version=:version AND generation=:generation AND ordinal=:ordinal"
                                ),
                                {
                                    "embedding": "["
                                    + ",".join(str(value) for value in vector)
                                    + "]",
                                    "kb": kb_id,
                                    "model": model_id,
                                    "model_version": model_version,
                                    "dimension": len(vector),
                                    "id": identifier,
                                    "version": version,
                                    "generation": generation,
                                    "ordinal": row["ordinal"],
                                    "now": datetime.now(UTC),
                                },
                            )
                        completed += len(batch)
                        await conn.execute(
                            text(
                                "UPDATE ima.ingestion_jobs SET completed_units=:completed,total_units=:total,updated_at=:now WHERE id=:id"
                            ),
                            {
                                "id": job["id"],
                                "completed": completed,
                                "total": len(chunks),
                                "now": datetime.now(UTC),
                            },
                        )
            except ModelGovernanceError as exc:
                async with engine.begin() as conn:
                    await failed(conn, job, exc.code, retryable=exc.status_code >= 500)
                return
            except GatewayError as exc:
                async with engine.begin() as conn:
                    await failed(conn, job, exc.code, retryable=True)
                return
            except ValueError:
                async with engine.begin() as conn:
                    await failed(conn, job, "INVALID_EMBEDDING_RESPONSE", retryable=True)
                return
            async with engine.begin() as conn:
                if await cancelled(conn, job["id"]):
                    return
                await finish(conn, job["id"], total=len(chunks))
                await conn.execute(
                    text(
                        "UPDATE ima.documents SET file_state='ready',updated_at=:now WHERE id=:id"
                    ),
                    {"id": identifier, "now": datetime.now(UTC)},
                )
            # Freshly embedded chunks must get an exact-model retrieval index or
            # grounded ask would demand a manual REINDEX_REQUIRED step.
            await index.defer_async(kb_id=str(kb_id))
        finally:
            await engine.dispose()

    @app.task(
        name="ima.ingestion.cleanup", queue=settings.ingestion_queue, retry=0, pass_context=True
    )
    async def cleanup(context: object, cleanup_id: str) -> None:
        engine = create_engine(settings)
        try:
            async with engine.begin() as conn:
                row = (
                    (
                        await conn.execute(
                            text(
                                "UPDATE ima.storage_cleanup_jobs SET status='running',attempts=attempts+1,updated_at=:now WHERE id=:id AND status IN ('queued','retryable') AND next_eligible_at <= :now RETURNING *"
                            ),
                            {"id": UUID(cleanup_id), "now": datetime.now(UTC)},
                        )
                    )
                    .mappings()
                    .first()
                )
                if not row:
                    return
                dependent = await conn.scalar(
                    text(
                        "SELECT EXISTS(SELECT 1 FROM ima.document_file_versions WHERE object_key=:key)"
                    ),
                    {"key": row["object_key"]},
                )
                if dependent:
                    await conn.execute(
                        text(
                            "UPDATE ima.storage_cleanup_jobs SET status='retryable',next_eligible_at=:next,error_code='DEPENDENCY_EXISTS',updated_at=:now WHERE id=:id"
                        ),
                        {
                            "id": row["id"],
                            "next": datetime.now(UTC)
                            + timedelta(seconds=settings.storage_retention_seconds),
                            "now": datetime.now(UTC),
                        },
                    )
                    return
            try:
                ObjectStorageClient(settings).delete(row["object_key"])
            except StorageClientError as exc:
                async with engine.begin() as conn:
                    await conn.execute(
                        text(
                            "UPDATE ima.storage_cleanup_jobs SET status='retryable',next_eligible_at=:next,error_code=:code,updated_at=:now WHERE id=:id"
                        ),
                        {
                            "id": row["id"],
                            "next": datetime.now(UTC) + timedelta(minutes=5),
                            "code": exc.code,
                            "now": datetime.now(UTC),
                        },
                    )
                return
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE ima.storage_cleanup_jobs SET status='succeeded',error_code=NULL,updated_at=:now WHERE id=:id"
                    ),
                    {"id": row["id"], "now": datetime.now(UTC)},
                )
        finally:
            await engine.dispose()

    @app.task(
        name="ima.ingestion.index", queue=settings.ingestion_queue, retry=0, pass_context=True
    )
    async def index(context: object, kb_id: str) -> None:
        """Build/refresh the KB's exact scene-default embedding index (idempotent)."""
        # Imported lazily: the search application module depends on the task
        # service, so a module-level import would close an import cycle.
        from ima.application.search import SearchService

        engine = create_engine(settings)
        try:
            service = SearchService(engine, ModelGovernanceService(engine, settings))
            await service.maintain_vector_index(kb_id)
        finally:
            await engine.dispose()

    return {
        "parse": parse,
        "chunk": chunk,
        "embed": embed,
        "cleanup": cleanup,
        "index": index,
    }
