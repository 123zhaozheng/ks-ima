# Object Storage and Durable Ingestion

## Goal

Make Python the sole authority for private file bytes, immutable file-version objects, parsing, chunk generation, embedding jobs, and user-visible ingestion state. Users can upload authorized files, monitor and retry ingestion, download or preview supported content, and receive safe failure states without a second mutable Bun/Zero file pipeline.

## Background

- The knowledge-tree task created Python-owned `ima.documents` and immutable `ima.document_versions`, but file bytes and ingestion remain unavailable behind `STORAGE_MIGRATION_PENDING`.
- Legacy Bun code owns S3 configuration, upload/download, blob deduplication, parsing, chunks, embeddings, and in-process polling. Those paths remain read-only compatibility inputs until explicit cutover.
- Python already owns workspace policy, audit, model governance, PostgreSQL migrations, and Procrastinate workers. The new slice must reuse those boundaries.
- Existing legacy parser evidence supports text, Markdown, JSON, PDF, DOCX, XLSX/XLS, and PPTX. The MVP deliberately supports only text, Markdown, JSON, PDF, DOCX, and XLSX/XLS; PPTX, OCR, images, audio, and video remain deferred.

## Requirements

### R1. Private object storage

- Add Python-owned S3-compatible configuration with explicit endpoint, region, bucket, credentials, object-size, timeout, and retention settings.
- Uploads use authenticated workspace/document authorization, bounded streaming, checksum calculation, content-length enforcement, MIME/extension validation, and an opaque object key bound to one immutable document version.
- Support presigned upload and authenticated completion/verification, presigned download with safe attachment metadata, and supported preview access. URLs are short-lived and never appear in logs, audit, browser storage, or error details.
- A checksum mismatch, incomplete upload, unsupported type, oversized object, or cross-workspace request fails atomically with typed Problem Details.
- Deduplication is explicit and version-safe: equal verified content may reuse a target object reference, but no version may point at an object not proven to exist and match its checksum.

### R2. File versions and lifecycle

- Extend the Python schema with immutable file-version object metadata: object key, checksum, byte size, MIME, upload state, source metadata, parser generation, and safe timestamps.
- Replacing or reparsing a file creates a new version/generation; prior versions remain immutable and readable only through authorized history/rollback rules.
- Trash, restore, permanent deletion, and folder ACL changes remain governed by the knowledge service. Object deletion is dependency-aware and deferred/retryable when jobs, versions, rollback retention, or later chunk/citation owners still reference the object.
- Legacy `public.blob`, `item`, and `entity` rows remain read-only migration inputs during coexistence. No dual-write and no target-to-legacy reverse write are allowed.

### R3. Durable ingestion jobs

- Persist parse, chunk, embedding, and cleanup state separately from Procrastinate delivery state, with stable document-version/generation identity, idempotency key, stage, progress, attempts, cancellation request, retry eligibility, safe error code, and timestamps.
- Use the existing PostgreSQL-backed Procrastinate worker boundary. API requests enqueue durable work and never create detached tasks or rely on in-memory queues.
- Jobs are restart-safe, claim-safe across workers, idempotent on repeat delivery, retryable with bounded backoff, cancellable at stage boundaries, and terminally failed/dead-lettered after policy limits.
- Expose safe status/progress/retry/cancel operations to authorized users. Status never reveals object keys, raw parser exceptions, source bytes, or hidden document names.

### R4. Safe parsing and derived text

- Parse only text, Markdown, JSON, PDF text, DOCX text, and XLSX/XLS tabular content in the MVP.
- Enforce parser-specific limits: total bytes, decompression/archive entries and ratio, PDF pages/text/time, DOCX/XLSX resource usage, extracted text bytes, and chunk count. Reject malformed, encrypted, unsupported, scanned/OCR-required, or unsafe inputs with stable states rather than guessing.
- Store normalized extracted text as a version-bound derived artifact, not as file Markdown in `document_versions`. Preserve parser name/version, source checksum, text digest, warnings, and bounded page/sheet location metadata.
- Preview is sanitized and bounded. Raw download remains a separate permissioned operation. Unsupported preview returns a capability/error state without fake success.

### R5. Chunking and embeddings

- Generate deterministic chunks from one immutable parsed-text generation using bounded size/overlap and stable ordinal/location metadata.
- Resolve embedding through Python model governance using the exact assigned published profile/model/gateway. Bun must not decrypt credentials or call an upstream embedding URL.
- Persist model identity, dimension, content digest, generation, and vector only after finite-value and dimension validation. A changed embedding dependency returns `REINDEX_REQUIRED` and never reports fake completion.
- A failed or unavailable embedding path preserves parsed text and exposes keyword-only/embedding-unavailable state without losing the source version.

