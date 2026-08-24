"""Database and migration readiness probes."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from ima.config import Settings


async def check_database(engine: AsyncEngine, settings: Settings) -> tuple[bool, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            schema_exists = await connection.scalar(
                text("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = :schema)"),
                {"schema": settings.database_schema},
            )
            if not schema_exists:
                return False, f"schema {settings.database_schema!r} is not migrated"
        return True, "database and target schema are reachable"
    except Exception:
        return False, "database is unavailable"
