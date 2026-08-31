"""Knowledge base authorization contracts (unit scope).

Covers the simplified role matrix, the membership-only SQL predicate, the
share-link security mode (salted peppered digests, join URLs, expiry/revocation
matrix, idempotent accept), and the member-role mutation policy.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from ima.application.authorization import (
    KbError,
    KbService,
    accepted_member_role,
    role_change_problem,
    share_link_problem,
    share_link_url,
    share_token_digest,
)
from ima.config import Settings
from ima.domain.authorization import DEFAULT_ROLE_GRANTS, KbAction, KbRole, role_allows
from ima.infrastructure.db.authorization import membership_sql, role_at_least

MIGRATIONS = Path(__file__).parents[2] / "migrations" / "versions"
SOURCE = Path(__file__).parents[2] / "src" / "ima"


def service() -> KbService:
    return KbService(cast(Any, SimpleNamespace()), Settings(environment="test"))


def test_role_matrix_is_simplified_to_three_member_roles() -> None:
    assert set(DEFAULT_ROLE_GRANTS) == {KbRole.OWNER, KbRole.EDITOR, KbRole.VIEWER}
    viewer = DEFAULT_ROLE_GRANTS[KbRole.VIEWER]
    assert viewer == frozenset(
        {KbAction.VIEW_METADATA, KbAction.VIEW_CONTENT, KbAction.DOWNLOAD, KbAction.ASK}
    )
    editor = DEFAULT_ROLE_GRANTS[KbRole.EDITOR]
    assert viewer < editor
    for action in (KbAction.CREATE_CHILD, KbAction.EDIT, KbAction.MOVE, KbAction.DELETE):
        assert action in editor
    assert DEFAULT_ROLE_GRANTS[KbRole.OWNER] == frozenset(KbAction)
    assert role_allows(KbRole.EDITOR, KbAction.EDIT)
    assert not role_allows(KbRole.VIEWER, KbAction.CREATE_CHILD)
    assert not role_allows(KbRole.VIEWER, KbAction.DELETE)


def test_role_level_orders_write_access() -> None:
    assert role_at_least(KbRole.OWNER, KbRole.EDITOR)
    assert role_at_least(KbRole.EDITOR, KbRole.EDITOR)
    assert role_at_least(KbRole.VIEWER, KbRole.VIEWER)
    assert not role_at_least(KbRole.VIEWER, KbRole.EDITOR)
    assert not role_at_least(KbRole.EDITOR, KbRole.OWNER)


def test_membership_predicate_has_no_acl_group_or_workspace_joins() -> None:
    sql = membership_sql().lower()
    assert "ima.kb_members" in sql
    assert "ima.knowledge_bases" in sql
    assert "m.state='active'" in sql
    for forbidden in ("folder_acl", "workspace", "group", "invit"):
        assert forbidden not in sql


def test_kb_authorization_migration_targets_new_tables_only() -> None:
    source = (MIGRATIONS / "20260825_0003_kb_authorization.py").read_text()
    for table in ("ima.kb_members", "ima.kb_share_links", "ima.folders", "ima.folder_closure"):
        assert table in source
    for retired in (
        "workspace_invitations",
        "workspace_groups",
        "workspace_group_members",
        "folder_acls",
        "folder_acl_entries",
    ):
        assert retired not in source
    assert "'owner','editor','viewer'" in source
    assert "CHECK (role IN ('editor','viewer'))" in source
    identity = (MIGRATIONS / "20260824_0002_identity_platform.py").read_text()
    assert "ima.knowledge_bases" in identity


def test_kb_service_source_drops_legacy_authorization_surface() -> None:
    source = (SOURCE / "application" / "authorization.py").read_text()
    for retired in (
        "workspace_invitations",
        "workspace_groups",
        "folder_acl",
        "manage_acl",
        "knowledge_manager",
        "repair_admin",
        "permission_preview",
        "send_invitation",
        "workspace_id",
    ):
        assert retired not in source
    assert "ima.kb_members" in source
    assert "ima.kb_share_links" in source
    assert "/join/" in source


def test_identity_capabilities_renamed_to_knowledge_bases() -> None:
    source = (SOURCE / "application" / "identity.py").read_text()
    assert "knowledge_bases_read" in source
    assert "knowledge_bases_manage" in source
    assert "workspaces_read" not in source
    assert "workspaces_manage" not in source


def test_share_token_digest_is_salted_peppered() -> None:
    value = share_token_digest("opaque-token", "salt-a", "pepper")
    assert value == share_token_digest("opaque-token", "salt-a", "pepper")
    assert value != share_token_digest("opaque-token", "salt-b", "pepper")
    assert value != share_token_digest("opaque-token", "salt-a", "other-pepper")
    assert value != share_token_digest("other-token", "salt-a", "pepper")
    # Matches the varchar(64) token_digest column.
    assert len(value) == 64


def test_share_link_url_uses_join_route() -> None:
    assert share_link_url("https://ima.example", "tok") == "https://ima.example/join/tok"
    assert share_link_url("https://ima.example/", "tok") == "https://ima.example/join/tok"


def test_share_link_problem_matrix() -> None:
    at = datetime(2026, 8, 31, tzinfo=UTC)
    future = at + timedelta(days=1)
    assert share_link_problem(revoked_at=None, expires_at=None, kb_active=True, at=at) is None
    assert share_link_problem(revoked_at=None, expires_at=future, kb_active=True, at=at) is None
    assert (
        share_link_problem(revoked_at=at, expires_at=None, kb_active=True, at=at)
        == "SHARE_LINK_INVALID"
    )
    # An expiry at or before the current instant rejects the joiner.
    assert (
        share_link_problem(revoked_at=None, expires_at=at, kb_active=True, at=at)
        == "SHARE_LINK_EXPIRED"
    )
    assert (
        share_link_problem(revoked_at=None, expires_at=None, kb_active=False, at=at)
        == "KB_NOT_FOUND"
    )


def test_accepting_a_share_link_is_idempotent_and_never_demotes() -> None:
    assert accepted_member_role(None, "viewer") == "viewer"
    assert accepted_member_role(None, "editor") == "editor"
    assert accepted_member_role("owner", "viewer") == "owner"
    assert accepted_member_role("editor", "viewer") == "editor"
    assert accepted_member_role("viewer", "editor") == "viewer"


def test_member_role_change_policy() -> None:
    # Only the owner manages members, and only editor<->viewer may change.
    assert role_change_problem(actor_role="owner", target_role="viewer", new_role="editor") is None
    assert role_change_problem(actor_role="owner", target_role="editor", new_role="viewer") is None
    assert (
        role_change_problem(actor_role="editor", target_role="viewer", new_role="editor")
        == "MEMBERSHIP_FORBIDDEN"
    )
    assert (
        role_change_problem(actor_role="viewer", target_role="viewer", new_role="editor")
        == "MEMBERSHIP_FORBIDDEN"
    )
    assert (
        role_change_problem(actor_role="owner", target_role="owner", new_role="editor")
        == "OWNER_PROTECTED"
    )
    assert (
        role_change_problem(actor_role="owner", target_role="viewer", new_role="owner")
        == "INVALID_ROLE"
    )


@pytest.mark.asyncio
async def test_create_share_link_rejects_unknown_role_and_bad_expiry() -> None:
    with pytest.raises(KbError) as invalid_role:
        await service().create_share_link(actor_user_id="owner-1", kb_id="kb-1", role="admin")
    assert invalid_role.value.status_code == 400
    assert invalid_role.value.code == "INVALID_SHARE_ROLE"
    with pytest.raises(KbError) as bad_expiry:
        await service().create_share_link(
            actor_user_id="owner-1", kb_id="kb-1", role="viewer", expires_in_days=0
        )
    assert bad_expiry.value.status_code == 400
    assert bad_expiry.value.code == "INVALID_SHARE_EXPIRY"


@pytest.mark.asyncio
async def test_create_knowledge_base_rejects_blank_name_without_database() -> None:
    with pytest.raises(KbError) as invalid_name:
        await service().create_knowledge_base("user-1", "   ")
    assert invalid_name.value.status_code == 400
    assert invalid_name.value.code == "INVALID_KB_NAME"


def test_kb_service_public_surface_matches_contract() -> None:
    names = {
        name
        for name in dir(KbService)
        if not name.startswith("_") and callable(getattr(KbService, name))
    }
    expected = {
        "require_membership",
        "require_write_access",
        "list_knowledge_bases",
        "get_knowledge_base",
        "create_knowledge_base",
        "rename_knowledge_base",
        "archive_knowledge_base",
        "restore_knowledge_base",
        "delete_archived_knowledge_base",
        "list_members",
        "update_member_role",
        "remove_member",
        "leave_knowledge_base",
        "folders",
        "breadcrumbs",
        "create_folder",
        "folder",
        "rename_folder",
        "move_folder",
        "reorder_folder",
        "delete_folder",
        "create_share_link",
        "list_share_links",
        "revoke_share_link",
        "accept_share_link",
    }
    assert expected <= names
    for retired in (
        "leave",
        "delete_knowledge_base",
        "set_acl",
        "acl",
        "acl_subjects",
        "permission_preview",
        "trash_folder",
        "restore_folder",
    ):
        assert retired not in names


def test_router_facing_signatures_accept_positional_calls() -> None:
    surfaces = {
        KbService.create_share_link: [
            "self",
            "actor_user_id",
            "kb_id",
            "role",
            "expires_in_days",
        ],
        KbService.list_share_links: ["self", "actor_user_id", "kb_id"],
        KbService.revoke_share_link: ["self", "actor_user_id", "kb_id", "link_id"],
        KbService.accept_share_link: ["self", "user_id", "token"],
        KbService.update_member_role: [
            "self",
            "actor_id",
            "kb_id",
            "user_id",
            "role",
            "expected_version",
        ],
        KbService.remove_member: ["self", "actor_id", "kb_id", "user_id", "expected_version"],
        KbService.leave_knowledge_base: ["self", "actor_id", "kb_id"],
        KbService.delete_archived_knowledge_base: ["self", "actor_id", "kb_id"],
    }
    for method, params in surfaces.items():
        signature = inspect.signature(method)
        assert list(signature.parameters) == params
        assert all(
            parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
            for parameter in signature.parameters.values()
        )
