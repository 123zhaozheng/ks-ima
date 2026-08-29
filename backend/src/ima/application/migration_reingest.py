"""Bounded re-ingestion readiness rules for migrated legacy files (G2).

Pure classification only; the CLI performs the bounded enqueue against the
existing ``ima.ingestion_jobs`` pipeline and worker capacity.
"""

from __future__ import annotations

from ima.application.ingestion import SUPPORTED_MIME_TYPES

READY = "ready"
DEGRADED = "degraded"
FAILED = "failed"
PENDING = "pending"

_TERMINAL_BAD = frozenset({"failed", "dead_letter", "cancelled"})


def mime_supported(mime_type: str | None) -> bool:
    return mime_type is not None and mime_type.lower() in SUPPORTED_MIME_TYPES


def classify_readiness(
    *,
    file_state: str,
    parse_status: str | None = None,
    chunk_status: str | None = None,
    embed_status: str | None = None,
    mime_type: str | None = None,
) -> str:
    """Classify one migrated file version into ready/degraded/failed/pending.

    - ``ready``: the embed stage marked the document ready.
    - ``failed``: the document is failed, or parse terminated badly.
    - ``degraded``: parse succeeded but a downstream stage terminated badly,
      or the MIME type is unsupported (bytes exist, text cannot be derived).
    - ``pending``: everything still in flight or not yet enqueued.
    """
    if file_state == "ready":
        return READY
    if file_state == "failed":
        return FAILED
    if parse_status in _TERMINAL_BAD:
        return DEGRADED if not mime_supported(mime_type) else FAILED
    if parse_status == "succeeded" and (
        chunk_status in _TERMINAL_BAD or embed_status in _TERMINAL_BAD
    ):
        return DEGRADED
    if chunk_status in _TERMINAL_BAD or embed_status in _TERMINAL_BAD:
        return FAILED
    if not mime_supported(mime_type):
        return DEGRADED
    return PENDING


def enqueue_budget(max_active: int, active_jobs: int, limit: int, candidates: int) -> int:
    """Bounded enqueue budget: worker capacity and operator limit both apply."""
    if max_active <= 0 or limit <= 0:
        return 0
    budget = max_active - active_jobs
    if budget <= 0:
        return 0
    return max(0, min(budget, limit, candidates))
