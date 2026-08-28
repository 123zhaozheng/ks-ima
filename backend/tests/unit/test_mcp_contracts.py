"""Unit tests for the transport-neutral OAuth/MCP contracts and redaction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ima.application.mcp_contracts import (
    ALL_MCP_SCOPES,
    OAUTH_MAPPING,
    SCOPE_TOOL_MAP,
    AuthorizationServerMetadata,
    McpActor,
    McpScope,
    OAuthErrorCode,
    ProtectedResourceMetadata,
    is_canonical_resource_url,
    oauth_metadata_url,
    parse_scopes,
    pkce_s256,
    redact_value,
    tools_for_scopes,
)
from ima.config import Settings

# ---------------------------------------------------------------------------
# Scope and tool mapping
# ---------------------------------------------------------------------------


def test_scope_enum_values_are_canonical() -> None:
    assert McpScope.WORKSPACES_READ.value == "mcp:workspaces:read"
    assert McpScope.KNOWLEDGE_READ.value == "mcp:knowledge:read"
    assert McpScope.KNOWLEDGE_SEARCH.value == "mcp:knowledge:search"
    assert McpScope.KNOWLEDGE_ASK.value == "mcp:knowledge:ask"
    assert McpScope.KNOWLEDGE_WRITE.value == "mcp:knowledge:write"


def test_parse_scopes_accepts_known_and_preserves_order() -> None:
    parsed = parse_scopes("mcp:knowledge:read mcp:knowledge:search mcp:knowledge:read")
    assert parsed == ("mcp:knowledge:read", "mcp:knowledge:search")


def test_parse_scopes_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        parse_scopes("mcp:knowledge:read mcp:bogus:read")


def test_parse_scopes_empty() -> None:
    assert parse_scopes(None) == ()
    assert parse_scopes("") == ()


def test_oauth_error_mapping_distinguishes_bearer_from_token_exchange() -> None:
    assert OAUTH_MAPPING["invalid_grant"] is OAuthErrorCode.INVALID_GRANT
    assert OAUTH_MAPPING["invalid_token"] is OAuthErrorCode.INVALID_TOKEN


def test_pkce_s256_matches_rfc_7636_vector() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert pkce_s256(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    with pytest.raises(ValueError):
        pkce_s256("too-short")
    with pytest.raises(ValueError):
        pkce_s256("x" * 42 + "+")


def test_tools_for_scopes_union_matches_tool_map() -> None:
    read = tools_for_scopes((McpScope.KNOWLEDGE_READ.value,))
    assert "kb_get_tree" in read
    assert "kb_mkdir" not in read
    assert set(tools_for_scopes(("mcp:knowledge:write",))) == set(
        SCOPE_TOOL_MAP[McpScope.KNOWLEDGE_WRITE.value]
    )


def test_every_scope_maps_to_at_least_one_tool() -> None:
    for scope in ALL_MCP_SCOPES:
        assert SCOPE_TOOL_MAP[scope.value], f"{scope.value} maps to no tools"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


def test_redaction_handles_nested_structures() -> None:
    payload = {
        "access_token": "raw-token",
        "nested": {"code_verifier": "raw-verifier", "keep": "visible"},
        "list": [{"refresh_token": "raw-refresh"}, {"secret": "x"}],
        "model": McpActor(
            actor_type="human",
            user_id="u1",
            workspace_id="w1",
            correlationId="c1",
            scopes=("mcp:knowledge:read",),
        ),
    }
    redacted = redact_value(payload)
    assert redacted["access_token"] == "<redacted>"
    assert redacted["nested"]["code_verifier"] == "<redacted>"
    assert redacted["nested"]["keep"] == "visible"
    assert redacted["list"][0]["refresh_token"] == "<redacted>"
    assert redacted["list"][1]["secret"] == "<redacted>"
    # pydantic model fields are dumped to a dict and secret fields replaced.
    assert redacted["model"]["correlationId"] == "c1"


def test_redaction_is_case_insensitive() -> None:
    assert redact_value({"Access_Token": "v"})["Access_Token"] == "<redacted>"


def test_redact_never_touches_unrelated_fields() -> None:
    payload = {"workspace_id": "w1", "path": "/a/b"}
    assert redact_value(payload) == payload


# ---------------------------------------------------------------------------
# Metadata URLs and resource identity
# ---------------------------------------------------------------------------


def test_oauth_metadata_url_normalizes_origin() -> None:
    url = oauth_metadata_url("https://example.com/", "/.well-known/oauth-authorization-server")
    assert url == "https://example.com/.well-known/oauth-authorization-server"
    with pytest.raises(ValueError):
        oauth_metadata_url("example.com", "/x")


def test_is_canonical_resource_url() -> None:
    assert is_canonical_resource_url("https://example.com/mcp")
    assert is_canonical_resource_url("https://example.com/mcp")
    assert not is_canonical_resource_url("example.com/mcp")
    assert not is_canonical_resource_url("https://example.com/mcp?x=1")


def test_metadata_contracts_serialize() -> None:
    as_meta = AuthorizationServerMetadata(
        issuer="https://example.com",
        authorization_endpoint="https://example.com/oauth/authorize",
        token_endpoint="https://example.com/oauth/token",
        revocation_endpoint="https://example.com/oauth/revoke",
        response_types_supported=("code",),
        grant_types_supported=("authorization_code", "refresh_token"),
        code_challenge_methods_supported=("S256",),
        token_endpoint_auth_methods_supported=("none",),
        scopes_supported=("mcp:workspaces:read",),
    )
    data = as_meta.model_dump(by_alias=True)
    assert data["response_types_supported"] == ("code",)
    assert data["grant_types_supported"] == ("authorization_code", "refresh_token")

    pr = ProtectedResourceMetadata(
        resource="https://example.com/mcp",
        authorization_servers=("https://example.com",),
        scopes_supported=("mcp:workspaces:read",),
    )
    assert pr.model_dump(by_alias=True)["authorization_servers"] == ("https://example.com",)
    assert pr.model_dump(by_alias=True)["bearer_methods_supported"] == ("header",)


def test_mcp_actor_requires_bound_fields() -> None:
    with pytest.raises(ValidationError):
        McpActor(
            actor_type="human",
            user_id=None,
            principal_id=None,
            workspace_id="w1",
            scopes=("mcp:knowledge:read",),
        )
    with pytest.raises(ValidationError):
        McpActor(
            actor_type="human",
            principal_id="p1",
            workspace_id="w1",
            scopes=("mcp:knowledge:read",),
        )


# ---------------------------------------------------------------------------
# Settings: canonical resource and OAuth caps
# ---------------------------------------------------------------------------


def test_mcp_resource_url_is_derived() -> None:
    settings = Settings(environment="test")
    assert settings.mcp_resource_url == "http://localhost:8080/mcp"


def test_mcp_oauth_caps_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", oauth_access_token_seconds=99999)
    with pytest.raises(ValidationError):
        Settings(environment="test", service_credential_max_seconds=999999999)
    with pytest.raises(ValidationError):
        Settings(environment="test", credential_rotation_overlap_seconds=9999)
    # A deployment may shorten durations.
    settings = Settings(environment="test", oauth_access_token_seconds=60)
    assert settings.oauth_access_token_seconds == 60
