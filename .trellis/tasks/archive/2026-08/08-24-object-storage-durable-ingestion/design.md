# Object Storage and Durable Ingestion Design

## 1. Authority and deployment boundary

Python owns target file bytes metadata, upload completion, immutable file-version object bindings, parser/derived-text/chunk/index state, ingestion status, and cleanup decisions. PostgreSQL is the transactional source of truth. S3-compatible storage is private blob storage. One `ima-api` process serves HTTP; one or more `ima-worker` processes consume a named Procrastinate ingestion queue. API startup never runs migrations or starts detached work.

Legacy Bun/Zero storage, `public.blob`, `item`, `entity.conf.parseStatus`, legacy chunks, and Bun model calls remain read-only compatibility inputs during the rollback window. A target-owned document never falls back to a legacy mutation when Python fails.

```text
Vue + generated client
  -> Caddy exact /api/v1/workspaces|documents|ingestion|storage routes
  -> FastAPI adapters + shared CSRF/session/error transport
  -> KnowledgeService + StorageService + IngestionService + WorkspaceService policy
  -> ima.documents/file_versions/object_refs/derived_text/ingestion_jobs/chunks
  -> private S3-compatible object store

Procrastinate delivery -> ingestion worker
  -> parser sandbox/limits -> derived text -> deterministic chunks
  -> Python model-governance embedding execution -> validated vectors
```

## 2. Data model

Add an additive Alembic migration under `ima` with restrictive composite workspace/document/version foreign keys and indexes:

- `document_file_versions`: stable document ID, immutable semantic version/generation, object state (`pending|verified|failed|orphaned`), opaque object key, checksum algorithm/value, size, MIME, original filename metadata, source fingerprint, created actor/time, and verification timestamps. Unique `(document_id, version)` and unique verified `(workspace_id, checksum, size, mime)` only where dedupe policy permits.
- `document_derived_text`: document/version/generation identity, parser name/version, source checksum, normalized text digest, bounded text payload or private derived artifact reference, safe warning/error code, status, and timestamp. Immutable after publication.
- `document_chunks`: document/version/generation, ordinal, bounded text, digest, page/sheet/character location, embedding status, model ID/version, dimension, vector, and timestamps. Restrictive FKs prevent deleting source versions while dependent chunks remain.
- `ingestion_jobs`: stable idempotency key, document/version/generation, stage (`upload|parse|chunk|embed|cleanup`), status (`queued|running|retryable|cancel_requested|cancelled|succeeded|failed|dead_letter`), progress counters, attempt/lease/retry timestamps, safe error code, correlation ID, and actor metadata.
- `storage_cleanup_jobs`: object/version dependency snapshot, retryable deletion state, attempts, next eligibility, safe error code, and timestamps.

Use immutable triggers/checks for published versions and finite vector/dimension validation. Keep object keys and raw errors out of DTOs/audit. Add deletion guards for active jobs, dependent derived artifacts/chunks, rollback retention, and future blob/citation owners.

## 3. Upload, download, and preview contracts

Recommended operations with stable IDs:

```text
GET  /api/v1/workspaces/{workspaceId}/storage-capabilities
POST /api/v1/folders/{folderId}/files/upload-ticket
POST /api/v1/documents/{documentId}/file-versions/complete
GET  /api/v1/documents/{documentId}/file
GET  /api/v1/documents/{documentId}/file/download
GET  /api/v1/documents/{documentId}/file/preview
GET  /api/v1/documents/{documentId}/ingestion
POST /api/v1/documents/{documentId}/ingestion/retry
POST /api/v1/documents/{documentId}/ingestion/cancel
GET  /api/v1/documents/{documentId}/file-versions
GET  /api/v1/documents/{documentId}/file-versions/{version}/ingestion
```

The ticket contains only a short-lived upload URL, opaque ticket ID, target document/version, required checksum/size/MIME, and expiry. The browser sends bytes directly to S3 using the ticket; completion verifies existence, exact size/checksum, content type, and ownership before publishing metadata and enqueuing parse. Download/preview uses a fresh short-lived URL or bounded server stream after policy authorization. Preview returns sanitized text/HTML or a safe unavailable reason; it never returns a legacy URL or raw parser exception.

All mutations require exact Origin/CSRF. Upload completion, retry, cancel, and permanent cleanup require recent auth where defined by the existing policy. Hidden documents return the same safe 404 for metadata, ticket, bytes, preview, status, history, and errors.

## 4. Ingestion state machine

`complete` creates one idempotent generation and durable stage records. The worker claims jobs with lease/attempt checks and uses deterministic `(document_id, version, generation, stage)` keys. Each stage commits its own bounded transaction:

