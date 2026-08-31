"""OpenAPI contract tests for the knowledge base API surface.

Covers the kb-first simplify: /knowledge-bases CRUD, members, share links,
folder tree, and admin knowledge base endpoints are mounted; the retired
workspace invitation/group/ACL/permission-preview/repair endpoints are absent.
"""

from __future__ import annotations

import pytest

from ima.api.app import create_app
from ima.config import Settings


@pytest.fixture(scope="module")
def schema() -> dict:
    app = create_app(Settings(environment="test"))
    return app.openapi()


def test_knowledge_base_crud_endpoints_are_registered(schema: dict) -> None:
    paths = schema["paths"]
    assert set(paths["/api/v1/knowledge-bases"]) == {"get", "post"}
    assert set(paths["/api/v1/knowledge-bases/{kb_id}"]) == {"get", "patch", "delete"}
    assert "post" in paths["/api/v1/knowledge-bases/{kb_id}/archive"]
    assert "post" in paths["/api/v1/knowledge-bases/{kb_id}/restore"]
    assert paths["/api/v1/knowledge-bases"]["get"]["operationId"] == "listKnowledgeBases"
    assert paths["/api/v1/knowledge-bases"]["post"]["operationId"] == "createKnowledgeBase"
    assert paths["/api/v1/knowledge-bases/{kb_id}"]["get"]["operationId"] == "getKnowledgeBase"
    assert paths["/api/v1/knowledge-bases/{kb_id}"]["patch"]["operationId"] == "renameKnowledgeBase"
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/archive"]["post"]["operationId"]
        == "archiveKnowledgeBase"
    )
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/restore"]["post"]["operationId"]
        == "restoreKnowledgeBase"
    )
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}"]["delete"]["operationId"] == "deleteKnowledgeBase"
    )


def test_member_endpoints_are_registered_without_add_or_search(schema: dict) -> None:
    paths = schema["paths"]
    assert "get" in paths["/api/v1/knowledge-bases/{kb_id}/members"]
    member_item = paths["/api/v1/knowledge-bases/{kb_id}/members/{user_id}"]
    assert set(member_item) == {"patch", "delete"}
    assert "post" in paths["/api/v1/knowledge-bases/{kb_id}/leave"]
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/members"]["get"]["operationId"]
        == "listKnowledgeBaseMembers"
    )
    assert member_item["patch"]["operationId"] == "updateKnowledgeBaseMemberRole"
    assert member_item["delete"]["operationId"] == "removeKnowledgeBaseMember"
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/leave"]["post"]["operationId"]
        == "leaveKnowledgeBase"
    )
    # Membership joins happen through share links; direct add/search are gone.
    assert "post" not in paths["/api/v1/knowledge-bases/{kb_id}/members"]


def test_member_role_patch_only_allows_editor_and_viewer(schema: dict) -> None:
    components = schema["components"]["schemas"]
    assert components["MemberRolePatchRequest"]["properties"]["role"]["enum"] == [
        "editor",
        "viewer",
    ]
    assert components["KbMember"]["properties"]["role"]["enum"] == ["owner", "editor", "viewer"]


def test_share_link_endpoints_are_registered(schema: dict) -> None:
    paths = schema["paths"]
    share_links = paths["/api/v1/knowledge-bases/{kb_id}/share-links"]
    assert set(share_links) == {"get", "post"}
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/share-links/{link_id}"]["delete"]["operationId"]
        == "revokeKnowledgeBaseShareLink"
    )
    assert share_links["get"]["operationId"] == "listKnowledgeBaseShareLinks"
    assert share_links["post"]["operationId"] == "createKnowledgeBaseShareLink"
    accept = paths["/api/v1/kb-share-links/{token}/accept"]
    assert accept["post"]["operationId"] == "acceptKbShareLink"
    components = schema["components"]["schemas"]
    assert components["ShareLinkCreateRequest"]["properties"]["role"]["enum"] == [
        "editor",
        "viewer",
    ]
    share_link = components["ShareLink"]["properties"]
    assert set(share_link) == {"id", "kbId", "url", "role", "expiresAt", "revokedAt", "createdAt"}


