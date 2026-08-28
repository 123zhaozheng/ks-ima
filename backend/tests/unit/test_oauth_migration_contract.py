"""Unit tests for the OAuth/MCP schema isolation and domain contracts.

These tests do not require PostgreSQL.  They assert that the migration never
touches the legacy ``public.connector`` schema, that the OAuth/MCP tables keep a
digest-only storage contract, and that the transport-neutral domain records and
CIDR normalization behave correctly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from ima.domain.oauth import (
    GrantRecord,
    GrantState,
    normalize_cidr_allowlist,
)

MIGRATION_PATH = Path(__file__).parents[2] / "migrations/versions/20260826_0008_oauth_mcp.py"
HARDENING_PATH = (
    Path(__file__).parents[2] / "migrations/versions/20260828_0009_mcp_concurrency_hardening.py"
)


def test_migration_never_touches_public_connector() -> None:
    text = MIGRATION_PATH.read_text()
    assert "public.connector" not in text
    assert "CREATE TABLE ima.mcp_concurrency_leases" in text
    assert "ix_mcp_concurrency_source_expiry" in text
    assert "request_digest varchar(128) NOT NULL UNIQUE" in text
    assert '"public"' not in text
    assert "public." not in text
    assert "DROP SCHEMA IF EXISTS public" not in text
    # The migration stays in schema ima.
    assert "ima.mcp_clients" in text


def test_migration_rev_chain_continues_after_search() -> None:
    text = MIGRATION_PATH.read_text()
    assert 'revision = "20260826_0008"' in text
    assert 'down_revision = "20260826_0007"' in text
    hardening = HARDENING_PATH.read_text()
    assert 'revision = "20260828_0009"' in hardening
    assert 'down_revision = "20260826_0008"' in hardening
    assert "ix_mcp_concurrency_source_expiry" in hardening


def test_secret_bearing_columns_are_digest_only() -> None:
    """Every secret-bearing column must store only a peppered HMAC digest."""
    text = MIGRATION_PATH.read_text()
    # These columns must exist and never be named after a raw value in the
    # schema (the raw code/token/secret is never stored).
    for column in (
        "code_digest",
        "token_digest",
        "client_secret_digest",
        "digest",
    ):
        assert column in text
    # No column stores a raw password/token/secret literal prefix.
    for forbidden in ("raw_code", "raw_token", "raw_secret", "verifier_digest"):
        assert forbidden not in text


def test_scope_check_constraints_covered() -> None:
    """All canonical MCP scopes are enforced by the migration CHECK guards."""
    text = MIGRATION_PATH.read_text()
    for scope in (
        "mcp:workspaces:read",
        "mcp:knowledge:read",
        "mcp:knowledge:search",
        "mcp:knowledge:ask",
        "mcp:knowledge:write",
    ):
        assert scope in text


def test_schema_enforces_oauth_lineage_and_actor_shape() -> None:
    text = MIGRATION_PATH.read_text()
    assert "FOREIGN KEY(client_id,redirect_uri)" in text
    assert "FOREIGN KEY(family_id,grant_id)" in text
    assert "replaced_by uuid UNIQUE REFERENCES ima.mcp_refresh_tokens(id)" in text
    assert "replaced_by uuid REFERENCES ima.mcp_credentials(id)" in text
    assert "grant_id IS NOT NULL AND principal_id IS NULL AND client_id IS NOT NULL" in text
    assert "grant_id IS NULL AND principal_id IS NOT NULL AND client_id IS NULL" in text
    assert "secret_prefix varchar(32)" in text


def test_grant_record_is_bound_to_one_boundary() -> None:
    grant = GrantRecord(
        id=__import__("uuid").uuid4(),
        user_id="user-1",
        client_id=__import__("uuid").uuid4(),
        canonical_resource="https://example.com/mcp",
        workspace_id="workspace-1",
        folder_root_id=None,
        scopes=("mcp:knowledge:read",),
        state=GrantState.ACTIVE,
        expires_at=datetime.now(UTC),
    )
    assert grant.canonical_resource == "https://example.com/mcp"
    assert grant.state is GrantState.ACTIVE


def test_normalize_cidr_allowlist_validates_and_dedupes() -> None:
    assert normalize_cidr_allowlist(("10.0.0.0/8", "10.1.2.3")) == (
        "10.0.0.0/8",
        "10.1.2.3/32",
    )
    assert normalize_cidr_allowlist(("192.168.0.0/16", "192.168.0.0/16")) == ("192.168.0.0/16",)
    with pytest.raises(ValueError):
        normalize_cidr_allowlist(("not-a-cidr",))
