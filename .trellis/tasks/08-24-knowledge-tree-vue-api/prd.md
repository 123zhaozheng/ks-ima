# Knowledge Tree And Vue API Migration

## Goal

Make Python the sole knowledge-tree authority and migrate the reusable Vue
workspace experience from Rocicorp Zero to versioned REST/OpenAPI APIs and Vue
Query. Users must be able to navigate authorized folders, manage files and
Markdown notes, organize content with tags, and use a predictable trash
lifecycle without exposing restricted names or retaining a second mutable tree.

## Background

- Python already owns workspaces, memberships, folder closure, ACL anchors,
  folder lifecycle, optimistic versions, audit events, and fail-closed policy
  filtering in `backend/src/ima/application/authorization.py`.
- The browser still reads and mutates the knowledge tree through generic Zero
  `entity`, `item`, `page`, `pagePatch`, and JSON `conf.tags` contracts in
  `src-shared/queries.ts` and `src-shared/mutators.ts`.
- Legacy trash moves generic entities under a special trash root and has no
  target lifecycle/version contract. Legacy Pages use mutable text plus patch
  rows rather than immutable document versions.
- `src-server/kb/ops.ts` is shared by browser/API/MCP and mixes this slice with
  later object-storage, ingestion, search, and Ask responsibilities. It cannot
  be deleted wholesale until those named consumers migrate.
- The parent migration fixes the target around stable documents, immutable
  versions, Markdown notes, normalized tags, explicit lifecycle, generated API
  clients, and server-side authorization. Durable parsing/vector ingestion and
  grounded search remain later children.

## Requirements

### R1. Stable Knowledge Domain

- Reuse the existing Python-owned `folders`, closure, ACL, lifecycle, and audit
  contracts; do not create a parallel folder or authorization service.
- Add stable `documents` with kinds `file|note`, workspace/folder ownership,
  lifecycle, optimistic version, current immutable document version, safe
  ingestion summary, and created/updated actor metadata.
- Add immutable numbered document versions. Editing or restoring a Markdown
  note creates a new version; published history is never rewritten in place.
- File and note IDs remain stable across rename, move, trash, restore, content
  revision, later reparse, and later reindex operations.
- Names, Markdown, MIME metadata, sizes, tags, and lifecycle values are bounded
  and typed. Arbitrary legacy `entity.conf` JSON is not a target extension bag.
- This child migrates existing file metadata but does not create file-byte
  placeholders. Upload, download, preview, blob verification, and ingestion
  remain unavailable with the typed reason `STORAGE_MIGRATION_PENDING` until
  the immediately following storage/ingestion child completes.

### R2. Folder And Document APIs

- Expose versioned folder tree/list/breadcrumb and document list/detail/create/
  rename/move APIs with deterministic cursor pagination and stable tie-breaking.
- Every mutation uses an expected version. Stale state, sibling-name conflict,
  move cycle, invalid destination, archived workspace, and dependency conflict
  return stable Problem Details without partial writes.
- Batch operations validate all visible targets and permissions atomically; a
  hidden or stale target fails the operation rather than being silently skipped.
- Folder and document moves update effective ACL ownership atomically. A file or
  note always inherits its current folder ACL in the MVP.

### R3. Markdown Notes

- Implement complete Markdown note create, read, edit, autosave/manual-save,
  immutable history, version diff metadata, and restore-to-new-version behavior.
- Concurrent edits fail with a typed conflict and preserve the losing browser's
  unsaved text for recovery; last-write-wins data loss is forbidden.
- Rendered Markdown is sanitized. Trashed or unauthorized notes are not readable
  through content, history, tag, breadcrumb, error, or generated-client paths.
- Page/PagePatch migration converts supported live Markdown/plain-text content,
  records source mappings, and reports unsupported patch histories without
  guessing or silently discarding active content.

### R4. Tags

- Implement workspace-scoped normalized tags and document-tag relations with
  create, rename, merge, delete, list, and single/batch assignment operations.
