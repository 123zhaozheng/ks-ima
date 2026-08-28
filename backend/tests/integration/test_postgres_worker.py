"""End-to-end durable queue test against the Compose target database."""

from __future__ import annotations

import asyncio
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from ima.config import Settings
from ima.infrastructure.db.engine import create_engine
from ima.infrastructure.tasks.service import JobService

DATABASE_URL = os.environ.get("IMA_TEST_DATABASE_URL")


async def _wait_for_status(engine: object, job_id: str, expected: str) -> tuple[str, int]:
    for _ in range(60):
        async with engine.connect() as connection:  # type: ignore[attr-defined]
            row = (
                await connection.execute(
                    text("SELECT status, attempts FROM ima_jobs.diagnostic_job WHERE id = :id"),
                    {"id": job_id},
                )
            ).one()
        if row.status == expected:
            return row.status, row.attempts
        await asyncio.sleep(0.25)
    raise AssertionError(f"job {job_id} did not reach {expected}, last status={row.status}")


async def _wait_for_heartbeat(engine: object, worker_name: str) -> datetime:
    for _ in range(60):
        async with engine.connect() as connection:  # type: ignore[attr-defined]
            heartbeat = await connection.scalar(
                text(
                    "SELECT heartbeat_at FROM ima_jobs.worker_heartbeat "
                    "WHERE worker_name = :worker_name"
                ),
                {"worker_name": worker_name},
            )
        if isinstance(heartbeat, datetime):
            return heartbeat
        await asyncio.sleep(0.25)
    raise AssertionError(f"worker {worker_name} did not publish a heartbeat")


@pytest.mark.postgres
@pytest.mark.skipif(not DATABASE_URL, reason="IMA_TEST_DATABASE_URL is not configured")
@pytest.mark.asyncio
async def test_idempotency_retry_and_worker_restart() -> None:
    assert DATABASE_URL is not None
    run_id = uuid4().hex[:12]
    # PostgreSQL NOTIFY channels are limited to 63 bytes; Procrastinate adds
    # its own prefix to queue names.
    integration_queue = f"di-{run_id}"
    integration_worker_name = f"diagnostic-integration-{run_id}"
    normal_queue = f"dn-{run_id}"
    normal_worker_name = f"diagnostic-normal-{run_id}"
    settings = Settings(
        environment="test",
        database_url=DATABASE_URL,
        task_database_url=DATABASE_URL,
        diagnostic_jobs_enabled=True,
        worker_lag_warning_seconds=10,
        diagnostic_queue=integration_queue,
        worker_name=integration_worker_name,
    )
    engine = create_engine(settings)
    service = JobService(settings, engine)
    integration_worker_env = {
        **os.environ,
        "IMA_DATABASE_URL": DATABASE_URL,
        "IMA_LOG_LEVEL": "DEBUG",
        "IMA_DIAGNOSTIC_QUEUE": settings.diagnostic_queue,
        "IMA_WORKER_NAME": settings.worker_name,
    }
    normal_worker_env = {
        **os.environ,
        "IMA_DATABASE_URL": DATABASE_URL,
        "IMA_LOG_LEVEL": "DEBUG",
        "IMA_DIAGNOSTIC_QUEUE": normal_queue,
        "IMA_WORKER_NAME": normal_worker_name,
    }
    normal_worker = None
    integration_worker = None
    key = f"integration-{uuid4()}"
    try:
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM ima_jobs.diagnostic_job"))
        await service.start()
        first = await service.enqueue(key, fail_once=True, correlation="integration")
        duplicate = await service.enqueue(key, fail_once=True, correlation="integration")
        assert first.id == duplicate.id
        await service.stop()

        # The job is durable while no worker is running. Starting a fresh worker
        # proves that queued work survives the API/worker process boundary.
        normal_worker = subprocess.Popen(  # noqa: ASYNC220
            ["uv", "run", "--project", ".", "python", "-m", "ima.workers.main"],
            cwd=Path(__file__).parents[2],
            env=normal_worker_env,
        )
        await _wait_for_heartbeat(engine, normal_worker_name)

        # A normal worker must not claim work from the integration queue.
        async with engine.connect() as connection:
            queued = (
                await connection.execute(
                    text("SELECT status, attempts FROM ima_jobs.diagnostic_job WHERE id = :id"),
                    {"id": first.id},
                )
            ).one()
        assert (queued.status, queued.attempts) == ("queued", 0)

        integration_worker = subprocess.Popen(  # noqa: ASYNC220
            ["uv", "run", "--project", ".", "python", "-m", "ima.workers.main"],
            cwd=Path(__file__).parents[2],
            env=integration_worker_env,
        )
        status, attempts = await _wait_for_status(engine, str(first.id), "succeeded")
        assert status == "succeeded"
        assert attempts == 2

        async with engine.connect() as connection:
            count = await connection.scalar(
                text("SELECT count(*) FROM ima_jobs.diagnostic_job WHERE idempotency_key = :key"),
                {"key": key},
            )
            heartbeat = await connection.scalar(
                text(
                    "SELECT heartbeat_at FROM ima_jobs.worker_heartbeat "
                    "WHERE worker_name = :worker_name"
                ),
                {"worker_name": settings.worker_name},
            )
        assert count == 1
        assert isinstance(heartbeat, datetime)
        assert heartbeat.tzinfo is not None
        assert (datetime.now(UTC) - heartbeat).total_seconds() < 10
    finally:
        await service.stop()
        await engine.dispose()
        for worker in (integration_worker, normal_worker):
            if worker is None:
                continue
            if os.name == "nt" and worker.pid:
                await asyncio.to_thread(
                    subprocess.run,
                    ["taskkill", "/T", "/F", "/PID", str(worker.pid)],
                    check=False,
                    capture_output=True,
                )
            else:
                worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=10)
