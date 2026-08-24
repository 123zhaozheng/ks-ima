"""HTTP middleware shared by every foundation endpoint."""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ima.infrastructure.observability.telemetry import ensure_correlation_id

logger = logging.getLogger(__name__)


class RequestBodyTooLarge(Exception):
    """Raised when a streamed request exceeds the configured body limit."""


class CorrelationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        correlation = ensure_correlation_id(headers.get("x-correlation-id"))
        scope["ima.correlation_id"] = correlation

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-correlation-id", correlation.encode())
                ]
            await send(message)

        await self.app(scope, receive, send_with_header)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            content_length = next(
                (v for k, v in scope.get("headers", []) if k.lower() == b"content-length"), None
            )
            if content_length and content_length.isdigit() and int(content_length) > self.max_bytes:
                from starlette.requests import Request

                from ima.api.errors import make_problem

                response = make_problem(
                    Request(scope, receive),
                    status=413,
                    title="Request body too large",
                    detail="The request body exceeds the configured limit",
                    code="BODY_TOO_LARGE",
                )
                await response(scope, receive, send)
                return
            bytes_received = 0

            async def limited_receive() -> Message:
                nonlocal bytes_received
                message = await receive()
                if message["type"] == "http.request":
                    bytes_received += len(message.get("body", b""))
                    if bytes_received > self.max_bytes:
                        raise RequestBodyTooLarge
                return message

            try:
                await self.app(scope, limited_receive, send)
            except RequestBodyTooLarge:
                from starlette.requests import Request

                from ima.api.errors import make_problem

                response = make_problem(
                    Request(scope, limited_receive),
                    status=413,
                    title="Request body too large",
                    detail="The request body exceeds the configured limit",
                    code="BODY_TOO_LARGE",
                )
                await response(scope, limited_receive, send)
            return
        await self.app(scope, receive, send)


class RequestTimingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        started = time.perf_counter()
        status_code = 500

        async def timed_send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, timed_send)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            scope["ima.duration_ms"] = duration_ms
            if scope["type"] == "http":
                logger.info(
                    "request_completed",
                    extra={
                        "operation": scope.get("path", ""),
                        "result": status_code,
                        "duration_ms": duration_ms,
                        "correlation_id": scope.get("ima.correlation_id", ""),
                    },
                )
