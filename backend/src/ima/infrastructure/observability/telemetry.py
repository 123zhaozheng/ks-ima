"""Request correlation and low-cardinality observability helpers."""

from __future__ import annotations

from contextvars import ContextVar
from uuid import UUID, uuid4

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")


def ensure_correlation_id(value: str | None = None) -> str:
    if value:
        try:
            UUID(value)
        except ValueError:
            pass
        else:
            correlation_id.set(value)
            return value
    generated = str(uuid4())
    correlation_id.set(generated)
    return generated
