import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from ima.api.middleware import BodyLimitMiddleware


def test_body_limit_rejects_chunked_requests() -> None:
    messages = iter(
        [
            {"type": "http.request", "body": b"12", "more_body": True},
            {"type": "http.request", "body": b"34", "more_body": False},
        ]
    )
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return next(messages)

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def app(
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        await receive()
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "http_version": "1.1",
    }
    asyncio.run(BodyLimitMiddleware(app, max_bytes=3)(scope, receive, send))
    assert sent[0]["status"] == 413