- Normalize surrounding whitespace and compare names case-insensitively while
  preserving an administrator-visible display form. Active duplicates are
  forbidden.
- Tag discovery and counts are ACL-filtered. Users cannot infer restricted
  documents, folders, names, or counts through tags.
- Workspace administrators and knowledge managers manage the tag vocabulary;
  editors may apply existing tags where they may edit the document; viewers are
  read-only.

### R5. Trash And Permanent Deletion

- Use one lifecycle model for folders, files, and notes. Trash preserves the
  original parent and cascades effective unavailability to descendants.
- Trash listing is permission-filtered and cursor-paginated across resource
  kinds. Restore uses the original parent when valid or requires an authorized
  explicit destination, with typed name/version conflicts.
- Only an active workspace administrator may permanently delete knowledge
  content. Platform roles alone do not grant content deletion or visibility.
- Permanent deletion is dependency-aware, audited, and ordered so later blob,
  chunk, citation, and job owners can refuse or complete cleanup safely. No
  endpoint reports deletion success while owned dependencies remain.

### R6. Authorization And Non-Disclosure

- Reuse the canonical workspace policy actions: metadata/content view,
  download, ask, create child, edit, move, delete, and ACL management.
- Lists, gets, breadcrumbs, tags, trash, versions, batch results, and errors are
  filtered in server SQL. Vue must never fetch all workspace IDs and filter
  hidden resources locally.
- Unauthorized folder/document names, IDs, paths, counts, tags, version
  metadata, and restore destinations behave as nonexistent.
- Platform administrators remain infrastructure authorities only and gain no
  implicit workspace content access.

### R7. Vue Migration

- Replace Zero-backed workspace switching, folder tree/list/breadcrumbs,
  document routing, Markdown notes, tags, and trash with the checked generated
  OpenAPI client, shared session/CSRF transport, and TanStack Vue Query.
- Preserve useful workflows: expandable tree, deterministic pagination,
  rename, drag/drop move, multi-select, batch actions, upload entry, recent
  navigation where still in scope, and desktop/mobile layouts.
- The upload entry is rendered from server capability state and remains disabled
  with `STORAGE_MIGRATION_PENDING`. It never calls the legacy Bun/S3 path and
  never reports success before the storage child owns the operation.
- Provide keyboard and touch alternatives for pointer interactions, stable
  focus/selection, narrow breadcrumb overflow, and mobile action access.
- Cover loading, empty, pagination, retry, offline/network error, stale conflict,
  forbidden/not-found, access revoked, trashed, archived, dependency, and
  partial-transition states. Failed optimistic mutations roll back visibly.
- No component-local HTTP client, handwritten duplicate DTO, Zero materialized
  view, generic entity cast, or mutable `conf` policy state becomes the new
  authority.

### R8. Migration, Coexistence, And Deletion

- Add a resumable, idempotent knowledge migration with per-record source
  fingerprint/checkpoint and safe plan/apply/verify/report modes.
- Preserve workspace/folder/document IDs where valid; map legacy folder,
  `item`, `page`, `pagePatch`, and `conf.tags` rows explicitly. Cycles,
  cross-workspace parents, malformed tags, dangling payloads, unsupported page
  histories, and collisions enter a safe review/failed report without guessing.
- Compare source/target hierarchy, content checksums where available, closure,
  ACL visibility, lifecycle, tags, and representative role results before
  cutover. Legacy rows remain read-only rollback inputs during the window.
- A migrated route has one writer. Target failure must not silently fall back to
  a legacy mutation. Rollback is an explicit route/artifact switch before final
  write cutover, not per-request dual-write.
- Delete migrated Zero queries/mutators/stores and generic entity components only
  after every browser caller moves. Split mixed Bun adapters by ownership;
  retain named storage/ingestion/search/MCP consumers until their child removes
  them. Every retained compatibility symbol has a deletion milestone.

### R9. Audit, Operations, And Quality

- Audit creates, edits, restores, moves, tags, trash, permanent deletes,
  migration events, conflicts, and denied mutations with safe IDs/actions/counts
  only; never store Markdown content, filenames from restricted resources, blob
  material, patch bodies, or raw exception strings in audit/logs.
