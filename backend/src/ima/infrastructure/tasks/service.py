"""Durable diagnostic jobs backed by PostgreSQL via Procrastinate."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from procrastinate import App
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ima.api.contracts import DiagnosticJob
from ima.config import Settings
from ima.infrastructure.tasks.app import create_task_app
from ima.infrastructure.tasks.diagnostic import register_tasks

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