def test_folder_tree_endpoints_are_registered(schema: dict) -> None:
    paths = schema["paths"]
    base = "/api/v1/knowledge-bases/{kb_id}/folders"
    assert set(paths[base]) == {"get", "post"}
    item = paths[f"{base}/{{folder_id}}"]
    assert set(item) == {"get", "patch", "delete"}
    assert paths[f"{base}/{{folder_id}}/breadcrumbs"]["get"]
    assert paths[f"{base}/{{folder_id}}/move"]["post"]
    assert paths[f"{base}/{{folder_id}}/reorder"]["post"]
    assert paths[base]["get"]["operationId"] == "listKnowledgeBaseFolders"
    assert paths[base]["post"]["operationId"] == "createKnowledgeBaseFolder"
    assert item["get"]["operationId"] == "getKnowledgeBaseFolder"
    assert item["patch"]["operationId"] == "renameKnowledgeBaseFolder"
    assert item["delete"]["operationId"] == "deleteKnowledgeBaseFolder"
    folder = schema["components"]["schemas"]["Folder"]["properties"]
    assert "kbId" in folder
    assert "workspaceId" not in folder
    assert "aclAnchorId" not in folder


def test_admin_knowledge_base_endpoints_are_registered(schema: dict) -> None:
    paths = schema["paths"]
    assert set(paths["/api/v1/admin/knowledge-bases"]) == {"get", "post"}
    assert "post" in paths["/api/v1/admin/knowledge-bases/{kb_id}/archive"]
    assert "post" in paths["/api/v1/admin/knowledge-bases/{kb_id}/restore"]
    assert "delete" in paths["/api/v1/admin/knowledge-bases/{kb_id}"]
    assert paths["/api/v1/admin/knowledge-bases"]["get"]["operationId"] == "adminListKnowledgeBases"
    assert (
        paths["/api/v1/admin/knowledge-bases"]["post"]["operationId"] == "adminCreateKnowledgeBase"
    )
    request = schema["components"]["schemas"]["KnowledgeBaseRequest"]["properties"]
    assert "initialOwnerUserId" in request
    assert "initialAdminUserId" not in request


def test_model_governance_kb_endpoints_are_registered(schema: dict) -> None:
    paths = schema["paths"]
    assert (
        paths["/api/v1/knowledge-bases/{kb_id}/capabilities"]["get"]["operationId"]
        == "listKnowledgeBaseModelCapabilities"
    )
    assignments = "/api/v1/admin/knowledge-bases/{kb_id}/profile-assignments"
    assert "get" in paths[assignments]
    workflow = f"{assignments}/{{workflow}}"
    assert set(paths[workflow]) == {"put", "delete"}
    assert paths[workflow]["put"]["operationId"] == "assignKnowledgeBaseCapabilityProfile"
    assert paths[workflow]["delete"]["operationId"] == "removeKnowledgeBaseCapabilityProfile"


def test_retired_workspace_endpoints_are_absent(schema: dict) -> None:
    for path in schema["paths"]:
        lowered = path.casefold()
        assert "workspace" not in lowered, path
        assert "invitation" not in lowered, path
        assert "/acl" not in lowered, path
        assert "permission-preview" not in lowered, path
        assert "repair" not in lowered, path
        assert "/groups" not in lowered, path
        assert "/internal/" not in path


def test_retired_workspace_contract_models_are_absent(schema: dict) -> None:
    components = schema["components"]["schemas"]
    for retired in (
        "MemberWorkspace",
        "WorkspaceMember",
        "MemberAddRequest",
        "Invitation",
        "InvitationCreateRequest",
        "WorkspaceGroup",
        "FolderAcl",
        "AclEntry",
        "AclSubject",
        "PermissionPreviewRequest",
        "WorkspaceAdminRepairRequest",
        "UserSearchResult",
    ):
        assert retired not in components
