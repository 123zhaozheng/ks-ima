# Knowledge Tree And Vue API Migration Implementation

## 1. Preflight And Executable Fixtures

- Refresh CodeGraph and turn both research reports into an owned caller/deletion
  checklist. Confirm every generic entity/Zero/Bun/MCP/storage/search consumer.
- Add representative legacy fixtures: deep folders, 101 siblings, mixed roles/
  ACL inheritance, files, Pages/current text, PagePatch histories, JSON tags,
  trash, duplicate/case names, cycles, dangling/cross-workspace rows, malformed
  payloads, and pending parse/blob metadata.
- Pin role/action/error matrices and update the exact forced-PostgreSQL and
  Playwright collection gates before product implementation.

## 2. Schema And Shared Policy Boundary

- Add `20260825_0005_knowledge_tree` with folder listing revision, documents,
  immutable versions/trigger, tags, document tags, and migration checkpoints.
- Add restrictive composite FKs, checks, partial uniqueness, cursor indexes,
  deletion guards, and a populated-data downgrade refusal.
- Expose narrow reusable authorization methods from `WorkspaceService`; inject
  it into `KnowledgeService`. Do not copy membership, ACL, closure, or audit SQL.
- Test fresh/repeat Alembic, constraints, immutable updates, Unicode tag/title
  normalization, transaction rollback, and import safety.

## 3. Knowledge Domain And APIs

- Implement typed domain contracts, cursor codec, listing revision rules,
  capability availability, and safe Problem Details.
- Implement policy-filtered mixed folder contents and stable stale-aware cursor
  pagination. Extend folder mutations to increment affected listing revisions.
- Implement document get/rename/move/batch operations with deterministic locks,
  optimistic versions, inherited folder policy, and safe audit.
- Implement Markdown note create/edit/history/version detail/restore with bounded
  content, canonical digest, sanitized rendering contract, and concurrency tests.
- Implement tag vocabulary/merge/delete/list/count and document assignment with
  role/action enforcement and ACL-first aggregation.
- Implement unified trash/list/restore/permanent delete and effective lifecycle
  under trashed folders. Refuse non-empty/dependent deletes.
- Export OpenAPI and add contract tests for operation IDs, DTO privacy, stable
  errors, and absence of upload/download/preview production endpoints.

## 4. Legacy Knowledge Migration

- Implement `ima migrate-legacy-knowledge plan|apply|verify|report` using
  fingerprints, checkpoints, per-record transactions, repeat safety, and safe
  summaries.
- Import/verify folders against existing Python target rows, file metadata as
  pending documents, Page current text/version history where provable, tags,
  relations, trash/original parents, and preserved IDs.
- Report cycles, cross-workspace/dangling parents, collisions, malformed tags,
  payload gaps, unsupported PagePatch histories, and changed fingerprints. Never
  invent content, flatten failures, or read/log file bytes.
- Run interrupted/repeated apply, concurrent apply, verify mismatch, and content-
  residue tests on a clean owned PostgreSQL project.

## 5. Generated Client And Vue Query Boundary

- Regenerate checked OpenAPI JSON and TypeScript client; extend the single shared
  session/CSRF transport and Problem Details decoder without duplicate DTOs.
- Add one knowledge query/composable layer for keys, pagination, cancellation,
  conflicts, optimistic rollback, and authoritative invalidation.
- Migrate workspace switching and route guards away from Zero knowledge preloads.
  Cancel/clear workspace-scoped queries, selections, and drafts on switch.
- Migrate `FolderTree`, breadcrumbs, mixed knowledge list, rename/reorder/move,
  multi-select, batch actions, tags, and trash to generated APIs.
- Implement accessible keyboard/touch behavior, mobile layout, empty/loading/
  retry/offline/not-found/conflict/access-revoked/archived states.
- Implement Markdown source/preview editor, history, autosave cancellation,
  unsaved conflict recovery, and sanitized render tests.
- Render file metadata and server capability state. Keep upload/download/preview
  disabled with `STORAGE_MIGRATION_PENDING`; no legacy or fake handler exists.

## 6. Cutover And Evidence-Driven Deletion

- Split mixed `kb/ops.ts` ownership. Remove folder/note/tag browser/API writers
  from Bun while retaining explicit storage/ingestion/search/MCP consumers.
- Delete migrated Zero knowledge queries/mutators/preloads/stores and obsolete
  generic entity/Page/PagePatch components only after caller searches and builds
  prove no browser consumer.
- Remove migrated entity types from frontend unions/routes/menus instead of
  hiding controls. Keep legacy tables/relations read-only for rollback/migration.
- Add Caddy/coexistence tests for exact Python knowledge route families and
  target-failure no-fallback behavior. Do not broaden all `/api/*` prematurely.
- Produce a retained-symbol manifest with later child owner and deletion gate.

## 7. Focused And Cross-Layer Validation

Backend:

```text
cd backend
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest
uv run python scripts/export_openapi.py --check
```

Frontend/Bun:

```text
cd ..
bun run generate:api
bun run lint
bunx vue-tsc --noEmit
bun test src src-server src-shared
bun run test:unit
bun run build:front
bun run build:admin
bun run build:server
bun run test:e2e
```

- Run Quasar builds sequentially; they share `.quasar` state and memory.
- Execute the research validation matrix: deep tree, 101 siblings,
  `LISTING_CHANGED`, rename/move/reorder conflict, cycles, ACL 404, concurrent
  notes, history restore, Unicode tags, mixed trash, dependency delete, migration
  repeat/failure recovery, and desktop/mobile keyboard/touch journeys.
- Scan source, generated output, build output, browser storage, logs, audit, and
  reports for content leaks, Zero knowledge writes, generic casts, Page/TipTap/
  CRDT remnants, file-byte handlers, fake success, TODO/placeholders, and skips.
- Clean owned Docker projects, volumes, ports, Playwright results, and temp files.

## 8. Full Review, Specs, And Commit Gate

- Trace note create -> policy -> document/version transaction -> generated DTO ->
  Vue Query -> editor -> conflict/history/restore and folder move -> listing
  revision -> cache reset. Trace denied rows through list/tag/trash/error paths.
- Run `trellis-check` full-scope and fix every verified finding with regression
  tests. Re-run all affected gates after the last fix.
- Add executable backend/frontend knowledge-tree specs with signatures, schemas,
  cursor/version rules, authorization matrices, error cases, tests, and wrong vs
  correct examples.
- Commit implementation and specs separately, archive this child, record the
  journal, then immediately plan/start the storage/ingestion child before any
  intermediate application release.

## 9. Rollback Point

- Preserve source counts/fingerprints, PostgreSQL/object metadata snapshot,
  legacy frontend/Bun artifact, and mapping/equivalence report.
- Before final write freeze, rollback deploys the old artifact and re-enables
  legacy knowledge writes. Never reverse-write target Markdown versions into
  PagePatch or dual-write a request.
- After the new SPA cutover, legacy knowledge rows remain read-only until the
  storage child proves file-byte continuity and the final migration task closes
  the rollback window.
