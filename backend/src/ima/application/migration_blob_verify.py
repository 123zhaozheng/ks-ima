"""Report model for HEAD verification of migrated object versions.

The CLI performs the HEAD checks through ``ObjectStorageClient``; this module
keeps the report shape and exit-code decision pure and unit testable.
"""

from __future__ import annotations

from dataclasses import dataclass

VERIFIED = "verified"
MISSING = "missing"
CORRUPT = "corrupt"


@dataclass(frozen=True, slots=True)
class BlobVerifyRecord:
    document_id: str
    version: int
    object_key: str
    status: str
    detail: str


def build_blob_verify_report(
    *,
    records: list[BlobVerifyRecord],
    orphan_keys: tuple[str, ...] | list[str],
    legacy_blob_rows: int,
    storage_configured: bool = True,
) -> dict[str, object]:
    verified = [record for record in records if record.status == VERIFIED]
    missing = [record for record in records if record.status == MISSING]
    corrupt = [record for record in records if record.status == CORRUPT]
    orphans = sorted(str(key) for key in orphan_keys)
    ok = bool(
        storage_configured
        and len(verified) == len(records)
        and not missing
        and not corrupt
        and not orphans
    )
    return {
        "storageConfigured": storage_configured,
        "checked": len(records),
        "verified": len(verified),
        "missing": [_record_payload(record) for record in missing],
        "corrupt": [_record_payload(record) for record in corrupt],
        "orphans": orphans,
        "legacyBlobRows": int(legacy_blob_rows),
        "migratedVersions": len(records),
        "ok": ok,
        "secretValues": False,
    }


def _record_payload(record: BlobVerifyRecord) -> dict[str, object]:
    return {
        "documentId": record.document_id,
        "version": record.version,
        "objectKey": record.object_key,
        "detail": record.detail,
    }
