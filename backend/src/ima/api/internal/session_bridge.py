"""Fail-closed identity introspection for the temporary Bun consumer."""

# ruff: noqa: E501

from __future__ import annotations

import hmac

from fastapi import APIRouter, Header, HTTPException, Request

from ima.api.v1.auth import service

router = APIRouter(prefix="/internal/session", tags=["internal"], include_in_schema=False)


@router.post("/introspect", operation_id="internalSessionIntrospect")
async def introspect(
    request: Request, x_ima_bridge_token: str | None = Header(default=None)
) -> dict[str, object]:
    expected = request.app.state.settings.bridge_token.get_secret_value()
    if not x_ima_bridge_token or not hmac.compare_digest(x_ima_bridge_token, expected):
        raise HTTPException(401, "Invalid bridge credential")
    value = await service(request).current_session(request)
    if not value:
        raise HTTPException(401, "Session is not active")
    return {"user": value[1].model_dump(by_alias=True)}
