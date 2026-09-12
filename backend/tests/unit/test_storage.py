from __future__ import annotations

from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest

from ima.application.knowledge import KnowledgeError
from ima.application.storage import StorageService
from ima.config import Settings
from ima.infrastructure.storage import ObjectStorageClient, StorageClientError


class FakeClient:
    def __init__(self) -> None:
        self.head_arguments: dict[str, object] | None = None
        self.copy_arguments: dict[str, object] | None = None

    def head_object(self, **kwargs: object) -> dict[str, object]:
        self.head_arguments = kwargs
        return {
            "ContentLength": 3,
            "ChecksumSHA256": ObjectStorageClient._checksum_header(
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
            ),
            "ContentType": "text/plain",
        }

    def get_object(self, **kwargs: object) -> dict[str, object]:
        return {"Body": BytesIO(b"abc")}

    def copy_object(self, **kwargs: object) -> dict[str, object]:
        self.copy_arguments = kwargs
        return {}


def storage() -> ObjectStorageClient:
    value = ObjectStorageClient(
        Settings(
            storage_endpoint="http://storage.test",
            storage_bucket="files",
            storage_access_key_id="key",
            storage_secret_access_key="secret",
        )
    )
    value._client = FakeClient()
    return value


def test_malformed_ticket_returns_typed_failure() -> None:
    service = StorageService.__new__(StorageService)
    service.settings = Settings(token_pepper="ticket-test")
    with pytest.raises(KnowledgeError) as exc_info:
        service._verify_ticket("%%%", uuid4())
    assert exc_info.value.code == "INVALID_UPLOAD_TICKET"

    storage_service = (
        Path(__file__).parents[2] / "src" / "ima" / "application" / "storage.py"
    ).read_text()
    upload = storage_service.index("async def upload_ticket")
    replacement = storage_service.index("async def replacement_ticket")
    complete = storage_service.index("async def complete")
    upload_section = storage_service[upload:replacement]
    replacement_section = storage_service[replacement:complete]
    assert upload_section.index("self.client.presigned_put") < upload_section.index(
        "INSERT INTO ima.documents"
    )
    assert replacement_section.index("self.client.presigned_put") < replacement_section.index(
        "INSERT INTO ima.document_file_versions"
    )

    client = storage()
    client.verify(
        "key", "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", 3, "text/plain"
    )
    assert client._client.head_arguments == {
        "Bucket": "files",
        "Key": "key",
        "ChecksumMode": "ENABLED",
    }


def test_verify_rejects_mismatched_object_checksum() -> None:
    with pytest.raises(StorageClientError, match="OBJECT_VERIFICATION_FAILED"):
        storage().verify("key", "00" * 32, 3, "text/plain")


def test_copy_verified_uses_server_side_copy_and_rechecks_target() -> None:
    client = storage()
    client.copy_verified(
        "legacy",
        "target",
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
        3,
        "text/plain",
    )
    assert client._client.copy_arguments == {
        "Bucket": "files",
        "Key": "target",
        "CopySource": {"Bucket": "files", "Key": "legacy"},
        "ContentType": "text/plain",
        "MetadataDirective": "REPLACE",
        "ChecksumAlgorithm": "SHA256",
    }
    assert client._client.head_arguments == {
        "Bucket": "files",
        "Key": "target",
        "ChecksumMode": "ENABLED",
    }


from ima.application.storage import _previewable_inline


def test_inline_preview_whitelist_covers_browser_native_formats() -> None:
    for mime in ('text/plain', 'text/markdown', 'application/json', 'application/pdf', 'image/png', 'image/jpeg', 'image/webp'):
        assert _previewable_inline(mime), mime


def test_inline_preview_rejects_office_and_unknown_formats() -> None:
    for mime in ('application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.openxmlformats-officedocument.presentationml.presentation', 'application/zip', None, ''):
        assert not _previewable_inline(mime), mime
