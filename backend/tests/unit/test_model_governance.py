from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from ima.api.v1 import model_governance as model_governance_api
from ima.application.model_governance import ModelGovernanceService
from ima.config import Settings
from ima.domain.model_governance import (
    EmbeddingConfig,
    GroundedAskConfig,
    Workflow,
    canonical_config,
    config_digest,
    parse_profile_config,
    required_capabilities,
)
from ima.infrastructure.model_gateway import egress
from ima.infrastructure.model_gateway.egress import (
    EgressPolicy,
    GatewayError,
    GuardedGatewayClient,
    validate_base_url,
)
from ima.infrastructure.model_gateway.secrets import (
    SecretEnvelopeError,
    SecretKeyRing,
    redact_model_secret,
)


def test_secret_envelope_roundtrip_rotation_and_aad_failure() -> None:
    ring = SecretKeyRing(
        '{"v1":"a-development-key","v2":"b-development-key"}', "v2", "fingerprint-key"
    )
    envelope = ring.encrypt("token-value", gateway_id="gateway", secret_id="secret")
    assert envelope.key_version == "v2"
    assert ring.decrypt(envelope, gateway_id="gateway", secret_id="secret") == "token-value"
    rotated = ring.rotate(envelope, gateway_id="gateway", secret_id="secret")
    assert ring.decrypt(rotated, gateway_id="gateway", secret_id="secret") == "token-value"
    with pytest.raises(SecretEnvelopeError):
        ring.decrypt(envelope, gateway_id="other", secret_id="secret")


def test_secret_redaction_is_recursive() -> None:
    value = {"nested": [{"apiKey": "secret", "safe": "visible"}], "ciphertext": "bytes"}
    assert redact_model_secret(value) == {
        "nested": [{"apiKey": "[REDACTED]", "safe": "visible"}],
        "ciphertext": "[REDACTED]",
    }


def test_profile_contracts_are_typed_and_canonical() -> None:
    config = parse_profile_config(
        {"chatModelId": "chat", "systemPrompt": "Ground", "contextLimit": 1000, "outputLimit": 100},
        Workflow.GROUNDED_ASK,
    )
    assert isinstance(config, GroundedAskConfig)
    canonical = canonical_config(config)
    assert canonical["workflow"] == "grounded_ask"
    assert config_digest(config) == config_digest(canonical)
    assert required_capabilities(Workflow.GROUNDED_ASK, canonical) == ("chat",)
    embedding = EmbeddingConfig(embeddingModelId="embed", dimension=1536)
    assert required_capabilities(Workflow.EMBEDDING, embedding) == ("embedding",)


def test_egress_rejects_unsafe_url_shapes() -> None:
    with pytest.raises(GatewayError):
        validate_base_url("https://user:pass@example.invalid")
    with pytest.raises(GatewayError):
        validate_base_url("https://example.invalid/path")
    with pytest.raises(GatewayError):
        validate_base_url("http://example.invalid")
    policy = EgressPolicy(allowed_hosts=("gateway.internal",))
    assert policy.allowed_hosts == ("gateway.internal",)


