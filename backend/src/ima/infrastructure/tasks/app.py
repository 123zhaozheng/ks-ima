"""Procrastinate application definition shared by API and worker."""

from __future__ import annotations

import procrastinate

from ima.config import Settings


def create_task_app(settings: Settings) -> procrastinate.App:
    """Create a PostgreSQL-backed task app without opening a connection."""
    conninfo = settings.task_url.replace("postgresql+asyncpg://", "postgresql://")
    connector = procrastinate.PsycopgConnector(
        conninfo=conninfo,
        kwargs={"options": f"-c search_path={settings.task_schema}"},
    )
    return procrastinate.App(connector=connector)