- Add PostgreSQL concurrency and migration tests, API/OpenAPI contracts, Vue
  component tests, Bun coexistence tests, and full desktop/mobile Playwright
  journeys. Required PostgreSQL/browser tests may not skip.
- Ruff, mypy, pytest, forced PostgreSQL, OpenAPI export/generation/drift, ESLint,
  `vue-tsc`, Bun/Vitest, sequential Quasar builds, residue scans, and isolated
  test cleanup must pass.
- No accepted workflow is complete with a TODO, placeholder, mock-only
  production path, skipped required test, hard-coded success, dual mutable
  authority, or undocumented manual SQL.

## Acceptance Criteria

- [ ] AC1 (`R1`,`R2`): Authorized users can navigate deterministic folder and
      document pages, create folders/notes, rename/move metadata, and receive
      typed optimistic conflicts without duplicate, skipped, or partially
      mutated rows.
- [ ] AC2 (`R3`): Markdown notes work end to end with sanitized rendering,
      immutable history, restore-to-new-version, concurrent-edit recovery, and
      no TipTap/CRDT/Page runtime authority.
- [ ] AC3 (`R4`): Normalized workspace tags support full vocabulary and
      assignment lifecycle with role enforcement and ACL-safe counts/results.
- [ ] AC4 (`R5`): Unified trash, restore, cascade, pagination, conflicts, and
      workspace-admin-only dependency-aware permanent deletion work for folders,
      files, and notes.
- [ ] AC5 (`R6`): Every list/get/version/tag/trash/breadcrumb/error path hides
      unauthorized IDs, names, counts, content, and relationships as nonexistent.
- [ ] AC6 (`R7`): Workspace switching, tree, list, breadcrumbs, notes, tags, and
      trash use generated Python APIs and Vue Query with complete desktop/mobile,
      keyboard/touch, loading/error/conflict/access-revoked behavior.
- [ ] AC6a (`R1`,`R7`): File metadata remains visible and governable, while
      upload/download/preview are consistently unavailable with
      `STORAGE_MIGRATION_PENDING`; no legacy write, dual-write, fake success, or
      broken control is reachable.
- [ ] AC7 (`R8`): Knowledge migration plan/apply/repeat/verify/report is
      resumable and idempotent, preserves valid IDs/content/tags, reports every
      malformed or unsupported row, and never guesses or silently drops data.
- [ ] AC8 (`R8`): Migrated knowledge routes have one Python writer, rollback is
      explicit, and deleted Zero/generic-entity code has no live browser caller;
      retained storage/search/MCP compatibility has a named later owner.
- [ ] AC9 (`R9`): Safe audit and Problem Details cover positive, denied,
      conflict, migration, trash, and dependency cases without content leakage.
- [ ] AC10 (`R9`): Deep-tree, 101-sibling pagination, move cycles, concurrent
      notes, tags, mixed trash, ACL hiding, migration repeat/failure recovery,
      OpenAPI drift, desktop/mobile Playwright, builds, and residue gates pass
      with required PostgreSQL/browser suites reporting zero skips.

## Out Of Scope

- File upload/download tickets, object-store reads/writes, checksums, previews,
  and byte migration. These ship in the immediately following storage/ingestion
  child before any intermediate application release.
- Durable file parsing, chunking, embeddings, pgvector indexes, parser restart/
  retry/cancel, source-range extraction, reparse, and reindex execution; the
  object-storage/durable-ingestion child owns these.
- ACL-first keyword/vector search, reranking, conversations, grounded Ask,
  citations, and search-result UX; the search/Ask child owns these.
- OAuth grants, service principals, and the final Python MCP server. Existing
  MCP knowledge operations remain a named compatibility consumer until that
  child migrates them.
- Rich-text/TipTap/CRDT collaboration, arbitrary entity types or `conf` JSON,
  public publishing, cross-workspace search, conversation-as-knowledge, and
  permanent deletion as an external Agent tool.
