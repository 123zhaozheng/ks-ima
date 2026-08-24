from __future__ import annotations

from pathlib import Path

import pytest

from ima.api.app import create_app
from ima.cli import _parse_legacy_acl
from ima.config import Settings
from ima.domain.authorization import (
    DEFAULT_ROLE_GRANTS,
    AclAction,
    WorkspaceRole,
    legacy_role,
    validate_grants,
)
from ima.infrastructure.db.authorization import accessible_folder_ids_sql


def test_default_role_matrix_is_explicit_and_has_no_platform_bypass() -> None:
    assert DEFAULT_ROLE_GRANTS[WorkspaceRole.WORKSPACE_ADMIN] == frozenset(AclAction)
    assert AclAction.MANAGE_ACL not in DEFAULT_ROLE_GRANTS[WorkspaceRole.EDITOR]
    assert DEFAULT_ROLE_GRANTS[WorkspaceRole.VIEWER] == frozenset(
        {
            AclAction.VIEW_METADATA,
            AclAction.VIEW_CONTENT,
            AclAction.DOWNLOAD,
            AclAction.ASK,
        }
    )


def test_legacy_roles_map_without_guessing() -> None:
    assert legacy_role("owner") is WorkspaceRole.WORKSPACE_ADMIN
    assert legacy_role("admin") is WorkspaceRole.WORKSPACE_ADMIN
    assert legacy_role("member") is WorkspaceRole.EDITOR
    assert legacy_role("guest") is WorkspaceRole.VIEWER
    with pytest.raises(KeyError):
        legacy_role("unknown")


def test_acl_dependencies_are_rejected() -> None:
    with pytest.raises(ValueError, match="ask requires"):
        validate_grants({AclAction.ASK})
    with pytest.raises(ValueError, match="download requires"):
        validate_grants({AclAction.DOWNLOAD, AclAction.VIEW_CONTENT})
    assert validate_grants(
        {AclAction.DOWNLOAD, AclAction.VIEW_METADATA, AclAction.VIEW_CONTENT}
    ) == frozenset({AclAction.DOWNLOAD, AclAction.VIEW_METADATA, AclAction.VIEW_CONTENT})


def test_workspace_openapi_contracts_are_registered_and_bridge_is_private() -> None:
    app = create_app(Settings(environment="test"))
    schema = app.openapi()
    assert "/api/v1/workspaces" in schema["paths"]
    assert "/api/v1/workspaces/{workspace_id}/folders/{folder_id}/acl" in schema["paths"]
    assert "/api/v1/admin/workspaces/{workspace_id}/workspace-admin-repair" in schema["paths"]
    assert "/api/v1/internal/session/introspect" not in schema["paths"]
    assert "/api/v1/internal/authorization/decide" not in schema["paths"]


def test_authorization_migration_contains_all_target_tables_and_downgrade_guard() -> None:
    source = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "20260825_0003_workspace_authorization.py"
    ).read_text()
    for table in (
        "workspace_members",
        "workspace_invitations",
        "workspace_groups",
        "workspace_group_members",
        "folders",
        "folder_closure",
        "folder_acls",
        "folder_acl_entries",
        "workspace_authorization_migration",
    ):
        assert f"ima.{table}" in source
    assert "explicit snapshot" in source


def test_legacy_acl_parser_is_strict_and_normalizes_dependencies() -> None:
    entries, error = _parse_legacy_acl(
        {
            "acl": {
                "inherit": False,
                "aces": [
                    {"principalType": "role", "principalId": "guest", "actions": ["view", "ask"]}
                ],
            }
        }
    )
    assert error is None
    assert entries is not None
    assert {item[2] for item in entries} == {"view_metadata", "view_content", "ask"}
    _, error = _parse_legacy_acl(
        {
            "acl": {
                "inherit": False,
                "aces": [{"principalType": "role", "principalId": "bad", "actions": ["view"]}],
            }
        }
    )
    assert error == "unknown_acl_role"


def test_policy_predicate_requires_all_dependencies_for_the_same_subject() -> None:
    sql = accessible_folder_ids_sql()
    assert "e.action=:requested_action" in sql
    assert "required_actions" in sql
    assert "required_entry.subject_type=e.subject_type" in sql
    assert "required_entry.subject_id=e.subject_id" in sql