@pytest.mark.asyncio
async def test_guarded_execution_owns_auth_transport_and_stream_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[dict[str, object]] = []

    class FakeResponse:
        status_code = 200
        is_redirect = False
        headers = {"content-type": "application/json"}

        def __init__(self, chunks: list[bytes]) -> None:
            self._chunks = chunks

        async def __aenter__(self) -> FakeResponse:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def aiter_bytes(self):
            for chunk in self._chunks:
                yield chunk

    class FakeClient:
        def __init__(self, **kwargs: object) -> None:
            requests.append(kwargs)

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            requests.append({"method": method, "url": url, **kwargs})
            return FakeResponse([b'{"choices":[{"message":{"content":"OK"}}]}'])

    async def allowed(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        return ("192.0.2.10",)

    monkeypatch.setattr(egress, "resolve_allowed_addresses", allowed)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    client = GuardedGatewayClient(EgressPolicy(allowed_hosts=("gateway.internal",)))
    value = await client.chat_completion(
        "https://gateway.internal",
        "chat-model",
        {"messages": [{"role": "user", "content": "hello"}]},
        api_key="secret",
    )
    assert value["choices"]
    assert requests[0]["follow_redirects"] is False
    assert requests[0]["trust_env"] is False
    assert requests[1]["headers"] == {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": "Bearer secret",
    }
    assert requests[1]["url"] == "https://gateway.internal/chat/completions"


@pytest.mark.asyncio
async def test_stream_chat_yields_progressively_and_closes_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    yielded: list[bytes] = []
    closed = False

    class Response:
        status_code = 200
        is_redirect = False
        headers: dict[str, str] = {"content-type": "text/event-stream"}

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, *_args: object) -> None:
            nonlocal closed
            closed = True

        async def aiter_bytes(self):
            yield b"data: first\n\n"
            yield b"data: second\n\n"

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            nonlocal closed
            closed = True

        def stream(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    async def allowed(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        return ("192.0.2.10",)

    monkeypatch.setattr(egress, "resolve_allowed_addresses", allowed)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    stream = GuardedGatewayClient(EgressPolicy(allowed_hosts=("gateway.internal",)))
    iterator = stream.stream_chat_completion("https://gateway.internal", "model", {"messages": []})
    first = await anext(iterator)
    yielded.append(first)
    assert yielded == [b"data: first\n\n"]
    await iterator.aclose()
    assert closed is True


@pytest.mark.asyncio
async def test_dns_public_and_redirect_stream_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = EgressPolicy(allowed_hosts=("gateway.internal",), max_response_bytes=4)

    def public_dns(
        *_args: object, **_kwargs: object
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        return [(0, 0, 0, "", ("8.8.8.8", 443))]

    monkeypatch.setattr(egress.socket, "getaddrinfo", public_dns)
    with pytest.raises(GatewayError) as public_error:
        await egress.resolve_allowed_addresses("gateway.internal", policy, 443)
    assert public_error.value.code == "PUBLIC_ADDRESS_REJECTED"

    class Response:
        status_code = 302
        is_redirect = True
        headers: dict[str, str] = {}

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def aiter_bytes(self):
            yield b"oversized"

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    async def allowed(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        return ("192.0.2.10",)

    monkeypatch.setattr(egress, "resolve_allowed_addresses", allowed)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    with pytest.raises(GatewayError) as redirect_error:
        async for _chunk in GuardedGatewayClient(policy).stream_chat_completion(
            "https://gateway.internal", "model", {"messages": []}
        ):
            pass
    assert redirect_error.value.code == "REDIRECT_REJECTED"


@pytest.mark.asyncio
async def test_fake_upstream_executes_discovery_chat_embedding_and_rerank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    class Response:
        status_code = 200
        is_redirect = False
        headers: dict[str, str] = {"content-type": "application/json"}

        def __init__(self, body: dict[str, object]) -> None:
            self._chunks = [json.dumps(body).encode()]

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def aiter_bytes(self):
            for chunk in self._chunks:
                yield chunk

    class Client:
        def __init__(self, **kwargs: object) -> None:
            requests.append(("options", kwargs))

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(
            self, _method: str, url: str, *, json: dict[str, object], **_kwargs: object
        ) -> Response:
            requests.append((url, json))
            if url.endswith("/models"):
                return Response({"data": [{"id": "chat"}, {"id": "embedding"}, {"id": "rerank"}]})
            if url.endswith("/chat/completions"):
                return Response({"choices": [{"message": {"content": "OK"}}]})
            if url.endswith("/embeddings"):
                return Response({"data": [{"embedding": [0.1, 0.2]} for _ in json["input"]]})
            return Response({"results": [{"index": 0, "relevance_score": 0.9}]})

    async def allowed(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        return ("192.0.2.10",)

    monkeypatch.setattr(egress, "resolve_allowed_addresses", allowed)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    client = GuardedGatewayClient(EgressPolicy(allowed_hosts=("gateway.internal",)))
    base_url = "https://gateway.internal"
    assert await client.discover(base_url) == ("chat", "embedding", "rerank")
    assert (await client.chat_completion(base_url, "chat", {"messages": []}))["choices"]
    assert await client.embeddings(base_url, "embedding", ["one", "two"]) == (
        (0.1, 0.2),
        (0.1, 0.2),
    )
    assert await client.rerank(base_url, "rerank", "query", ["one", "two"]) == ((0, 0.9),)
    assert requests[0][1]["trust_env"] is False
    assert all("gateway.internal" in url for url, _payload in requests if url != "options")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "status", "expected"),
    [
        (b"not-json", 200, "INVALID_RESPONSE"),
        (b'{"data": [{}]}', 200, "INVALID_EMBEDDING_RESPONSE"),
        (b'{"results": [{"index": 4, "relevance_score": 0.1}]}', 200, "INVALID_RERANK_RESPONSE"),
        (b"unauthorized", 401, "UPSTREAM_HTTP_ERROR"),
    ],
)
async def test_fake_upstream_rejects_malformed_auth_and_shape_responses(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    status: int,
    expected: str,
) -> None:
    class Response:
        is_redirect = False
        headers: dict[str, str] = {"content-type": "application/json"}

        def __init__(self) -> None:
            self.status_code = status

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def aiter_bytes(self):
            yield body

    class Client:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    async def allowed(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        return ("192.0.2.10",)

    monkeypatch.setattr(egress, "resolve_allowed_addresses", allowed)
    monkeypatch.setattr(httpx, "AsyncClient", Client)
    client = GuardedGatewayClient(EgressPolicy(allowed_hosts=("gateway.internal",)))
    with pytest.raises(GatewayError) as error:
        if expected == "INVALID_EMBEDDING_RESPONSE":
            await client.embeddings("https://gateway.internal", "embedding", ["one"])
        elif expected == "INVALID_RERANK_RESPONSE":
            await client.rerank("https://gateway.internal", "rerank", "q", ["one"])
        else:
            await client.chat_completion("https://gateway.internal", "chat", {"messages": []})
    assert error.value.code == expected


@pytest.mark.asyncio
async def test_fake_upstream_timeout_and_bounded_non_stream_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TimeoutClient:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> TimeoutClient:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        def stream(self, *_args: object, **_kwargs: object):
            raise httpx.ReadTimeout("upstream timeout")

    async def allowed(*_args: object, **_kwargs: object) -> tuple[str, ...]:
        return ("192.0.2.10",)

    monkeypatch.setattr(egress, "resolve_allowed_addresses", allowed)
    monkeypatch.setattr(httpx, "AsyncClient", TimeoutClient)
    client = GuardedGatewayClient(EgressPolicy(allowed_hosts=("gateway.internal",)))
    with pytest.raises(GatewayError, match="Gateway request failed") as timeout:
        await client.chat_completion("https://gateway.internal", "chat", {"messages": []})
    assert timeout.value.code == "TIMEOUT"

    class OversizedResponse(TimeoutClient):
        def stream(self, *_args: object, **_kwargs: object):
            class Response:
                status_code = 200
                is_redirect = False
                headers: dict[str, str] = {}

                async def __aenter__(self) -> Response:
                    return self

                async def __aexit__(self, *_args: object) -> None:
                    return None

                async def aiter_bytes(self):
                    yield b"12345"

            return Response()

    monkeypatch.setattr(httpx, "AsyncClient", OversizedResponse)
    with pytest.raises(GatewayError) as oversized:
        await GuardedGatewayClient(
            EgressPolicy(allowed_hosts=("gateway.internal",), max_response_bytes=4)
        ).chat_completion("https://gateway.internal", "chat", {"messages": []})
    assert oversized.value.code == "RESPONSE_TOO_LARGE"


@pytest.mark.asyncio
async def test_dns_rebinding_and_custom_ca_path_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    def mixed_dns(
        *_args: object, **_kwargs: object
    ) -> list[tuple[object, object, object, object, tuple[str, int]]]:
        return [
            (0, 0, 0, "", ("1.1.1.1", 443)),
            (0, 0, 0, "", ("8.8.8.8", 443)),
        ]

    monkeypatch.setattr(egress.socket, "getaddrinfo", mixed_dns)
    with pytest.raises(GatewayError) as rebinding:
        await egress.resolve_allowed_addresses(
            "gateway.internal", EgressPolicy(allowed_hosts=("gateway.internal",)), 443
        )
    assert rebinding.value.code == "PUBLIC_ADDRESS_REJECTED"

    policy = EgressPolicy(allowed_hosts=("gateway.internal",), custom_ca_dir=str(tmp_path))
    with pytest.raises(GatewayError) as ca_error:
        policy.verify_bundle("..\\outside.pem")
    assert ca_error.value.code == "CUSTOM_CA_UNAVAILABLE"


@pytest.mark.asyncio
async def test_private_cidr_allowlist_is_explicit_and_per_gateway_limits_are_used() -> None:
    policy = EgressPolicy(allowed_cidrs=("127.0.0.0/8",))
    assert await egress.resolve_allowed_addresses("127.0.0.1", policy, 443) == ("127.0.0.1",)

    service = ModelGovernanceService.__new__(ModelGovernanceService)
    service.settings = Settings(
        model_allowed_hosts=("deployment.gateway",),
        model_allowed_cidrs=(),
        model_allow_insecure_private=True,
    )
    gateway_policy = service._policy_for_gateway(
        {
            "allowed_hosts": ("gateway.internal",),
            "allowed_cidrs": ("10.20.0.0/16",),
            "insecure_private": True,
            "max_response_bytes": 4096,
            "connect_timeout_ms": 250,
            "read_timeout_ms": 1500,
            "write_timeout_ms": 1750,
            "pool_timeout_ms": 350,
        }
    )
    assert gateway_policy.allowed_hosts == ("gateway.internal",)
    assert gateway_policy.allowed_cidrs == ("10.20.0.0/16",)
    assert gateway_policy.allow_insecure_private is True
    assert gateway_policy.max_response_bytes == 4096
    assert gateway_policy.read_timeout_seconds == 1.5


def test_auditor_gateway_projection_keeps_health_but_hides_infrastructure() -> None:
    gateway_id = UUID("00000000-0000-0000-0000-000000000001")
    checked_at = "2026-08-25T00:00:00+00:00"
    row = {
        "id": gateway_id,
        "name": "Intranet gateway",
        "normalized_base_url": "https://gateway.internal",
        "enabled": True,
        "allowed_capabilities": ("chat",),
        "tls_mode": "required",
        "insecure_private": False,
        "custom_ca_ref": "ca.pem",
        "version": 2,
        "secret_id": UUID("00000000-0000-0000-0000-000000000002"),
        "created_at": checked_at,
        "updated_at": checked_at,
    }
    projection = ModelGovernanceService._gateway_payload(
        row,
        include_sensitive=False,
        health=(
            {
                "capability": "chat",
                "state": "healthy",
                "reason_code": None,
                "latency_ms": 14,
                "checked_at": checked_at,
            },
        ),
    )
    assert projection["health"][0]["state"] == "healthy"
    assert projection["health"][0]["checked_at"] == checked_at
    assert projection["baseUrl"] is None
    assert projection["customCaRef"] is None
    assert projection["fingerprint"] is None


@pytest.mark.asyncio
async def test_existing_assignment_with_missing_model_is_denied_not_unassigned() -> None:
    class Result:
        def __init__(self, row: dict[str, object] | None) -> None:
            self.row = row

        def mappings(self) -> Result:
            return self

        def first(self) -> dict[str, object] | None:
            return self.row

    class Connection:
        def __init__(self, result: Result) -> None:
            self.result = result

        async def __aenter__(self) -> Connection:
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, *_args: object, **_kwargs: object) -> Result:
            return self.result

    class Engine:
        def __init__(self) -> None:
            self.results = [
                Result(None),
                Result({"profile_id": "profile-1", "profile_version": 3}),
            ]

        def connect(self) -> Connection:
            return Connection(self.results.pop(0))

    service = ModelGovernanceService.__new__(ModelGovernanceService)
    service.engine = Engine()
    result = await service._execution_target(
        "workspace-1", Workflow.TITLE_GENERATION, "chat", decrypt_secret=False
    )
    assert result == {
        "profile_id": "profile-1",
        "profile_version": 3,
        "reason": "UNAVAILABLE",
    }


@pytest.mark.asyncio
async def test_impact_is_read_only_while_mutations_keep_recent_auth_and_csrf() -> None:
    class Identity:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        async def has_capability(self, user_id: str, capability: str) -> bool:
            self.calls.append((user_id, capability))
            return True

    class Governance:
        async def impact(self, model_id: UUID) -> dict[str, object]:
            return {
                "modelId": model_id,
                "dimension": None,
                "affected": [],
                "requiresReindex": False,
            }

    identity = Identity()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(identity_service=identity, model_governance_service=Governance())
        )
    )
    current = ({"recent_auth_at": None}, SimpleNamespace(id="auditor-1"))
    model_id = UUID("00000000-0000-0000-0000-000000000003")
    result = await model_governance_api.impact(model_id, request, current)
    assert result["modelId"] == model_id
    assert identity.calls == [("auditor-1", "model_governance_read")]

    checks: list[str] = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(
        model_governance_api,
        "check_recent_auth",
        lambda *_args: checks.append("recent-auth"),
    )
    monkeypatch.setattr(
        model_governance_api,
        "check_csrf",
        lambda *_args: checks.append("csrf"),
    )
    try:
        await model_governance_api.require(request, current, mutate=True)
    finally:
        monkeypatch.undo()
    assert checks == ["recent-auth", "csrf"]


@pytest.mark.asyncio
async def test_rerank_rejects_nan_and_infinite_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GuardedGatewayClient(EgressPolicy())

    async def invalid_response(**_kwargs: object) -> dict[str, object]:
        return {"results": [{"index": 0, "relevance_score": _kwargs["score"]}]}

    def make_request(score: float):
        async def request_with_score(**kwargs: object) -> dict[str, object]:
            return await invalid_response(score=score, **kwargs)

        return request_with_score

    for score in (float("nan"), float("inf"), float("-inf")):
        monkeypatch.setattr(client, "_request", make_request(score))
        with pytest.raises(GatewayError, match="Gateway request failed") as error:
            await client.rerank("https://gateway.internal", "reranker", "query", ["document"])
        assert error.value.code == "INVALID_RERANK_RESPONSE"
