"""Transport-neutral OAuth/MCP authorization contracts.

These types model the authorization decisions shared by the MCP resource
server, the OAuth authorization server, and the target application services.
They never import FastAPI or API DTO modules; HTTP adapters translate them.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import UTC, datetime
from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Scopes and tool mapping
# ---------------------------------------------------------------------------


class McpScope(str, Enum):
    """OAuth scopes enforced for MCP tool discovery and use."""

    KNOWLEDGE_BASES_READ = "mcp:knowledge-bases:read"
    KNOWLEDGE_READ = "mcp:knowledge:read"
    KNOWLEDGE_SEARCH = "mcp:knowledge:search"
    KNOWLEDGE_ASK = "mcp:knowledge:ask"
    KNOWLEDGE_WRITE = "mcp:knowledge:write"


ALL_MCP_SCOPES: tuple[McpScope, ...] = (
    McpScope.KNOWLEDGE_BASES_READ,
    McpScope.KNOWLEDGE_READ,
    McpScope.KNOWLEDGE_SEARCH,
    McpScope.KNOWLEDGE_ASK,
    McpScope.KNOWLEDGE_WRITE,
)

# Each scope enables a family of tools; a tool may require a single scope.
SCOPE_TOOL_MAP: dict[str, tuple[str, ...]] = {
    McpScope.KNOWLEDGE_BASES_READ.value: ("kb_list_knowledge_bases",),
    McpScope.KNOWLEDGE_READ.value: (
        "kb_list_dir",
        "kb_get_tree",
        "kb_get_note",
        "kb_get_file",
    ),
    McpScope.KNOWLEDGE_SEARCH.value: ("kb_search",),
    McpScope.KNOWLEDGE_ASK.value: ("kb_ask",),
    McpScope.KNOWLEDGE_WRITE.value: (
        "kb_mkdir",
        "kb_create_note",
        "kb_update_note",
        "kb_upload_file",
        "kb_move",
        "kb_delete",
    ),
}

KNOWN_TOOLS: dict[str, str] = {
    tool: scope for scope, tools in SCOPE_TOOL_MAP.items() for tool in tools
}

PKCE_VERIFIER_PATTERN = re.compile(r"[A-Za-z0-9._~-]{43,128}\Z")


def parse_scopes(scopes: str | None) -> tuple[str, ...]:
    """Parse a space-separated scope string into known canonical scopes.

    Unknown scopes are rejected so a typo can never silently grant nothing.
    """
    if not scopes:
        return ()
    requested = tuple(part.strip() for part in scopes.split(" ") if part.strip())
    known = {scope.value for scope in ALL_MCP_SCOPES}
    unknown = set(requested) - known
    if unknown:
        raise ValueError(f"unknown MCP scope(s): {', '.join(sorted(unknown))}")
    # Preserve request order, drop duplicates.
    return tuple(dict.fromkeys(part for part in requested))


def tools_for_scopes(scopes: tuple[str, ...]) -> tuple[str, ...]:
    """Union of tool names enabled by the given canonical scopes."""
    return tuple(dict.fromkeys(tool for scope in scopes for tool in SCOPE_TOOL_MAP.get(scope, ())))


def scope_requires(scope: str, tool_name: str) -> bool:
    """Whether ``tool_name`` is exposed by the given canonical scope."""
    return tool_name in SCOPE_TOOL_MAP.get(scope, ())


def pkce_s256(code_verifier: str) -> str:
    """Validate an RFC 7636 verifier and return its base64url S256 challenge."""
    if not PKCE_VERIFIER_PATTERN.fullmatch(code_verifier):
        raise ValueError("code_verifier must be 43-128 RFC 7636 unreserved characters")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Actors
# ---------------------------------------------------------------------------


class McpActor(BaseModel):
    """Normalized caller identity for a single MCP request.

    One of ``user_id`` (interactive grant) or ``principal_id`` (service
    principal) is set.  Authorization is user-level: grants no longer bind a
    single knowledge base, so every tool call verifies membership and role
    against its target knowledge base in real time.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    actor_type: Literal["human", "service_principal"]
    user_id: str | None = None
    principal_id: str | None = None
    scopes: tuple[str, ...] = ()
    correlation_id: str = Field(default="", alias="correlationId")
    token_id: str | None = Field(default=None, exclude=True, repr=False)
    source_ip: str | None = Field(default=None, exclude=True, repr=False)
    concurrency_limit: int = Field(default=1, ge=1, exclude=True, repr=False)

    @model_validator(mode="after")
    def _require_exactly_one_identity(self) -> McpActor:
        if self.actor_type == "human" and (self.user_id is None or self.principal_id is not None):
            raise ValueError("human actors require only user_id")
        if self.actor_type == "service_principal" and (
            self.principal_id is None or self.user_id is not None
        ):
            raise ValueError("service-principal actors require only principal_id")
        known = {scope.value for scope in ALL_MCP_SCOPES}
        if not self.scopes or not set(self.scopes).issubset(known):
            raise ValueError("actor scopes must be non-empty canonical MCP scopes")
        return self