1. **Parse**: stream object through size/hash verification, MIME/extension allowlist, parser-specific limits, and a sandbox boundary. Store normalized derived text and parser metadata. Unsupported/OCR-required becomes a typed terminal `unsupported`; malformed/limit cases become typed `failed`.
2. **Chunk**: deterministic target/overlap settings produce stable ordinal/digest/location rows. A generation’s chunks are never rewritten in place.
3. **Embed**: resolve exact `Workflow.EMBEDDING` profile through Python model governance, call the guarded gateway, validate finite vectors and expected dimension, then persist model/dimension/vector atomically. Missing assignment may expose keyword-only state according to governance; existing broken assignments fail terminally without legacy fallback.
4. **Publish**: update safe document file state/capabilities and progress only after derived artifacts are committed.

Retries use bounded exponential backoff and safe error codes. Cancellation is cooperative at stage boundaries and persisted before acknowledgement. Worker restart reclaims expired leases. A dead-letter job preserves the source/version and exposes retry without duplicate chunks/vectors.

## 5. Parser safety

Implement Python parser adapters with shared byte/text limits and explicit format handlers for text/Markdown/JSON, PDF, DOCX, and XLSX/XLS. Enforce archive entry count/ratio, page/sheet/text limits, parser timeout, memory/size bounds, malformed input handling, and no arbitrary binary fallback. Keep parser version and source digest in every derived artifact. PPTX, OCR, image, audio, video, encrypted documents, and unsupported formats return a safe unsupported state.

## 6. Authorization, audit, and coexistence

`StorageService` receives `WorkspaceService` and reuses its narrow member/action/folder/audit methods; it does not copy ACL SQL. Authorize the target folder/document before any ticket, object metadata, byte, preview, status, retry, cancel, tag, or cleanup operation. Audit only safe document/version IDs, stage, outcome, counts, and error codes.

Legacy migration copies only verified objects with source fingerprint, target mapping, checksum, and outcome checkpoints. It never logs bytes, trusts legacy `conf`, or reverse-writes target data. Legacy readers continue until the explicit cutover task removes them; Caddy routes exact target families and preserves unrelated Bun paths.

## 7. Vue data flow

Extend the single generated client and `use-knowledge` query layer with workspace/document/version/job keys, cancellation, retry and invalidation. Upload flow is ticket -> direct S3 PUT with progress/abort -> completion -> poll/SSE-safe status. Workspace switching cancels old upload/status queries and clears scoped progress. File metadata renders pending/processing/ready/failed/unsupported; download/preview buttons reflect server capabilities and never call legacy URLs.

## 8. Rollback and operations

Before target write cutover capture legacy source counts/fingerprints, object metadata inventory, and old SPA/Bun artifacts. During coexistence target and legacy objects are not dual-written. Rollback switches the route/artifact and keeps target objects/read-only versions; it does not reverse-write into PagePatch/blob. Cleanup is delayed until rollback retention, job completion, chunk/citation dependency checks, and source equivalence are proven. Deployment passes S3 settings only to Python API/worker and keeps secrets out of browser/web containers.

## 9. Contract and failure matrix

- Missing/expired ticket, wrong checksum/size, unsupported MIME, object missing, cross-workspace, or unauthorized target -> safe typed 4xx/404 and no published version.
- Cursor/version/generation mismatch -> `409 VERSION_CONFLICT` or `INGESTION_GENERATION_CHANGED`, no partial state.
- Parse limit/malformed/unsupported -> `failed`/`unsupported` with stable safe code and retryability flag.
- Worker lease loss/restart -> one eventual completion, no duplicate published artifacts.
- Gateway unavailable/invalid vector/wrong dimension -> parsed text preserved, embedding unavailable/retryable or `REINDEX_REQUIRED`, no fake success.
- Cleanup dependency -> `DEPENDENCY_EXISTS`/deferred cleanup, object retained.
- Python unavailable -> no legacy write fallback for target-owned documents.

## 10. Validation

Use focused unit tests for codecs, ticket signing, checksum/limits, parser safety, state transitions, and redaction; PostgreSQL tests for migrations, immutable relationships, leases, retry/cancel/idempotency, ACL hiding, dependency cleanup, and governance dimensions; S3-compatible integration fixtures for private access, checksum, expiry, dedupe, orphan cleanup, and cross-workspace denial; OpenAPI/Caddy drift tests; Vue/Vitest and desktop/mobile Playwright upload/progress/preview/retry journeys; and deployment configuration checks.
