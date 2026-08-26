# Current storage and ingestion evidence

Research-only snapshot after knowledge-tree migration. Anchors are repository-relative and include symbols or line ranges observed on 2026-08-25. No product code was changed.

## Executive boundary

- Python now owns the knowledge tree, document lifecycle, ACL checks, metadata, and note versioning. `backend/src/ima/application/knowledge.py:100-240,290-450,680-770` and `backend/src/ima/api/v1/knowledge.py:35-190` expose/list/get/mutate notes, files-as-metadata, trash, and immutable note versions.
- File bytes and ingestion are not yet Python-owned. `KnowledgeService.capabilities` returns all three capabilities as `{"status":"unavailable","reason":"STORAGE_MIGRATION_PENDING"}` (`backend/src/ima/application/knowledge.py:100-107`); OpenAPI has no `/upload`, `/download`, or `/preview` path (`backend/tests/unit/test_knowledge.py:26-47`).
- MVP should migrate only **text, Markdown, JSON, PDF, DOCX, XLSX** for upload, durable parse, preview/download, chunks, and embeddings. Do not add OCR, audio, video, or PPTX to the first Python contract: image/audio/video return no parsed text in `src-server/kb/parse-file.ts:88-101`; PPTX exists only as a legacy parser branch (`:54-68`) and has no Python/browser-cutover evidence. Preserve legacy PPTX behavior until a separately verified parser/security decision.

## Legacy S3/object paths

- S3 configuration is Bun-only environment state: `src-server/utils/config.ts:1-10` (`S3_ENDPOINT`, bucket, access key, secret, region). Deployment supplies it only to `server` (`docker-compose.example.yml:20-38`), not `ima-api` or `ima-worker`.
- `src-server/utils/s3.ts:3-65` builds path-style or virtual-host S3 URLs, signs query presigned GETs, streams authenticated GET/PUT/DELETE, and sends `content-length` plus optional metadata. No multipart/resume/retention policy is present.
- Browser legacy upload endpoint is `src-server/s3.ts:40-150`, `PUT /api/s3/items/:id`: session/member authorization; SHA-256 and SHA-256-proof headers; dedupe by `(sha256, sha256Proof, refCount>=1)`; streams request body to S3 while hashing a tee; verifies S3 checksum and proof; inserts `blob`; attaches `item.blobId`; invokes `enqueueParse`. Download is authenticated presigned GET at `GET /api/s3/items/:id` and `GET .../url` (`:12-38,130-150`), with 30-minute expiry and attachment disposition.
- Legacy MCP file upload is bounded to 8 MiB (`src-server/kb/ops.ts:300-348`; route validation in `src-server/kb.ts:210-228`, tool contract in `src-server/mcp-dispatch.ts:69-79`). It buffers base64/text, hashes, dedupes only live blobs, writes S3 and `blob`, then queues parsing.
- Legacy deletion is ref-count driven: SQL trigger adjusts blob `refCount` and storage totals (`drizzle/20260317054607_create_trigger/migration.sql:1-36`); hourly cron deletes all `refCount=0` objects from S3 and then rows (`src-server/jobs/clean-blobs.ts:1-16`, scheduled `src-server/jobs/index.ts:15-24`). This has no grace period, tombstone, failed-delete queue, or document-version awareness.
- Object keys are currently opaque blob IDs. New Python storage must not reuse a legacy key without an explicit coexistence/read policy; otherwise old rows and new `ima.documents.storage_key` can collide semantically even though physical keys differ.

## Target metadata/schema and callers

