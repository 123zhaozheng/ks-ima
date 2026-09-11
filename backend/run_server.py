#!/usr/bin/env python
"""Standalone entry point that fixes Windows asyncio policy."""
import asyncio
import os
import subprocess
import sys
from sys import platform

if platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set database URLs with correct port and credentials
os.environ.setdefault("IMA_DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5430/app")
# Leave IMA_TASK_DATABASE_URL unset: the task app then reuses the main database,
# which is where the migration puts the `ima_jobs` Procrastinate schema. Pointing
# it at the `postgres` maintenance database breaks the worker with
# "procrastinate_*_v1 does not exist".

# The admin console is now part of the single front app (dev port 9015), so the
# backend must accept that origin for CSRF-checked mutations. Without this the
# defaults only allow http://localhost:8080 and every save returns 403.
os.environ.setdefault("IMA_PUBLIC_ORIGIN", "http://localhost:9015")
os.environ.setdefault("IMA_CORS_ORIGINS", "http://localhost:9015")

# Object storage (MinIO from docker-compose.dev.yml). All four are required
# together; without them the storage client is disabled and every upload
# ticket answers 503 STORAGE_UNAVAILABLE.
os.environ.setdefault("IMA_STORAGE_ENDPOINT", "http://127.0.0.1:9000")
os.environ.setdefault("IMA_STORAGE_BUCKET", "nyaai")
os.environ.setdefault("IMA_STORAGE_ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("IMA_STORAGE_SECRET_ACCESS_KEY", "minioadmin")
os.environ.setdefault("IMA_STORAGE_REGION", "us-east-1")

from uvicorn import run

if __name__ == "__main__":
    # The API never consumes ingestion jobs itself; a separate worker process
    # does (same shape as production).  Start it alongside the API so local dev
    # uploads actually get parsed/chunked/embedded, and always tear it down.
    worker = subprocess.Popen([sys.executable, "-m", "ima.workers.main"])
    try:
        run("ima.main:app", host="0.0.0.0", port=9016)
    finally:
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait()
        elif worker.returncode not in (0, -15, -9):
            print(
                f"ingestion worker exited unexpectedly (code {worker.returncode})",
                file=sys.stderr,
            )