# ---------------------------------------------------------------------------
# OAuth error mapping
# ---------------------------------------------------------------------------


class OAuthErrorCode(str, Enum):
    """Stable OAuth error codes used in error responses and log metadata.

    These are the safe, redacted error identities an authorization or token
    endpoint may return.  They never contain raw credential material.
    """

    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    INVALID_GRANT = "invalid_grant"
    INVALID_TOKEN = "invalid_token"
    UNSUPPORTED_RESPONSE_TYPE = "unsupported_response_type"
    INVALID_SCOPE = "invalid_scope"
    ACCESS_DENIED = "access_denied"
    SERVER_ERROR = "server_error"
    TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"


# Domain error codes that map onto OAuth errors.  Keep these in one table so
# the resource server and the token endpoint stay consistent.
OAUTH_MAPPING: dict[str, OAuthErrorCode] = {
    "invalid_request": OAuthErrorCode.INVALID_REQUEST,
    "invalid_client": OAuthErrorCode.UNAUTHORIZED_CLIENT,
    "invalid_redirect": OAuthErrorCode.INVALID_REQUEST,
    "invalid_resource": OAuthErrorCode.INVALID_REQUEST,
    "invalid_scope": OAuthErrorCode.INVALID_SCOPE,
    "invalid_code": OAuthErrorCode.INVALID_GRANT,
    "invalid_grant": OAuthErrorCode.INVALID_GRANT,
    "invalid_credential": OAuthErrorCode.INVALID_GRANT,
    "invalid_principal": OAuthErrorCode.INVALID_GRANT,
    "invalid_token": OAuthErrorCode.INVALID_TOKEN,
    "expired_code": OAuthErrorCode.INVALID_GRANT,
    "used_code": OAuthErrorCode.INVALID_GRANT,
    "code_challenge_mismatch": OAuthErrorCode.INVALID_GRANT,
    "verifier_mismatch": OAuthErrorCode.INVALID_GRANT,
    "refresh_reuse": OAuthErrorCode.INVALID_GRANT,
    "insufficient_scope": OAuthErrorCode.INSUFFICIENT_SCOPE,
    "policy_denied": OAuthErrorCode.ACCESS_DENIED,
    "network_denied": OAuthErrorCode.ACCESS_DENIED,
    "rate_limited": OAuthErrorCode.TEMPORARILY_UNAVAILABLE,
    "unsupported_grant_type": OAuthErrorCode.UNSUPPORTED_GRANT_TYPE,
}


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

# Field names whose values must never reach logs, audit events, or error
# bodies.  The set is deliberately conservative; a matched key at any depth is
# redacted by the central recursive redactor.
REDACTED_FIELDS: frozenset[str] = frozenset(
    {
        "authorization",
        "code",
        "code_verifier",
        "code_challenge",
        "code_challenge_method",
        "refresh_token",
        "access_token",
        "verifier",
        "client_secret",
        "secret",
        "password",
        "token",
        "service_secret",
    }
)