- Knowledge migration `backend/migrations/versions/20260825_0005_knowledge_tree.py:15-127` creates `ima.documents` with `kind`, lifecycle/version, `file_state` (`pending|ready|failed`), MIME, size, checksum, and `storage_key`; `document_versions` is immutable by trigger (`:42-66`) and currently allows Markdown only for notes (`CHECK(kind='note' OR markdown IS NULL)`). Files get no content/chunk/version-byte relation yet.
- `backend/src/ima/domain/knowledge.py:103-111` projects only `mimeType`, `sizeBytes`, `checksum`, and `fileState`; `backend/src/ima/application/knowledge.py:210-240` returns no file URL, parsed text, parser error, content version, or ingestion progress for files.
- The legacy schema is separate: `src-server/schema/schema.ts:232-278` has `item.text`, `item.blobId`, `item.mimeType`, `blob.sha256`, `sha256Proof`, `size`, `refCount`, and `chunk(entityId, ordinal, text, page, embedding)`. `blob` has no workspace/document FK; `item` points to legacy `entity` and is Zero-facing.
- Legacy coexistence is intentional and tested: `backend/tests/contract/test_knowledge_coexistence.py:32-60` requires `src-server/kb/ops.ts`, `kb.ts`, `kb/ingest.ts`, `s3.ts`, MCP, and retained imports to remain. The archived boundary says deletion waits for storage/ingestion/search/MCP cutovers (`.trellis/tasks/archive/2026-08/08-24-knowledge-tree-vue-api/research/retained-legacy-symbols.md:1-35`).
- Legacy migration is conservative and does not select blob bytes: `backend/src/ima/cli.py:493-575`; it maps file metadata to `documents` and a metadata-only version (`:790-840`) while malformed hierarchy, tags, unsupported page patches, source changes, and collisions become review/checkpoint states. It does not establish a verified object copy or chunk/embedding mapping.

## Parsing, safety, and MVP format support

- Legacy parser `src-server/kb/parse-file.ts:8-101` supports raw text-like data, Markdown, JSON fallback decoding, DOCX via Mammoth, XLSX/XLS via `xlsx-republish`, PDF text via `pdfjs-dist`, and PPTX XML extraction. Images/video/audio deliberately return `undefined`; PDF extraction loops over every page with no page/byte/time limit; DOCX/XLSX/PPTX decompression/parser limits are not explicit.
- Text note limit is 1,000,000 UTF-8 bytes (`backend/src/ima/application/knowledge.py:240-250,315-328`; contract max is characters in `backend/src/ima/api/v1/knowledge_contracts.py:42-54`). Backend global request body limit is configurable 25 MiB default and max 512 MiB (`backend/src/ima/config.py:27-31,160-168`), but no S3 object-size setting exists.
- Browser cache limits are 8 MiB per object and 128 MiB total (`src/utils/config.ts:1-4`, `src/utils/blob-cache.ts:90-121`), while legacy product copy says 5 GiB and MCP says 8 MiB (`i18n/zh-CN.json:540-552`; `src-server/kb/ops.ts:310-314`). Treat these as incompatible limits to reconcile before exposing a Python upload contract.
- Recommended Python parser safety envelope for MVP: enforce request/object max before persistence; bounded streaming/hash; MIME plus extension allowlist; decompression ratio and archive-entry/worksheet/page/text limits; PDF page count/text bytes/time limit; DOCX/XLSX resource limits; reject unsupported/OCR-required files as explicit `unparsed`/`unsupported`, never attempt generic binary-to-text decoding for arbitrary binary.

## Chunks, embeddings, scheduling, and governance boundary

