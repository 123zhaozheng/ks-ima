"""Procrastinate application definition shared by API and worker."""

from __future__ import annotations

from typing import LiteralString

import procrastinate

from ima.config import Settings

_CONFIGURE_PROCRASTINATE_SEARCH_PATH_SQL: LiteralString = """
DO $$
DECLARE
    routine record;
BEGIN
    FOR routine IN
        SELECT p.oid::regprocedure AS identity, p.prokind
        FROM pg_proc AS p
        JOIN pg_namespace AS n ON n.oid = p.pronamespace
        WHERE n.nspname = current_schema()
          AND p.proname LIKE 'procrastinate_%%'
          AND p.prokind IN ('f', 'p')
    LOOP
        EXECUTE format(
            CASE routine.prokind
                WHEN 'p' THEN 'ALTER PROCEDURE %%s SET search_path TO %%I'
                ELSE 'ALTER FUNCTION %%s SET search_path TO %%I'
            END,
            routine.identity,
            current_schema()
        );
    END LOOP;
END
$$;
"""


def create_task_app(settings: Settings) -> procrastinate.App:
    """Create a PostgreSQL-backed task app without opening a connection."""
    conninfo = settings.task_url.replace("postgresql+asyncpg://", "postgresql://")
    connector = procrastinate.PsycopgConnector(
        conninfo=conninfo,
        kwargs={"options": f"-c search_path={settings.task_schema}"},
    )
    return procrastinate.App(connector=connector)


def configure_procrastinate_function_search_path(task_app: procrastinate.App) -> None:
    """Pin Procrastinate routines to the task schema used by this connection."""
    task_app.connector.get_sync_connector().execute_query(
        query=_CONFIGURE_PROCRASTINATE_SEARCH_PATH_SQL
    )