### R6. APIs and Vue workflow

- Add versioned generated APIs for upload capability, upload ticket/complete, file metadata, download, preview, ingestion status, retry, cancel, and authorized version/generation history.
- Extend the shared session/CSRF transport and Problem Details decoder; do not add component-local HTTP clients or handwritten duplicate DTOs.
- Enable upload only when the server advertises storage capability. Show progress, abort, retry, parsing/indexing stages, unsupported/error states, preview/download availability, and access-revoked/not-found behavior on desktop and mobile.
- Switch workspace/document queries and local progress state on workspace changes; failed optimistic transitions roll back and stale generation/version conflicts require authoritative refresh.

### R7. Migration and coexistence

- Extend `ima migrate-legacy-knowledge plan|apply|verify|report` or add a named storage migration mode that copies only explicitly verified legacy objects, preserves source fingerprints and IDs/mappings, and records checksum/object/parse/index outcomes.
- Missing, changed, ambiguous, cross-workspace, inaccessible, or unsupported legacy blobs enter review/failed checkpoints. The process never reads/logs bytes unnecessarily, invents content, or silently drops a source.
- Caddy routes exact Python byte/job families while legacy S3/Bun routes remain available only for unmigrated objects during the rollback window. Target failure must not fall back to a legacy mutation for a migrated document.

### R8. Security and operations

- Enforce ACL before metadata, ticket, byte, preview, status, retry, cancel, tag, search-derived, and error serialization. Unauthorized resources behave as nonexistent.
- Keep secrets, presigned URLs, object keys, raw parser errors, extracted content from hidden resources, and byte material out of logs/audit/Problem Details.
- Add worker health/readiness, queue isolation, metrics-safe progress, orphan-object cleanup, retryable delete, and retention controls. API startup never migrates schema or starts background work.

## Acceptance Criteria

- [ ] AC1: An authorized editor can create/upload a supported file, complete checksum verification, see durable upload/parse/index progress, and access authorized preview/download; a viewer can only perform operations allowed by policy.
- [ ] AC2: Upload size, MIME, checksum, malformed archive/PDF, unsupported/OCR-required, timeout, cancellation, retry, and worker restart cases produce bounded deterministic states with no fake success or partial metadata.
- [ ] AC3: File versions and object references are immutable, generation-scoped, checksum-bound, dependency-aware, and preserved across rename, move, trash, restore, reparse, and reindex.
- [ ] AC4: Parsing supports only the declared MVP formats with explicit resource limits; derived text and chunks carry source/version/generation digests and safe location metadata.
- [ ] AC5: Embeddings use the Python model-governance assignment and guarded gateway, validate finite values/dimensions, honor `REINDEX_REQUIRED`, and never use a Bun/provider fallback when a target assignment exists.
- [ ] AC6: Generated OpenAPI/client, Vue Query, Caddy, desktop/mobile UI, progress/retry/cancel/preview/download flows remain synchronized and pass contract, unit, build, and browser tests.
- [ ] AC7: Legacy storage migration is resumable/idempotent, preserves fingerprints and valid mappings, reports every failure/review case, and does not dual-write or expose bytes across workspaces.
- [ ] AC8: PostgreSQL fresh/repeat migrations, durable queue/retry/restart, ACL hiding, cleanup/retention, OpenAPI drift, deployment wiring, and residue/coexistence gates pass with required PostgreSQL/browser suites reporting zero skips in CI.

## Out of Scope

- OCR or image understanding, scanned-PDF extraction, audio/video transcription, PPTX parsing, arbitrary binary text inference, public links, cross-workspace sharing, and external Agent upload/delete tools.
- Multipart/resumable uploads unless the agreed object-size limit proves a single bounded request insufficient.
- Search ranking, grounded Ask, citations UX, conversation persistence, and final Zero/Bun deletion; this task only emits versioned derived text/chunks/embeddings for the search child.
- Reverse-writing target versions into legacy Page/PagePatch/blob/chunk rows and long-term legacy object deletion before the cutover child proves rollback safety.

## Technical Notes and Decisions

- Recommended MVP formats: text, Markdown, JSON, PDF, DOCX, XLSX/XLS.
- PostgreSQL remains transactional source of truth; S3-compatible storage holds private bytes; Procrastinate delivers durable work; model governance owns all embedding network calls.
- Source bytes, derived text, chunks, and vectors are separate versioned resources. No arbitrary JSON `conf` state becomes authoritative.
- The detailed design, ordered implementation plan, research evidence, and context manifests are stored beside this PRD.
