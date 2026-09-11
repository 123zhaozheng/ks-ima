# Object Storage And Durable Ingestion Contracts

## Scope / Trigger

Apply this contract to Python S3-compatible configuration/client code, file-version object bindings, upload/download/preview APIs, parser/chunk/embedding/cleanup tasks, automatic retrieval-index upkeep after embedding, worker reconciliation, legacy blob migration, and any permanent-delete dependency involving file bytes or derived artifacts.

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
- Cancellation reaches a terminal state without a running worker: `queued`/`retryable`/`blocked` stages are set `cancelled` immediately, a `running` stage is set `cancel_requested` and finalized by that task at its next checkpoint, and reconciliation finalizes an orphan `cancel_requested` whose lease is absent or expired. Cancelling with no cancellable stage is a 409 `INGESTION_NOT_CANCELLABLE`.
- A document's `file_state` reflects ingestion terminal state: any terminal `failed`/`dead_letter`/`cancelled` stage sets `file_state='failed'` (cancellation reuses the `failed` terminal value), a successful embed sets `ready`, `ready` is never overwritten by a later terminal write, and retry resets the document to `pending`. Retry restarts from the earliest terminal stage (`parse`, else `chunk`, else `embed`) and reopens only downstream stages; an already succeeded upstream stage is never downgraded, so a failure after parse does not dead-end.
- Embeddings execute through the exact scene-default Python `Workflow.EMBEDDING` model. Persist only finite vectors with the expected dimension/model metadata. Parsed text remains available when embedding fails; target denial never invokes any provider fallback.
- After the embed stage makes a document `ready`, it enqueues an idempotent retrieval-index build for its knowledge base using the scene-default embedding model. Reconciliation also heals a knowledge base that has ready exact-model chunks but no active index. A knowledge base with no scene-default embedding model or no exact-model ready chunks is skipped, never error-looped.
- Ingestion and retrieval share one model resolver: the embed stage resolves its target from the scene-default resolver used for retrieval. No scene default yields `NO_ASSIGNMENT`; a configured but unusable target (`UNAVAILABLE`) fails the stage without a fake success.
- Object cleanup is deferred and retryable. It must not delete bytes referenced by an active file version, ingestion job, rollback-retained legacy source, derived artifact, chunk, or later citation owner.
- Byte/status/history operations authorize against the containing knowledge-base membership before serialization and hide inactive/unauthorized documents as nonexistent (folders and documents are `active`-only; there is no trash lifecycle). Object keys, presigned URLs, credentials, raw bytes, extracted hidden content, and raw exceptions never enter logs/audit/Problem Details.
- Legacy migration copies only completed metadata mappings with stable fingerprints. It bounded-streams/verifies the source, performs provider-side copy to an opaque target key, verifies the target, checkpoints repeatably, and never deletes or reverse-writes legacy objects.

## Validation Matrix

| Condition | Required result |
|---|---|
| Wrong/expired ticket, checksum, size, MIME, or missing object | Typed failure; no published version |
| Replacement conflict or failed PUT | Current file version/history unchanged |
| Worker restart, retry time, or expired lease | Reconciler eventually redelivers exactly one idempotent stage |
| Cancel queued/blocked stage, or orphaned cancel with no active lease | Job reaches `cancelled` without a live worker; document reaches `failed` |
| Terminal parse/chunk/embed failure or cancellation | Document `file_state='failed'`; `ready` is never downgraded |
| Retry after a terminal ingestion | Earliest terminal stage requeued, downstream reopened, document `file_state='pending'` |
| Parse malformed/oversized/archive bomb/unsupported | Bounded safe terminal state; no raw exception/content leak |
| Missing/broken embedding scene default or wrong vector dimension | Parsed text preserved; embedding unavailable/failed; no fake ready |
| Successful embed with exact-model ready chunks | Exact active vector index built automatically; grounded ask needs no manual step |
| Unauthorized or non-member file byte/status/history request | Safe 404 |
| Cleanup with any dependency | Retain object and return/defer dependency state |
| Changed/missing legacy blob | Review/failed checkpoint; no guessed copy |
| Provider HEAD omits checksum without checksum mode | Client explicitly requests checksum metadata |

## Tests Required

1. Ruff format/check, strict mypy, full pytest, and deterministic OpenAPI export.
2. Fresh isolated PostgreSQL image with both `vector` and `zhparser`; `IMA_REQUIRE_POSTGRES=1` must collect and pass the exact current PostgreSQL test count with zero skips.
3. Real private MinIO/S3-compatible upload ticket PUT, checksum HEAD, GET, delete, and legacy provider-side copy verification in isolated buckets with cleanup.
4. Worker tests for blocked stage ordering, idempotency, retry/dead-letter, cancellation, expired lease reconciliation, restart behavior, cleanup dependencies, and automatic/self-healing retrieval-index builds.
5. Parser fixtures for every supported and rejected format plus malformed, compressed, page/text/size limit cases.
6. Model-governance tests for exact scene-default embedding resolution, finite/dimension validation, terminal target denial, and `REINDEX_REQUIRED` dependencies.
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
