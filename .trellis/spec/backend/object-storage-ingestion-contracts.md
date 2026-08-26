# Object Storage And Durable Ingestion Contracts

## Scope / Trigger

Apply this contract to Python S3-compatible configuration/client code, file-version object bindings, upload/download/preview APIs, parser/chunk/embedding/cleanup tasks, worker reconciliation, legacy blob migration, and any permanent-delete dependency involving file bytes or derived artifacts.

## Signatures

```text
POST /api/v1/folders/{folderId}/files/upload-ticket
POST /api/v1/documents/{documentId}/file-versions/upload-ticket
POST /api/v1/documents/{documentId}/file-versions/complete
GET  /api/v1/documents/{documentId}/file-versions
GET  /api/v1/documents/{documentId}/file/download
GET  /api/v1/documents/{documentId}/file/preview
GET  /api/v1/documents/{documentId}/ingestion
POST /api/v1/documents/{documentId}/ingestion/retry|cancel

ima.document_file_versions
ima.document_derived_text
ima.document_chunks
ima.ingestion_jobs
ima.storage_cleanup_jobs
```

## Contracts

- Python is the only mutable target authority. PostgreSQL owns metadata/state, private S3-compatible storage owns bytes, Procrastinate owns delivery, and model governance owns embedding network calls.
- Upload tickets bind one actor-authorized folder/document, immutable file version, exact SHA-256, size, MIME, opaque key, and expiry. Completion publishes only after provider HEAD with `ChecksumMode=ENABLED` matches checksum, size, and MIME.
- Replacement creates a pending version without changing the current document pointer. Verified completion atomically advances current metadata/version; failed, expired, aborted, or conflicting replacement preserves the prior published version.
- Supported parse formats are text, Markdown, JSON, PDF text, DOCX, and XLSX. Legacy XLS, PPTX, OCR/scanned PDF, image, audio, and video parsing are unsupported until a bounded adapter is specified and tested.
- Parser limits cover object bytes, extracted text, PDF pages, ZIP entry count, uncompressed bytes, and decompression ratio. Unsupported/malformed/limit cases produce stable safe codes, never arbitrary binary decoding or raw parser errors.
- Parse, chunk, embed, and cleanup rows are persisted and idempotent. Dependent stages start blocked and are unblocked only after predecessor success. Worker reconciliation re-delivers queued/retryable rows, expired leases, and due cleanup rows after restart.
- Embeddings execute through the exact Python `Workflow.EMBEDDING` assignment. Persist only finite vectors with the expected dimension/model metadata. Parsed text remains available when embedding fails; target denial never invokes Bun/provider fallback.
- Object cleanup is deferred and retryable. It must not delete bytes referenced by an active file version, ingestion job, rollback-retained legacy source, derived artifact, chunk, or later citation owner.
- Byte/status/history operations authorize before serialization and hide inactive/trashed/unauthorized documents as nonexistent. Object keys, presigned URLs, credentials, raw bytes, extracted hidden content, and raw exceptions never enter logs/audit/Problem Details.
- Legacy migration copies only completed metadata mappings with stable fingerprints. It bounded-streams/verifies the source, performs provider-side copy to an opaque target key, verifies the target, checkpoints repeatably, and never deletes or reverse-writes legacy objects.

## Validation Matrix

| Condition | Required result |
|---|---|
| Wrong/expired ticket, checksum, size, MIME, or missing object | Typed failure; no published version |
| Replacement conflict or failed PUT | Current file version/history unchanged |
| Worker restart, retry time, or expired lease | Reconciler eventually redelivers exactly one idempotent stage |
| Parse malformed/oversized/archive bomb/unsupported | Bounded safe terminal state; no raw exception/content leak |
| Missing/broken embedding assignment or wrong vector dimension | Parsed text preserved; embedding unavailable/failed; no fake ready |
| Trashed/unauthorized file byte/status/history request | Safe 404 |
| Cleanup with any dependency | Retain object and return/defer dependency state |
| Changed/missing legacy blob | Review/failed checkpoint; no guessed copy |
| Provider HEAD omits checksum without checksum mode | Client explicitly requests checksum metadata |

## Tests Required

1. Ruff format/check, strict mypy, full pytest, and deterministic OpenAPI export.
2. Fresh isolated PostgreSQL image with both `vector` and `zhparser`; `IMA_REQUIRE_POSTGRES=1` must collect and pass the exact current PostgreSQL test count with zero skips.
3. Real private MinIO/S3-compatible upload ticket PUT, checksum HEAD, GET, delete, and legacy provider-side copy verification in isolated buckets with cleanup.
4. Worker tests for blocked stage ordering, idempotency, retry/dead-letter, cancellation, expired lease reconciliation, restart behavior, and cleanup dependencies.
5. Parser fixtures for every supported and rejected format plus malformed, compressed, page/text/size limit cases.
6. Model-governance tests for exact embedding assignment, finite/dimension validation, terminal target denial, and `REINDEX_REQUIRED` dependencies.
7. Caddy/OpenAPI/coexistence tests prove exact Python routes and retained legacy ownership until explicit cutover.

## Wrong vs Correct

### Wrong

```text
API completion trusts browser metadata -> marks file ready -> queues in-memory parse
worker calls Bun embedding URL -> cleanup deletes object on parse failure
```

### Correct

```text
API ticket -> direct private S3 PUT with signed checksum
completion -> provider HEAD checksum/size/MIME verification -> atomic published version
PostgreSQL stage rows -> Procrastinate delivery/reconciliation -> bounded parser
Python model governance -> validated vectors -> dependency-aware cleanup
```