def redact_value(
    value: object,
    *,
    holder_key: str = "",
    redact_keys: frozenset[str] = REDACTED_FIELDS,
    _depth: int = 0,
) -> object:
    """Recursively replace redacted field values with a placeholder.

    Works on dicts, lists, tuples, sets, and pydantic models.  A field is
    redacted when its key matches ``redact_keys`` (case-insensitive).  Depth
    guards against pathological nesting.
    """
    if _depth > 20:
        return "<redacted(deeper)>"
    if isinstance(value, dict):
        return {key: _redact_child(value[key], key, redact_keys, _depth) for key in value}
    if isinstance(value, list | tuple | set):
        items = [_redact_child(item, holder_key, redact_keys, _depth) for item in value]
        if isinstance(value, tuple):
            return tuple(items)
        if isinstance(value, set):
            return set(items)
        return items
    if isinstance(value, BaseModel):
        return {
            key: _redact_child(field_value, key, redact_keys, _depth)
            for key, field_value in value.model_dump(by_alias=True).items()
        }
    return value


def _redact_child(
    child: object,
    key: str,
    redact_keys: frozenset[str],
    depth: int,
) -> object:
    if key.lower() in redact_keys:
        return "<redacted>"
    return redact_value(child, holder_key=key, redact_keys=redact_keys, _depth=depth + 1)


# ---------------------------------------------------------------------------
# Well-known metadata contracts
# ---------------------------------------------------------------------------


class AuthorizationServerMetadata(BaseModel):
    """RFC 8414 authorization-server metadata for the OAuth endpoints."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    issuer: str
    authorization_endpoint: str = Field(alias="authorization_endpoint")
    token_endpoint: str = Field(alias="token_endpoint")
    revocation_endpoint: str = Field(alias="revocation_endpoint")
    response_types_supported: tuple[str, ...] = Field(alias="response_types_supported")
    grant_types_supported: tuple[str, ...] = Field(alias="grant_types_supported")
    code_challenge_methods_supported: tuple[str, ...] = Field(
        alias="code_challenge_methods_supported"
    )
    token_endpoint_auth_methods_supported: tuple[str, ...] = Field(
        alias="token_endpoint_auth_methods_supported"
    )
    revocation_endpoint_auth_methods_supported: tuple[str, ...] = Field(
        default=("none",), alias="revocation_endpoint_auth_methods_supported"
    )
    scopes_supported: tuple[str, ...] = Field(alias="scopes_supported")
    authorization_response_iss_parameter_supported: bool = Field(
        default=True, alias="authorization_response_iss_parameter_supported"
    )


class ProtectedResourceMetadata(BaseModel):
    """RFC 9728 protected-resource metadata for the canonical `/mcp` resource."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource: str
    authorization_servers: tuple[str, ...] = Field(alias="authorization_servers")
    scopes_supported: tuple[str, ...] = Field(alias="scopes_supported")
    bearer_methods_supported: tuple[Literal["header"], ...] = Field(
        default=("header",), alias="bearer_methods_supported"
    )


# ---------------------------------------------------------------------------
# Metadata URL helpers
# ---------------------------------------------------------------------------


def oauth_metadata_url(public_origin: str, path: str) -> str:
    """Normalize a public metadata URL against a normalized origin."""
    origin = public_origin.rstrip("/")
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("public origin must be an absolute HTTP(S) URL")
    if not path.startswith("/"):
        raise ValueError("metadata path must start with '/'")
    return f"{origin}{path}"


def is_canonical_resource_url(resource: str) -> bool:
    """Whether a resource identifier is a canonical absolute HTTP(S) URL path."""

    parsed = urlparse(resource)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.query or parsed.fragment:
        return False
    return True


def _utc_now() -> datetime:
    return datetime.now(UTC)
