"""Durable, retrying model health task."""

from __future__ import annotations

from uuid import UUID

from procrastinate import JobContext

from ima.application.model_governance import ModelGovernanceService
from ima.config import Settings
from ima.infrastructure.db.engine import create_engine


def register_model_health_task(app: object, settings: Settings) -> object:
    if not hasattr(app, "task"):
        raise TypeError("task app must provide the Procrastinate task decorator")

    @app.task(  # type: ignore[misc]
        name="ima.model-health.v1",
        queue=settings.diagnostic_queue,
        retry=3,
        pass_context=True,
    )
    async def model_health(
        _context: JobContext, *, gateway_id: str, capability: str | None = None
    ) -> None:
        engine = create_engine(settings)
        try:
            service = ModelGovernanceService(engine, settings)
            from ima.domain.model_governance import ModelCapability

            await service.check_gateway_health(
                None,
                UUID(gateway_id),
                ModelCapability(capability) if capability else None,
            )
        finally:
            await engine.dispose()

    return model_health
