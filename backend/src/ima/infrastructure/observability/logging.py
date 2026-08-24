"""Structured logging with recursive secret redaction."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, cast

from pythonjsonlogger.json import JsonFormatter

_SECRET_NAME = re.compile(
    r"(secret|password|token|api[_-]?key|authorization|credential|private[_-]?key)", re.I
)


def redact(value: Any, *, key: str = "") -> Any:
    if key and _SECRET_NAME.search(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return cast(
            dict[str, Any], {str(name): redact(item, key=str(name)) for name, item in value.items()}
        )
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


class RedactingFormatter(JsonFormatter):
    def process_log_record(self, log_record: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], redact(log_record))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
