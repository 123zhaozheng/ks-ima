# Object Storage and Durable Ingestion Implementation Plan

## 1. Evidence and preflight

- [ ] Refresh code graph/research after the knowledge-tree commit; inventory every legacy S3, blob, parse, chunk, embedding, preview, upload, download, MCP, search, and cleanup caller.
- [ ] Add owned fixtures for supported formats, malformed/oversized inputs, archive bombs, bad checksums, duplicate content, missing objects, cross-workspace rows, version replacement, retry/restart/cancel, model dimension mismatch, and retention dependencies.
- [ ] Pin upload, parser, ingestion-stage, role/action, error, capability, and deletion matrices in tests before implementation.

## 2. Storage schema and configuration

- [ ] Add validated Python S3 settings, object-size/timeouts, retention, parser limits, and deployment wiring for API/worker only.
- [ ] Add additive Alembic schema for immutable file-version object bindings, derived text, chunks/vectors, ingestion jobs, and cleanup jobs.
- [ ] Add restrictive composite FKs/checks/indexes, immutable triggers, finite-vector/dimension constraints, lease/idempotency uniqueness, and downgrade refusal for populated data.
- [ ] Add import-safety, fresh/repeat migration, transaction rollback, orphan/dependency/delete guard, and cleanup tests.

## 3. Object storage application boundary

- [ ] Implement one guarded S3-compatible client with private endpoint policy, bounded streaming, checksum/hash verification, opaque key generation, presigned ticket/download/preview URLs, and no secret/URL logging.
- [ ] Implement authorized upload-ticket creation, direct-upload completion verification, safe file metadata, dedupe/reference policy, and stable Problem Details.
- [ ] Implement file-version creation/replacement, download, sanitized preview, and capability projection through `WorkspaceService` policy methods.
- [ ] Extend folder/document listing/detail and lifecycle invalidation so storage/object dependencies remain version-safe across rename, move, trash, restore, and permanent delete.

## 4. Parser and durable ingestion

- [ ] Implement bounded parser adapters for text/Markdown/JSON/PDF/DOCX/XLSX/XLS; reject unsupported/OCR-required/PPTX/image/audio/video and unsafe inputs explicitly.
- [ ] Implement deterministic derived-text and chunk generation with source/version/generation digests and safe location metadata.
- [ ] Register Procrastinate parse/chunk/embed/cleanup tasks on a named queue with lease recovery, idempotency, bounded retries/backoff, dead-letter state, cancellation boundaries, and worker health.
- [ ] Resolve embeddings only through Python model governance; validate finite vectors/dimensions, preserve parsed text on embedding failure, and honor `REINDEX_REQUIRED`.
- [ ] Add status/progress/retry/cancel APIs and audit safe stage/result metadata.

## 5. Generated API and Vue workflow

- [ ] Add explicit operation IDs/DTOs for capabilities, ticket/complete, file/download/preview, ingestion status/retry/cancel, and version/generation history.
- [ ] Export OpenAPI and regenerate TypeScript; extend the shared client/composable only, with cancellation, polling/invalidation, conflicts, and optimistic rollback.
- [ ] Enable upload controls from server capabilities; implement progress, abort, retry, unsupported/error/processing states, preview/download, and workspace-switch cleanup.
- [ ] Remove target-owned browser calls to legacy S3/Bun endpoints while retaining named compatibility consumers for unmigrated data.

## 6. Legacy migration and coexistence

- [ ] Extend `migrate-legacy-knowledge` plan/apply/verify/report for explicitly verified blob copy, checksum/object mapping, parse/index state, fingerprints, and review failures.
- [ ] Add exact Caddy routes and coexistence tests; assert target failure never invokes legacy mutation and internal storage/worker routes are not public.
- [ ] Produce retained-symbol/deletion manifest for legacy S3, blob, parser, chunks, embedding, preview, MCP, search, and cleanup owners.

## 7. Required validation

```text
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest -m postgres
uv run python scripts/export_openapi.py --check

cd ..
bun run generate:api
bun run lint
vue-tsc --noEmit
bun test
bun run test:unit
bun run build:front
bun run build:admin
bun run build:server
bun run test:e2e

docker compose -f docker-compose.example.yml config
```

Additional gates: S3-compatible integration fixture, parser safety suite, worker restart/idempotency/progress suite, model-governance embedding suite, migration equivalence/repeat/failure recovery, residue scan, desktop/mobile browser upload/preview/retry journeys, and cleanup of test buckets, database projects, ports, queues, and Playwright artifacts.

## 8. Rollback points

- Before schema writes: preserve migration/object metadata snapshots and legacy artifacts.
- Before API route cutover: target storage remains unavailable; old browser/Bun routes remain unchanged.
- During coexistence: target-owned documents have one Python writer; rollback switches artifact/routes without reverse-writing target versions into legacy rows.
- Before cleanup: require source equivalence, checksum verification, dependency closure, retention expiry, and successful worker drain.
