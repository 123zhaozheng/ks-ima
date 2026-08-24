"""Idempotent diagnostic task used by deployment and restart checks."""

from __future__ import annotations

import logging

from procrastinate import JobContext

logger = logging.getLogger(__name__)


def register_tasks(app: object, *, queue_name: str = "diagnostic") -> object:
    """Register the diagnostic task on a Procrastinate app instance."""
    if not hasattr(app, "task"):
        raise TypeError("task app must provide the Procrastinate task decorator")

    @app.task(  # type: ignore[misc]
        name="ima.diagnostic.v1", queue=queue_name, retry=3, pass_context=True
    )
    async def diagnostic(
        context: JobContext, *, idempotency_key: str, fail_once: bool = False
    ) -> None:
        connector = context.app.connector
        try:
            attempt = await connector.execute_query_one_async(
                "UPDATE diagnostic_job SET status = 'running', attempts = attempts + 1, "
                "updated_at = now() WHERE idempotency_key = %(idempotency_key)s "
                "RETURNING attempts",
                idempotency_key=idempotency_key,
            )
            logger.info(
                "diagnostic_job_attempt",
                extra={
                    "idempotency_key": idempotency_key,
                    "attempt": attempt["attempts"],
                    "fail_once": fail_once,
                },
            )
            if fail_once and attempt["attempts"] == 1:
                raise RuntimeError("controlled diagnostic failure")
            await connector.execute_query_async(
                "UPDATE diagnostic_job SET status = 'succeeded', updated_at = now() "
                "WHERE idempotency_key = %(idempotency_key)s",
                idempotency_key=idempotency_key,
            )
        except Exception:
            attempts = await connector.execute_query_one_async(
                "SELECT attempts FROM diagnostic_job WHERE idempotency_key = %(idempotency_key)s",
                idempotency_key=idempotency_key,
            )
            if attempts["attempts"] >= 3:
                await connector.execute_query_async(
                    "UPDATE diagnostic_job SET status = 'failed', updated_at = now() "
                    "WHERE idempotency_key = %(idempotency_key)s",
                    idempotency_key=idempotency_key,
                )
            raise
        logger.info("diagnostic_job_completed", extra={"idempotency_key": idempotency_key})

    return diagnostic
