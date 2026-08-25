"""Network policy for administrator-configured intranet model gateways."""

from __future__ import annotations

import asyncio
import ipaddress
import math
import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import httpx


class GatewayError(RuntimeError):
    """Stable, safe gateway failure; details never contain response bodies."""

    def __init__(self, code: str, message: str = "Gateway request failed") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class EgressPolicy:
    allowed_hosts: tuple[str, ...] = ()
    allowed_cidrs: tuple[str, ...] = ()
    allow_insecure_private: bool = False
    max_response_bytes: int = 8 * 1024 * 1024
    connect_timeout_seconds: float = 5
    read_timeout_seconds: float = 30
    write_timeout_seconds: float = 30
    pool_timeout_seconds: float = 5
    custom_ca_dir: str | None = None
    _networks: tuple[Any, ...] = field(init=False, repr=False, default=())

    def __post_init__(self) -> None:
        try:
            object.__setattr__(
                self,
                "_networks",
                tuple(ipaddress.ip_network(v, strict=False) for v in self.allowed_cidrs),
            )
        except ValueError as exc:
            raise GatewayError("INVALID_ALLOWLIST") from exc

    @property
    def networks(self) -> tuple[Any, ...]:
        return self._networks

    def verify_bundle(self, reference: str | None) -> str | bool:
        if not reference:
            return True
        if not self.custom_ca_dir:
            raise GatewayError("CUSTOM_CA_UNAVAILABLE")
        root = Path(self.custom_ca_dir).resolve()
        bundle = (root / reference).resolve()
        if root not in bundle.parents or not bundle.is_file():
            raise GatewayError("CUSTOM_CA_UNAVAILABLE")
        return str(bundle)


