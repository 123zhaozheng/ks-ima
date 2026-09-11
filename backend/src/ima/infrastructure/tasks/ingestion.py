"""Durable, idempotent file ingestion task registration."""

# ruff: noqa: E501

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from procrastinate import App
from sqlalchemy import text

from ima.application.ingestion import ParseError, Parser, deterministic_chunks
from ima.application.model_governance import ModelGovernanceError, ModelGovernanceService
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine
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
                        """INSERT INTO ima.document_derived_text(document_id,version,generation,parser_name,parser_version,source_checksum,text_digest,text_content,status,created_at) VALUES (:id,:version,:generation,:parser,:parser_version,:checksum,:digest,:content,'ready',:now) ON CONFLICT(document_id,version,generation) DO NOTHING"""
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
                                "SELECT text_content FROM ima.document_derived_text WHERE document_id=:id AND version=:version AND generation=:generation AND status='ready'"
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
                    chunks = deterministic_chunks(
                        derived["text_content"],
                        settings.ingestion_chunk_size,
                        settings.ingestion_chunk_overlap,
                        settings.ingestion_max_chunks,
                    )
                except ParseError as exc:
                    await failed(conn, job, exc.code, retryable=False)
                    return
                if await cancelled(conn, job["id"]):
                    return
                kb_id = await conn.scalar(
                    text("SELECT kb_id FROM ima.documents WHERE id=:id"), {"id": identifier}
                )
                if not kb_id:
                    await failed(conn, job, "DOCUMENT_NOT_FOUND", retryable=False)
                    return
                for ordinal, content, digest in chunks:
                    await conn.execute(
                        text(
                            """INSERT INTO ima.document_chunks(kb_id,document_id,version,generation,ordinal,text_content,content_digest,created_at,updated_at) VALUES (:kb,:id,:version,:generation,:ordinal,:content,:digest,:now,:now) ON CONFLICT(document_id,version,generation,ordinal) DO NOTHING"""
                        ),
                        {
                            "kb": kb_id,
                            "id": identifier,
                            "version": version,
                            "generation": generation,
                            "ordinal": ordinal,
                            "content": content,
                            "digest": digest,
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
                await finish(conn, job["id"], total=len(chunks))
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
                model = (
                    (
                        await conn.execute(
                            text("""SELECT m.id,m.version,m.embedding_dimension FROM ima.kb_profile_assignments a
                            JOIN ima.capability_profile_versions p ON p.profile_id=a.profile_id AND p.version=a.profile_version
                            JOIN ima.governed_models m ON m.id=CAST(p.config->>'embeddingModelId' AS uuid)
                            WHERE a.kb_id=:kb AND a.workflow='embedding'
                              AND m.capability='embedding' AND m.enabled AND m.validated"""),
                            {"kb": kb_id},
                        )
                    )
                    .mappings()
                    .first()
                )
                chunks = (
                    (
                        await conn.execute(
                            text(
                                "SELECT ordinal,text_content FROM ima.document_chunks WHERE document_id=:id AND version=:version AND generation=:generation ORDER BY ordinal"
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
                if not model:
                    await failed(conn, job, "NO_ASSIGNMENT", retryable=False)
                    return
            try:
                vectors = await ModelGovernanceService(engine, settings).managed_embeddings(
                    str(kb_id), [row["text_content"] for row in chunks]
                )
                if (
                    len(vectors) != len(chunks)
                    or any(
                        not vector or any(not math.isfinite(value) for value in vector)
                        for vector in vectors
                    )
                    or any(len(vector) != int(model["embedding_dimension"]) for vector in vectors)
                ):
                    raise ValueError
                dimensions = {len(vector) for vector in vectors}
                if len(dimensions) != 1:
                    raise ValueError
            except ModelGovernanceError as exc:
                async with engine.begin() as conn:
                    await failed(conn, job, exc.code, retryable=exc.status_code >= 500)
                return
            except ValueError:
                async with engine.begin() as conn:
                    await failed(conn, job, "INVALID_EMBEDDING_RESPONSE", retryable=True)
                return
            async with engine.begin() as conn:
                if await cancelled(conn, job["id"]):
                    return
                for row, vector in zip(chunks, vectors, strict=True):
                    await conn.execute(
                        text(
                            "UPDATE ima.document_chunks SET kb_id=:kb,embedding=CAST(:embedding AS vector),model_id=:model,model_version=:model_version,embedding_dimension=:dimension,embedding_status='ready',updated_at=:now WHERE document_id=:id AND version=:version AND generation=:generation AND ordinal=:ordinal"
                        ),
                        {
                            "embedding": "[" + ",".join(str(value) for value in vector) + "]",
                            "kb": kb_id,
                            "model": model["id"],
                            "model_version": model["version"],
                            "dimension": len(vector),
                            "id": identifier,
                            "version": version,
                            "generation": generation,
                            "ordinal": row["ordinal"],
                            "now": datetime.now(UTC),
                        },
                    )
                await finish(conn, job["id"], total=len(chunks))
                await conn.execute(
                    text(
                        "UPDATE ima.documents SET file_state='ready',updated_at=:now WHERE id=:id"
                    ),
                    {"id": identifier, "now": datetime.now(UTC)},
                )
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

    return {"parse": parse, "chunk": chunk, "embed": embed, "cleanup": cleanup}
