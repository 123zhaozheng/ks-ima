#!/usr/bin/env python
"""Standalone entry point that fixes Windows asyncio policy."""
import asyncio
import os
from sys import platform

if platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set database URLs with correct port and credentials
os.environ.setdefault("IMA_DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5430/app")
os.environ.setdefault("IMA_TASK_DATABASE_URL", "postgresql+asyncpg://user:password@localhost:5430/postgres")

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
    run("ima.main:app", host="0.0.0.0", port=9016)