def validate_base_url(value: str, *, insecure_private: bool = False) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise GatewayError("INVALID_BASE_URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise GatewayError("INVALID_BASE_URL")
    if parsed.path not in {"", "/"}:
        raise GatewayError("INVALID_BASE_URL")
    if parsed.scheme == "http" and not insecure_private:
        raise GatewayError("INSECURE_GATEWAY")
    try:
        port = parsed.port
    except ValueError as exc:
        raise GatewayError("INVALID_BASE_URL") from exc
    if port is not None and not 1 <= port <= 65535:
        raise GatewayError("INVALID_BASE_URL")
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", "")).rstrip("/")


def capability_url(base_url: str, capability: str) -> str:
    base = validate_base_url(base_url, insecure_private=urlparse(base_url).scheme == "http")
    paths = {
        "models": "/models",
        "chat": "/chat/completions",
        "embedding": "/embeddings",
        "rerank": "/rerank",
    }
    try:
        path = paths[capability]
    except KeyError as exc:
        raise GatewayError("UNKNOWN_CAPABILITY") from exc
    return f"{base}{path}"


async def resolve_allowed_addresses(
    host: str, policy: EgressPolicy, port: int | None
) -> tuple[str, ...]:
    """Resolve all addresses and reject mixed/public/rebinding results."""

    addresses: tuple[str, ...]
    literal_target = False
    try:
        literal = ipaddress.ip_address(host)
        addresses = (str(literal),)
        literal_target = True
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().run_in_executor(
                None, lambda: socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
            )
        except (OSError, socket.gaierror) as exc:
            raise GatewayError("DNS_FAILURE") from exc
        addresses = tuple(str(info[4][0]) for info in infos)
    if not addresses:
        raise GatewayError("DNS_EMPTY")
    allowed_hosts = {value.rstrip(".").lower() for value in policy.allowed_hosts}
    if host.rstrip(".").lower() not in allowed_hosts and not policy.networks:
        raise GatewayError("HOST_NOT_ALLOWLISTED")
    for value in addresses:
        ip = ipaddress.ip_address(value)
        explicitly_allowed = host.rstrip(".").lower() in allowed_hosts or any(
            ip in network for network in policy.networks
        )
        if (
            ip.is_unspecified or ip.is_loopback or ip.is_link_local or ip.is_multicast
        ) and not explicitly_allowed:
            raise GatewayError("PRIVATE_ADDRESS_REJECTED")
        if policy.networks and not any(ip in network for network in policy.networks):
            raise GatewayError("ADDRESS_NOT_ALLOWLISTED")
        if ip.is_global and not (
            (literal_target and host.rstrip(".").lower() in allowed_hosts)
            or any(ip in network for network in policy.networks)
        ):
            raise GatewayError("PUBLIC_ADDRESS_REJECTED")
    return addresses


async def validate_egress(base_url: str, policy: EgressPolicy, *, insecure_private: bool) -> str:
    normalized = validate_base_url(
        base_url, insecure_private=insecure_private and policy.allow_insecure_private
    )
    parsed = urlparse(normalized)
    await resolve_allowed_addresses(parsed.hostname or "", policy, parsed.port)
    return normalized


class GuardedGatewayClient:
    """One bounded no-redirect client for all supported gateway capabilities."""

    def __init__(self, policy: EgressPolicy) -> None:
        self.policy = policy

    def _timeout(self) -> httpx.Timeout:
        return httpx.Timeout(
            connect=self.policy.connect_timeout_seconds,
            read=self.policy.read_timeout_seconds,
            write=self.policy.write_timeout_seconds,
            pool=self.policy.pool_timeout_seconds,
        )

    async def _request(
        self,
        *,
        base_url: str,
        capability: str,
        payload: dict[str, object] | None = None,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> dict[str, object] | list[object]:
        normalized = await validate_egress(base_url, self.policy, insecure_private=insecure_private)
        url = capability_url(normalized, capability)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout(),
                follow_redirects=False,
                trust_env=False,
                verify=self.policy.verify_bundle(custom_ca_ref),
            ) as client:
                async with client.stream(
                    "POST" if payload is not None else "GET", url, json=payload, headers=headers
                ) as response:
                    if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                        raise GatewayError("REDIRECT_REJECTED")
                    if response.status_code >= 400:
                        raise GatewayError("UPSTREAM_HTTP_ERROR")
                    length = response.headers.get("content-length")
                    if length:
                        try:
                            declared_length = int(length)
                        except ValueError as exc:
                            raise GatewayError("INVALID_RESPONSE") from exc
                        if declared_length < 0:
                            raise GatewayError("INVALID_RESPONSE")
                        if declared_length > self.policy.max_response_bytes:
                            raise GatewayError("RESPONSE_TOO_LARGE")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.policy.max_response_bytes:
                            raise GatewayError("RESPONSE_TOO_LARGE")
                        chunks.append(chunk)
                    try:
                        value = httpx.Response(200, content=b"".join(chunks)).json()
                    except ValueError as exc:
                        raise GatewayError("INVALID_RESPONSE") from exc
        except GatewayError:
            raise
        except httpx.TimeoutException as exc:
            raise GatewayError("TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise GatewayError("NETWORK_ERROR") from exc
        if not isinstance(value, dict | list):
            raise GatewayError("INVALID_RESPONSE")
        return value

    async def discover(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> tuple[str, ...]:
        value = await self._request(
            base_url=base_url,
            capability="models",
            api_key=api_key,
            custom_ca_ref=custom_ca_ref,
            insecure_private=insecure_private,
        )
        if not isinstance(value, dict) or not isinstance(value.get("data"), list):
            raise GatewayError("INVALID_MODELS_RESPONSE")
        names: list[str] = []
        for item in cast(list[Any], value["data"]):
            if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                names.append(item["id"])
        return tuple(sorted(set(names)))

    async def chat(
        self,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> dict[str, object]:
        value = await self._request(
            base_url=base_url,
            capability="chat",
            api_key=api_key,
            custom_ca_ref=custom_ca_ref,
            insecure_private=insecure_private,
            payload={
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": False,
            },
        )
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("choices"), list)
            or not value["choices"]
        ):
            raise GatewayError("INVALID_CHAT_RESPONSE")
        return value

    async def embeddings(
        self,
        base_url: str,
        model: str,
        inputs: list[str],
        *,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> tuple[tuple[float, ...], ...]:
        value = await self._request(
            base_url=base_url,
            capability="embedding",
            api_key=api_key,
            custom_ca_ref=custom_ca_ref,
            insecure_private=insecure_private,
            payload={"model": model, "input": inputs},
        )
        if not isinstance(value, dict) or not isinstance(value.get("data"), list):
            raise GatewayError("INVALID_EMBEDDING_RESPONSE")
        vectors: list[tuple[float, ...]] = []
        for item in cast(list[Any], value["data"]):
            if not isinstance(item, dict) or not isinstance(item.get("embedding"), list):
                raise GatewayError("INVALID_EMBEDDING_RESPONSE")
            try:
                vector = tuple(float(number) for number in item["embedding"])
            except (TypeError, ValueError) as exc:
                raise GatewayError("INVALID_EMBEDDING_RESPONSE") from exc
            if not vector or any(
                number != number or number in {float("inf"), float("-inf")} for number in vector
            ):
                raise GatewayError("INVALID_EMBEDDING_RESPONSE")
            vectors.append(vector)
        if len(vectors) != len(inputs):
            raise GatewayError("INVALID_EMBEDDING_RESPONSE")
        return tuple(vectors)

    async def rerank(
        self,
        base_url: str,
        model: str,
        query: str,
        documents: list[str],
        *,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> tuple[tuple[int, float], ...]:
        value = await self._request(
            base_url=base_url,
            capability="rerank",
            api_key=api_key,
            custom_ca_ref=custom_ca_ref,
            insecure_private=insecure_private,
            payload={"model": model, "query": query, "documents": documents},
        )
        if not isinstance(value, dict) or not isinstance(value.get("results"), list):
            raise GatewayError("INVALID_RERANK_RESPONSE")
        result: list[tuple[int, float]] = []
        for item in cast(list[Any], value["results"]):
            if not isinstance(item, dict):
                raise GatewayError("INVALID_RERANK_RESPONSE")
            try:
                index = int(item["index"])
                score = float(item["relevance_score"])
            except (KeyError, TypeError, ValueError) as exc:
                raise GatewayError("INVALID_RERANK_RESPONSE") from exc
            if index < 0 or index >= len(documents) or not math.isfinite(score):
                raise GatewayError("INVALID_RERANK_RESPONSE")
            result.append((index, score))
        return tuple(result)

    async def probe(
        self,
        base_url: str,
        capability: str,
        model: str,
        *,
        dimension: int | None = None,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> tuple[bool, str | None, int | None]:
        """Run a bounded harmless probe and return success, stable code, latency."""

        started = asyncio.get_running_loop().time()
        try:
            if capability == "chat":
                await self.chat(
                    base_url,
                    model,
                    [{"role": "user", "content": "Reply with OK."}],
                    max_tokens=8,
                    api_key=api_key,
                    custom_ca_ref=custom_ca_ref,
                    insecure_private=insecure_private,
                )
            elif capability == "embedding":
                vectors = await self.embeddings(
                    base_url,
                    model,
                    ["probe"],
                    api_key=api_key,
                    custom_ca_ref=custom_ca_ref,
                    insecure_private=insecure_private,
                )
                if dimension is not None and len(vectors[0]) != dimension:
                    return (
                        False,
                        "DIMENSION_MISMATCH",
                        int((asyncio.get_running_loop().time() - started) * 1000),
                    )
            elif capability == "rerank":
                await self.rerank(
                    base_url,
                    model,
                    "probe",
                    ["probe one", "probe two"],
                    api_key=api_key,
                    custom_ca_ref=custom_ca_ref,
                    insecure_private=insecure_private,
                )
            else:
                return False, "UNKNOWN_CAPABILITY", None
        except GatewayError as exc:
            return False, exc.code, int((asyncio.get_running_loop().time() - started) * 1000)
        return True, None, int((asyncio.get_running_loop().time() - started) * 1000)

    async def chat_completion(
        self,
        base_url: str,
        model: str,
        payload: dict[str, object],
        *,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> dict[str, object]:
        """Execute a managed non-streaming chat request with a forced model."""

        request_payload = dict(payload)
        request_payload["model"] = model
        request_payload["stream"] = False
        value = await self._request(
            base_url=base_url,
            capability="chat",
            payload=request_payload,
            api_key=api_key,
            custom_ca_ref=custom_ca_ref,
            insecure_private=insecure_private,
        )
        if not isinstance(value, dict):
            raise GatewayError("INVALID_CHAT_RESPONSE")
        choices = value.get("choices")
        if not isinstance(choices, list) or not choices:
            raise GatewayError("INVALID_CHAT_RESPONSE")
        return value

    async def stream_chat_completion(
        self,
        base_url: str,
        model: str,
        payload: dict[str, object],
        *,
        api_key: str | None = None,
        custom_ca_ref: str | None = None,
        insecure_private: bool = False,
    ) -> AsyncIterator[bytes]:
        """Stream a managed chat response while enforcing the body limit."""

        normalized = await validate_egress(base_url, self.policy, insecure_private=insecure_private)
        url = capability_url(normalized, "chat")
        request_payload = dict(payload)
        request_payload["model"] = model
        request_payload["stream"] = True
        headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout(),
                follow_redirects=False,
                trust_env=False,
                verify=self.policy.verify_bundle(custom_ca_ref),
            ) as client:
                async with client.stream(
                    "POST", url, json=request_payload, headers=headers
                ) as response:
                    if response.is_redirect or response.status_code in {301, 302, 303, 307, 308}:
                        raise GatewayError("REDIRECT_REJECTED")
                    if response.status_code >= 400:
                        raise GatewayError("UPSTREAM_HTTP_ERROR")
                    length = response.headers.get("content-length")
                    if length:
                        try:
                            declared_length = int(length)
                        except ValueError as exc:
                            raise GatewayError("INVALID_RESPONSE") from exc
                        if declared_length < 0:
                            raise GatewayError("INVALID_RESPONSE")
                        if declared_length > self.policy.max_response_bytes:
                            raise GatewayError("RESPONSE_TOO_LARGE")
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.policy.max_response_bytes:
                            raise GatewayError("RESPONSE_TOO_LARGE")
                        yield chunk
        except GatewayError:
            raise
        except httpx.TimeoutException as exc:
            raise GatewayError("TIMEOUT") from exc
        except httpx.HTTPError as exc:
            raise GatewayError("NETWORK_ERROR") from exc


__all__ = [
    "EgressPolicy",
    "GatewayError",
    "GuardedGatewayClient",
    "capability_url",
    "validate_base_url",
    "validate_egress",
]