- Legacy ingest `src-server/kb/ingest.ts:20-75` fetches S3, parses, writes `item.text/language`, deletes and recreates all chunks, then calls `safeEmbedTexts`; parse status is stored in `entity.conf.parseStatus` (`queued|parsing|ready|failed|unparsed`). A parse failure is caught and persisted, but indexing is not transactional with text/status.
- Chunking is 400-800-ish configurable text with default target 600/overlap 80 (`src-server/kb/chunk-text.ts:1-6`; `ingest.ts:27-40`). Legacy chunk schema has ordinal/page and nullable JSON embedding but no model ID/dimension/version/content digest/index job ID (`src-server/schema/schema.ts:249-264`).
- Scheduling is process-memory and polling, not durable: `enqueueParse` uses an `inflight` `Set` plus `setTimeout(...,200)` (`ingest.ts:76-84`); `parseQueuedItems` polls 20 queued entities and 30 unindexed text rows every 15 seconds (`:105-137`, `src-server/jobs/index.ts:15-24`). Restart loses in-flight work and concurrent instances can claim the same row.
- Python Procrastinate conventions are established: shared PostgreSQL app/connector in `backend/src/ima/infrastructure/tasks/app.py:1-17`; tasks use `@app.task(name=..., queue=..., retry=3, pass_context=True)` (`.../diagnostic.py:12-60`, `.../model_health.py:14-40`); worker registers tasks and runs explicit queues with heartbeat (`backend/src/ima/workers/main.py:32-55`); API defers work through the task object, not detached tasks (`backend/src/ima/infrastructure/tasks/service.py:67-105`). A new ingestion queue should follow this pattern and use a stable idempotency key/content version.
- Model governance owns embedding execution in Python. `backend/src/ima/application/model_governance.py:2090-2110` resolves exact `Workflow.EMBEDDING` assignment and calls the guarded gateway; target denial is terminal and legacy fallback is allowed only for verified absence of an assignment per `.trellis/spec/backend/model-governance-contracts.md:50-67`. Bun’s current `src-server/kb/embed.ts:1-38` calls Bun resolver/legacy adapters and must not remain authoritative after Python ingestion cutover.
- Governance already tracks embedding model dimensions and dependencies: model create/validation requires dimension (`backend/src/ima/application/model_governance.py:570-610,1084-1105`); dependency/dimension changes return `REINDEX_REQUIRED` (`:1580-1610,2175-2218`). New chunk/index records must retain model ID, dimension, content/version digest, and job/index state so this contract can be enforced.

## Current Vue upload/file preview/progress workflows

- Knowledge browser upload is explicitly disabled: `src/views/DirView.vue:25-42` marks “Upload files” and “Upload folder” disabled with “File storage migration is pending”; empty state repeats the message (`:80-83`). E2E asserts upload remains disabled (`tests/e2e/knowledge-tree.pw.ts:23-27,146-150`).
- Generic legacy upload service uses XHR progress, abort signal, speed/ETA, SHA-256 headers, precheck/dedupe, and a task-progress wrapper (`src/services/upload.ts:8-108`). It uploads by item ID, not Python document UUID, and calls `/api/s3/items/:id` through `getItemUrl`.
- Legacy blob cache downloads an authenticated presigned URL, verifies SHA-256, caches IndexedDB blobs up to 8/128 MiB, and returns URL or bytes (`src/utils/blob-cache.ts:59-130`). This is reusable UX behavior but must be pointed at Python capability/document endpoints and preserve authorization/expiry/hash verification.
- Legacy item preview supports PDF/DOCX/XLSX using Vue Office and downloads bytes via the cache (`src/components/FilePreview.vue:1-60`). `ItemView.vue:260-280` also advertises image, video, audio, Markdown, and text previews; these are legacy item behavior, not the Python MVP commitment. Python target should implement safe previews for text/Markdown and PDF/DOCX/XLSX, with binary download as a separate permissioned operation.
- `src/views/ItemView.vue:303-348` still downloads/reparses through legacy URLs and Bun `/api/kb/reparse`; it is not the migrated `KnowledgeDocumentPage.vue` workflow. `src/pages/KnowledgeDocumentPage.vue:125-176` currently covers note fetch/edit/history only.

## Migration, coexistence, deletion, and retention blockers

