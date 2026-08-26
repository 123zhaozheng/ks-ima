"""Worker process entry point; migrations remain an explicit deployment step."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ima.config import get_settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.observability.logging import configure_logging
from ima.infrastructure.tasks.app import create_task_app
from ima.infrastructure.tasks.diagnostic import register_tasks
from ima.infrastructure.tasks.ingestion import register_ingestion_tasks
from ima.infrastructure.tasks.model_health import register_model_health_task


async def heartbeat(engine: object, interval: int, worker_name: str) -> None:
    while True:
        async with engine.begin() as connection:  # type: ignore[attr-defined]
            await connection.execute(
                text(
                    "INSERT INTO ima_jobs.worker_heartbeat (worker_name, heartbeat_at) "
                    "VALUES (:worker_name, :now) ON CONFLICT (worker_name) DO UPDATE "
                    "SET heartbeat_at = :now"
                ),
                {"worker_name": worker_name, "now": datetime.now(UTC)},
            )
        await asyncio.sleep(interval)


async def reconcile_ingestion(
    engine: AsyncEngine, ingestion_tasks: dict[str, Any], interval: int = 15
) -> None:
    while True:
        now = datetime.now(UTC)
        async with engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT document_id,version,generation,stage FROM ima.ingestion_jobs
                            WHERE (status IN ('queued','retryable')
                                   AND (retry_at IS NULL OR retry_at <= :now))
                               OR (status='running' AND lease_expires_at < :now)"""
                        ),
                        {"now": now},
                    )
                )
                .mappings()
                .all()
            )
            cleanup_rows = (
                (
                    await connection.execute(
                        text(
                            """SELECT id FROM ima.storage_cleanup_jobs
                            WHERE status IN ('queued','retryable') AND next_eligible_at <= :now"""
                        ),
                        {"now": now},
                    )
                )
                .mappings()
                .all()
            )
        for row in rows:
            await ingestion_tasks[row["stage"]].defer_async(
                document_id=str(row["document_id"]),
                version=int(row["version"]),
                generation=int(row["generation"]),
            )
        for row in cleanup_rows:
            await ingestion_tasks["cleanup"].defer_async(cleanup_id=str(row["id"]))
        await asyncio.sleep(interval)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    task_app = create_task_app(settings)
    register_tasks(task_app, queue_name=settings.diagnostic_queue)
    register_model_health_task(task_app, settings)
    ingestion_tasks = register_ingestion_tasks(task_app, settings)
    engine = create_engine(settings)
    async with task_app.open_async():
        heartbeat_task = asyncio.create_task(
            heartbeat(engine, settings.worker_heartbeat_seconds, settings.worker_name),
            name="ima-worker-heartbeat",
        )
        reconcile_task = asyncio.create_task(
            reconcile_ingestion(engine, ingestion_tasks), name="ima-ingestion-reconciliation"
        )
        try:
            await task_app.run_worker_async(
                queues=[settings.diagnostic_queue, settings.ingestion_queue],
                name=settings.worker_name,
            )
        finally:
            heartbeat_task.cancel()
            reconcile_task.cancel()
            await asyncio.gather(heartbeat_task, reconcile_task, return_exceptions=True)
            await engine.dispose()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
