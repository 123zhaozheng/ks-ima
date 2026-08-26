"""Durable diagnostic jobs backed by PostgreSQL via Procrastinate."""

# ruff: noqa: E501

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from procrastinate import App
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from ima.api.contracts import DiagnosticJob
from ima.config import Settings
from ima.infrastructure.tasks.app import create_task_app
from ima.infrastructure.tasks.diagnostic import register_tasks
from ima.infrastructure.tasks.ingestion import register_ingestion_tasks
from ima.infrastructure.tasks.model_health import register_model_health_task

logger = logging.getLogger(__name__)


class JobService:
    """Application-facing adapter around the durable queue.

    Procrastinate owns persistence, leasing, retries, and recovery. This adapter
    only translates the queue's operational state into the HTTP contract.
    """

    def __init__(self, settings: Settings, engine: AsyncEngine) -> None:
        self.settings = settings
        self.engine = engine
        self._app: App = create_task_app(settings)
        self._diagnostic_task = register_tasks(self._app, queue_name=settings.diagnostic_queue)
        self._model_health_task = register_model_health_task(self._app, settings)
        self._ingestion_tasks = register_ingestion_tasks(self._app, settings)

    async def enqueue_model_health(self, gateway_id: UUID, capability: str | None = None) -> None:
        await self._model_health_task.defer_async(  # type: ignore[attr-defined]
            gateway_id=str(gateway_id), capability=capability
        )

    async def create_ingestion_jobs(
        self,
        connection: AsyncConnection,
        document_id: UUID,
        version: int,
        generation: int,
        actor: str,
    ) -> bool:
        key = f"{document_id}:{version}:{generation}:parse"
        now = datetime.now(UTC)
        row = (
            await connection.execute(
                text(
                    """INSERT INTO ima.ingestion_jobs(id,idempotency_key,document_id,version,generation,stage,status,created_by,created_at,updated_at)
                    VALUES (:id,:key,:document,:version,:generation,'parse','queued',:actor,:now,:now)
                    ON CONFLICT (idempotency_key) DO NOTHING RETURNING id"""
                ),
                {
                    "id": uuid4(),
                    "key": key,
                    "document": document_id,
                    "version": version,
                    "generation": generation,
                    "actor": actor,
                    "now": now,
                },
            )
        ).scalar()
        for stage in ("chunk", "embed"):
            await connection.execute(
                text(
                    """INSERT INTO ima.ingestion_jobs(id,idempotency_key,document_id,version,generation,stage,status,created_by,created_at,updated_at)
                    VALUES (:id,:key,:document,:version,:generation,:stage,'blocked',:actor,:now,:now)
                    ON CONFLICT (idempotency_key) DO NOTHING"""
                ),
                {
                    "id": uuid4(),
                    "key": f"{document_id}:{version}:{generation}:{stage}",
                    "document": document_id,
                    "version": version,
                    "generation": generation,
                    "stage": stage,
                    "actor": actor,
                    "now": now,
                },
            )
        return row is not None

    async def defer_ingestion_parse(self, document_id: UUID, version: int, generation: int) -> None:
        await self._ingestion_tasks["parse"].defer_async(
            document_id=str(document_id), version=version, generation=generation
        )

    async def enqueue_ingestion(
        self, document_id: UUID, version: int, generation: int, actor: str
    ) -> None:
        async with self.engine.begin() as connection:
            created = await self.create_ingestion_jobs(
                connection, document_id, version, generation, actor
            )
        if created:
            await self.defer_ingestion_parse(document_id, version, generation)

    async def defer_ingestion_stage(
        self, document_id: UUID, version: int, generation: int, stage: str
    ) -> None:
        task = self._ingestion_tasks.get(stage)
        if task is None:
            raise ValueError("unknown ingestion stage")
        if stage == "cleanup":
            raise ValueError("cleanup requires a cleanup job ID")
        await task.defer_async(document_id=str(document_id), version=version, generation=generation)

    async def enqueue_cleanup(self, object_key: str, document_id: UUID, version: int) -> None:
        now = datetime.now(UTC)
        async with self.engine.begin() as connection:
            cleanup_id = (
                await connection.execute(
                    text(
                        """INSERT INTO ima.storage_cleanup_jobs(id,object_key,document_id,version,status,next_eligible_at,created_at,updated_at)
                        VALUES (:id,:key,:document,:version,'queued',:now,:now,:now)
                        ON CONFLICT (object_key) DO UPDATE SET next_eligible_at=LEAST(ima.storage_cleanup_jobs.next_eligible_at, EXCLUDED.next_eligible_at)
                        RETURNING id"""
                    ),
                    {
                        "id": uuid4(),
                        "key": object_key,
                        "document": document_id,
                        "version": version,
                        "now": now,
                    },
                )
            ).scalar_one()
        await self._ingestion_tasks["cleanup"].defer_async(cleanup_id=str(cleanup_id))

    async def start(self) -> None:
        await self._app.open_async()

    async def stop(self) -> None:
        await self._app.close_async()

    async def readiness(self) -> tuple[bool, str]:
        try:
            async with self.engine.connect() as connection:
                heartbeat = await connection.scalar(
                    text(
                        "SELECT heartbeat_at FROM ima_jobs.worker_heartbeat "
                        "WHERE worker_name = :worker_name"
                    ),
                    {"worker_name": self.settings.worker_name},
                )
        except Exception:
            return False, "worker heartbeat is unavailable"
        if not isinstance(heartbeat, datetime):
            return False, "worker heartbeat has not been recorded"
        age = (datetime.now(UTC) - heartbeat).total_seconds()
        if age > self.settings.worker_lag_warning_seconds:
            return False, "worker heartbeat is stale"
        return True, "worker heartbeat is current"

    async def enqueue(self, key: str, fail_once: bool, correlation: str) -> DiagnosticJob:
        """Enqueue a job through the durable implementation.

        The queue integration is initialized by the worker process; API requests
        do not create detached tasks or rely on process memory for execution.
        """
        now = datetime.now(UTC)
        async with self.engine.begin() as connection:
            result = await connection.execute(
                text(
                    """INSERT INTO ima_jobs.diagnostic_job
                    (id, idempotency_key, status, attempts, correlation_id,
                     created_at, updated_at)
                    VALUES (:id, :key, 'queued', 0, :correlation, :now, :now)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING id, status, attempts, correlation_id, created_at, updated_at"""
                ),
                {"id": uuid4(), "key": key, "correlation": correlation, "now": now},
            )
            row = result.mappings().first()
            should_enqueue = row is not None
            if row is None:
                row = (
                    (
                        await connection.execute(
                            text(
                                "SELECT id, status, attempts, correlation_id, created_at, "
                                "updated_at "
                                "FROM ima_jobs.diagnostic_job WHERE idempotency_key = :key"
                            ),
                            {"key": key},
                        )
                    )
                    .mappings()
                    .one()
                )
        if should_enqueue:
            await self._diagnostic_task.defer_async(idempotency_key=key, fail_once=fail_once)  # type: ignore[attr-defined]
        return DiagnosticJob(
            id=row["id"],
            status=row["status"],
            attempts=row["attempts"],
            correlationId=row["correlation_id"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
        )

    async def get(self, job_id: UUID) -> DiagnosticJob:
        async with self.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        text(
                            "SELECT id, status, attempts, correlation_id, created_at, "
                            "updated_at "
                            "FROM ima_jobs.diagnostic_job WHERE id = :id"
                        ),
                        {"id": job_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return DiagnosticJob(
            id=row["id"],
            status=row["status"],
            attempts=row["attempts"],
            correlationId=row["correlation_id"],
            createdAt=row["created_at"],
            updatedAt=row["updated_at"],
        )