1. No Python object client/config/deployment wiring or upload/download/preview endpoints; `ima-api` and `ima-worker` lack S3 settings (`docker-compose.example.yml:44-82`).
2. `ima.documents.storage_key` exists but is not populated/served; no immutable file-version object relation exists, so replacing a file cannot safely preserve source bytes/history.
3. Legacy rows/blobs are not workspace-scoped at blob level and old cleanup deletes unreferenced blobs immediately; migration needs a reference/copy/verification policy before old deletion.
4. Legacy parse/chunk/embedding rows are owned by Zero/Bun callers; Python must not dual-write or treat `entity.conf.parseStatus` as authoritative during coexistence.
5. No durable parse/embedding progress schema or cancel/retry state exists in Python; Procrastinate queue state alone is insufficient for user-visible stage/progress and version-safe idempotency.
6. No parser resource limits, OCR policy, quarantine, or malicious archive/PDF test suite exists.
7. Model governance requires exact embedding assignment/dimension and blocks unsafe fallback; ingestion must resolve/embed through Python rather than importing Bun credentials or calling providers directly.
8. Knowledge API generated client has no byte routes and Caddy only routes workspace/document metadata (`Caddyfile:20-30,70-80`); route additions require generated OpenAPI and Caddy/coexistence tests.
9. Permanent delete currently requires trash and rejects dependent rows (`backend/src/ima/application/knowledge.py:744-770`); retention must define whether source objects/versions/chunks/jobs are deleted synchronously, deferred, or retained for audit/recovery. Folder/workspace cascades and legacy cleanup need separate inventory.
10. `legacy_knowledge_migration` checkpoints support per-source retry/review but do not prove blob copy, checksum, or parser equivalence (`backend/migrations/...0005...:82-91`, `backend/src/ima/cli.py:692-900`).

## Deletion and retention inventory

| Resource | Current owner | Current deletion behavior | MVP recommendation/blocker |
|---|---|---|---|
| Legacy S3 blob object | Bun `src-server/utils/s3.ts` | Hourly delete when `blob.refCount=0` | Freeze/delete only after verified reference inventory and grace-period cleanup; never infer from Python document lifecycle alone |
| Legacy `public.blob` row | Bun/Drizzle | Deleted after successful S3 delete | Retain until copy/checksum and all legacy readers are retired |
| Legacy `item`/`entity` metadata | Zero/Bun | Entity cascade/legacy lifecycle | Read-only during coexistence; map source IDs/fingerprints to checkpoint |
| Python `ima.documents` | Python | Trash then admin-only permanent delete; FK restrict on dependencies | Delete metadata only when source/version/jobs/chunks/object cleanup policy confirms no references |
| Python `document_versions` | Python | Immutable; document FK restrict; deleted with document only | Retain immutable source/version metadata; file versions need object key/checksum/content digest |
| Python object bytes | Not implemented | None | Add explicit object state, version binding, checksum, pending/orphan cleanup and retention grace period |
| Parse/embedding jobs | Not implemented; legacy polling | Legacy in-memory queue disappears on restart | Durable job rows + Procrastinate delivery, retry/dead-letter/lease recovery, cancel semantics, idempotency |
| Legacy chunks/embeddings | Bun `chunk` | Entity cascade; reindex deletes/recreates chunks | Preserve old index for rollback; delete only after target retrieval/citation parity and model dependency migration |
| Python chunks/embeddings | Not implemented | None | Version-scoped records with model/dimension/digest and dependency index; no cross-version overwrite |
| Browser IndexedDB cache | Vue `blob-cache` | LRU-like trim at 128 MiB; no server retention effect | Keep client eviction independent; verify each download hash and avoid caching unauthorized URLs |
| Migration checkpoints | Python `legacy_knowledge_migration` | Explicit status/retry/review | Retain audit/review evidence through rollout; source fingerprint changes must halt, not overwrite |

## Recommended MVP boundaries

