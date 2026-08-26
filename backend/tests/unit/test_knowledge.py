from __future__ import annotations

from ima.api.app import create_app
from ima.domain.knowledge import ListingCursor, TrashCursor, markdown_digest, normalize_name


def test_knowledge_cursor_round_trip_is_opaque_and_typed() -> None:
    cursor = ListingCursor("root", 7, 3, "note", "document-id")
    encoded = cursor.encode()
    assert "root" not in encoded
    assert ListingCursor.decode(encoded) == cursor


def test_trash_cursor_round_trip_is_opaque_and_workspace_bound() -> None:
    cursor = TrashCursor("workspace", "2026-08-25T00:00:00+00:00", "document-id")
    encoded = cursor.encode()
    assert "workspace" not in encoded
    assert TrashCursor.decode(encoded) == cursor
    display, normalized = normalize_name("  Cafe\u0301  ")
    assert display == "Café"
    assert normalized == "café"
    assert markdown_digest("hello") != markdown_digest("hello ")


def test_knowledge_openapi_has_stable_operations_and_storage_routes() -> None:
    paths = create_app().openapi()["paths"]
    assert (
        paths["/api/v1/folders/{folder_id}/contents"]["get"]["operationId"] == "listFolderContents"
    )
    assert (
        paths["/api/v1/folders/{folder_id}/notes"]["post"]["operationId"] == "createKnowledgeNote"
    )
    assert (
        paths["/api/v1/workspaces/{workspace_id}/knowledge-capabilities"]["get"]["operationId"]
        == "getKnowledgeCapabilities"
    )
    tag_path = paths["/api/v1/workspaces/{workspace_id}/tags/{tag_id}"]
    assert tag_path["delete"]["operationId"] == "deleteKnowledgeTag"
    assert (
        paths["/api/v1/workspaces/{workspace_id}/tags/{tag_id}/merge"]["post"]["operationId"]
        == "mergeKnowledgeTag"
    )
    assert (
        paths["/api/v1/folders/{folder_id}/files/upload-ticket"]["post"]["operationId"]
        == "createFileUploadTicket"
    )
    assert (
        paths["/api/v1/documents/{document_id}/file/download"]["get"]["operationId"]
        == "getFileDownload"
    )
    assert (
        paths["/api/v1/documents/{document_id}/file/preview"]["get"]["operationId"]
        == "getFilePreview"
    )
    assert (
        paths["/api/v1/documents/{document_id}/file-versions/upload-ticket"]["post"]["operationId"]
        == "createFileReplacementUploadTicket"
    )
    assert (
        paths["/api/v1/documents/{document_id}/file-versions"]["get"]["operationId"]
        == "listFileVersions"
    )
    version = paths["/api/v1/documents/{document_id}/file-versions"]["get"]["responses"]["200"]
    assert "checksum" not in str(version)
    assert "sizeBytes" not in str(version)
    assert "mimeType" not in str(version)
