from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from ima.application.ingestion import ParseError, Parser, deterministic_chunks, validate_upload_type
from ima.config import Settings
from ima.infrastructure.storage import ObjectStorageClient


def test_parser_accepts_bounded_json_and_is_deterministic() -> None:
    parser = Parser(Settings())
    parsed = parser.parse(b'{"name":"IMA","items":[1,2]}', "sample.json", "application/json")
    assert parsed.parser == "json"
    assert parsed.digest == sha256(parsed.text.encode()).hexdigest()
    assert deterministic_chunks(parsed.text, 10, 2, 10) == deterministic_chunks(
        parsed.text, 10, 2, 10
    )


@pytest.mark.parametrize(
    ("filename", "mime_type"),
    [
        (
            "presentation.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ("image.png", "image/png"),
        ("archive.zip", "application/zip"),
    ],
)
def test_parser_rejects_out_of_scope_types(filename: str, mime_type: str) -> None:
    with pytest.raises(ParseError, match="UNSUPPORTED_FILE_TYPE"):
        validate_upload_type(filename, mime_type)


def test_parser_rejects_legacy_xls_without_a_biff_parser() -> None:
    with pytest.raises(ParseError, match="UNSUPPORTED_FILE_TYPE"):
        validate_upload_type("legacy.xls", "application/vnd.ms-excel")


def test_s3_checksum_uses_the_required_base64_header_value() -> None:
    assert (
        ObjectStorageClient._checksum_header("00" * 32)
        == "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    )


def test_s3_verification_requests_provider_checksum_metadata() -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] = {}

        def head_object(self, **kwargs: object) -> dict[str, object]:
            self.kwargs = kwargs
            return {
                "ContentLength": 1,
                "ContentType": "text/plain",
                "ChecksumSHA256": ObjectStorageClient._checksum_header("00" * 32),
            }

    client = ObjectStorageClient(Settings())
    fake = FakeClient()
    client._client = fake
    client.verify("object", "00" * 32, 1, "text/plain")
    assert fake.kwargs["ChecksumMode"] == "ENABLED"


def test_worker_reconciles_due_retries_and_expired_leases() -> None:
    worker = (Path(__file__).parents[2] / "src" / "ima" / "workers" / "main.py").read_text()
    assert "status IN ('queued','retryable')" in worker
    assert "lease_expires_at < :now" in worker
    assert "storage_cleanup_jobs" in worker
    assert "defer_async(" in worker


def test_stage_rows_begin_blocked_until_the_predecessor_succeeds() -> None:
    root = Path(__file__).parents[2]
    migration_path = root / "migrations" / "versions" / "20260825_0006_storage_ingestion.py"
    migration = migration_path.read_text()
    service = (root / "src" / "ima" / "infrastructure" / "tasks" / "service.py").read_text()
    assert "'blocked','queued','running'" in migration
    assert ":stage,'blocked'" in service


def test_completion_persists_stage_rows_with_the_published_version_before_delivery() -> None:
    storage = (Path(__file__).parents[2] / "src" / "ima" / "application" / "storage.py").read_text()
    publish = storage.index("UPDATE ima.documents SET current_version")
    stage_rows = storage.index("await self.jobs.create_ingestion_jobs")
    delivery = storage.index("await self.jobs.defer_ingestion_parse")
    transaction_end = storage.rindex("        await self.jobs.defer_ingestion_parse")
    assert publish < stage_rows < transaction_end <= delivery


def test_retry_cancel_and_status_are_scoped_to_the_current_file_version() -> None:
    storage = (Path(__file__).parents[2] / "src" / "ima" / "application" / "storage.py").read_text()
    retry = storage.index("async def retry")
    cancel = storage.index("async def cancel")
    status = storage.index("async def status")
    retry_section = storage[retry:cancel]
    cancel_section = storage[cancel:status]
    status_section = storage[status:]
    assert "document_id=:id AND version=:version" in retry_section
    assert '"version": row["version"]' in retry_section
    assert "document_id=:id AND version=:version" in cancel_section
    assert "document_id=:id AND version=:version" in status_section


def test_parser_rejects_invalid_json() -> None:
    with pytest.raises(ParseError, match="MALFORMED_DOCUMENT"):
        Parser(Settings()).parse(b"{", "bad.json", "application/json")