- **In scope:** private authenticated upload/download; checksum/hash verification; dedupe with immutable version binding; text/Markdown/JSON direct parsing; PDF text extraction; DOCX text extraction; XLSX/XLS tabular-to-Markdown extraction if XLS compatibility is intentionally retained; safe preview/download; durable parse and embedding jobs; status/progress/retry; workspace ACL before metadata/bytes; Python model-governance embedding execution; migration copy/verify for explicitly mapped legacy files.
- **Out of scope:** OCR/scanned-PDF image understanding, image interpretation, audio/video transcription, PPTX parsing/preview, generic arbitrary binary indexing, multipart/resumable upload unless required by an agreed object-size limit. These may remain legacy-only or report unsupported during coexistence.
- **MVP parser output:** a version-bound normalized text artifact plus parser metadata/error. Keep source bytes immutable and do not put extracted text into `document_versions.markdown` for files, because the schema currently forbids file Markdown and source/version identity must remain distinct.
- **MVP indexing:** chunks are derived from one immutable document version; replacing/reparsing creates a new generation and never mutates prior generation. Embedding call is Python governance only; no embedding vector persistence if dimension/model validation fails.

## Executable validation matrix

| Area | Command/test | Expected proof |
|---|---|---|
| Python static/unit | `cd backend; uv run ruff check src tests; uv run mypy; uv run pytest -q` | New storage/parser/job contracts type/lint clean; invalid MIME/size/checksum/archive cases typed |
| Python migration | `cd backend; uv run pytest -q tests/integration/test_postgres_knowledge.py -m postgres` with `IMA_TEST_DATABASE_URL` | Fresh/repeat migration, immutable versions, ACL/trash/dependency behavior remain green |
| Durable worker | `cd backend; uv run pytest -q tests/integration/test_postgres_worker.py -m postgres` | Queue survives API/worker boundary, retry/attempt state and worker heartbeat verified; add restart/idempotency/progress cases |
| Storage integration | New Postgres + S3-compatible fixture test | Private ACL, upload checksum/proof, dedupe, presigned expiry/disposition, download hash, orphan cleanup, no cross-workspace access |
| Parser safety | `cd src-server; bun test kb/parse-file.test.ts` plus Python parser tests | Text/Markdown/JSON/PDF/DOCX/XLSX fixtures; malformed/truncated/oversized/compression-bomb/too-many-pages/unsupported cases bounded and fail safe |
| Governance boundary | `cd backend; uv run pytest -q tests/unit/test_model_governance.py tests/integration/test_postgres_model_governance.py -m postgres` | Embeddings resolve exact assigned model/dimension; target denial terminal; no Bun/provider direct path; `REINDEX_REQUIRED` honored |
| Legacy coexistence | `cd backend; uv run pytest -q tests/contract/test_knowledge_coexistence.py tests/contract/test_coexistence.py` | Legacy symbols stay until explicit cutover; Python knowledge routes do not import Zero/Bun or claim byte ownership early |
| OpenAPI/Caddy | `uv run python backend/scripts/export_openapi.py`; `bun run generate:api`; contract route assertions and Caddy config check | Byte routes, auth/error DTOs, capability states, and proxy paths are synchronized; internal bridge is not browser-exposed |
| Frontend unit/e2e | `bun test`; `bun run test:unit`; `bun run test:e2e` | Upload controls enabled only when capability available; progress/abort/retry, preview/download, stale document/version refresh, mobile/desktop behavior |
| Deployment | `docker compose -f docker-compose.example.yml config` then migration/API/worker/integration services | S3 secrets reach only intended services, worker queue/schema configured, migration gates API/worker startup, health/readiness fails closed |
| Migration verification | `uv run python -m ima.cli migrate-legacy-knowledge report|verify` with legacy fixture | Every copied file has source fingerprint, target UUID/version, object checksum and parse/index state; changed/ambiguous/missing blob becomes review, never guessed |
| Retention/deletion | Integration fixture with active/trashed/version/job/chunk/object combinations | Trash hides content; permanent delete requires admin and no dependencies; deferred object cleanup is retryable and cannot delete bytes still referenced by any version or rollback reader |

## Agent identity

Research agent ID: `grok-build-storage-ingestion-research-20260825`.
