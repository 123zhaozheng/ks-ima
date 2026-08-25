# Knowledge Tree And Vue API Migration Design

## 1. Authority And Slice Boundary

Python becomes the sole mutable authority for folders, document identities,
Markdown versions, tags, and trash. The Vue application reads and mutates those
domains through generated `/api/v1` contracts and TanStack Vue Query. Zero and
generic entity JSON are migration inputs only after cutover.

```text
Vue/Quasar
  -> generated knowledge client + shared session/CSRF transport
  -> /api/v1/workspaces|folders|documents|tags|trash
  -> KnowledgeService + existing WorkspaceService policy boundary
  -> ima.folders + documents + versions + tags + audit

Legacy public.entity/item/page/pagePatch/conf.tags
  -> migrate-legacy-knowledge plan/apply/verify/report
  -> disabled read-only rollback source
```

This child deliberately does not own file bytes. Existing file metadata is
migrated and can be listed, moved, tagged, trashed, restored, and audited. The
server advertises upload/download/preview as unavailable with
`STORAGE_MIGRATION_PENDING`. The Vue upload entry consumes that state and cannot
reach Bun/S3. The next child adds real storage before any intermediate release.

## 2. Module Boundaries And Reuse

```text
backend/migrations/versions/20260825_0005_knowledge_tree.py
backend/src/ima/domain/knowledge.py
backend/src/ima/application/knowledge.py
backend/src/ima/application/legacy_knowledge.py
backend/src/ima/api/v1/knowledge.py
backend/src/ima/api/v1/knowledge_contracts.py
```

`KnowledgeService` owns documents, versions, tags, unified content listing, and
document lifecycle. It receives the existing `WorkspaceService` and uses narrow
public policy methods for membership/action checks, visible folder filtering,
folder lookup, and safe audit. It does not copy ACL SQL, role logic, closure
updates, or session handling.

Existing folder endpoints remain authoritative. Folder lifecycle operations are
extended transactionally to account for document dependencies and effective
lifecycle. A document under a trashed ancestor is effectively trashed without
rewriting every descendant document; restoring the ancestor makes it visible
again. Direct document trash records its original folder.

API adapters own FastAPI dependencies, CSRF/recent-auth requirements, Pydantic
contracts, and Problem Details mapping. Domain/application code does not import
FastAPI, Vue types, Zero schemas, or S3 clients.

## 3. Data Model

The additive Alembic migration extends `ima` without modifying legacy `public`
tables.

- `folders.children_version`: monotonic listing revision incremented whenever a
  direct child folder/document is created, renamed in a way that changes order,
  reordered, moved in/out, trashed, restored, or deleted.
- `documents`: stable ID, workspace ID, folder ID, kind (`file|note`), title,
  normalized title, lifecycle (`active|trashed`), original folder ID, row
  version, current content version, file state (`pending|ready|failed`), safe
  file metadata, created/updated actor and timestamps.
- `document_versions`: document ID + semantic version, kind, immutable Markdown
  content for notes, optional legacy file metadata/checksum reference, safe
  source metadata, created actor/time, and canonical digest. Update/delete of an
  existing version is rejected by a PostgreSQL trigger.
- `tags`: workspace-scoped stable ID, display name, NFKC/casefold normalized
  name, lifecycle, optimistic version, created/updated metadata, and unique
  active normalized name.
- `document_tags`: workspace/document/tag composite identity with restrictive
  FKs and assigned actor/time.
- `legacy_knowledge_migration`: source kind/ID, fingerprint, target kind/ID,
  status, attempt, stable reason, timestamps, and mapping metadata without
  document content.

Documents use restrictive workspace/folder composite FKs. Active title
uniqueness is enforced per folder + document kind + normalized title. Folder
and document names may coincide because they are different product kinds;
duplicate active notes or files of the same kind may not.

Permanent deletion checks current/future restrictive dependencies before
removing document tags, immutable versions, and the stable document in one
transaction. Later blob/chunk/job/citation tables reference document/version
restrictively, so this operation naturally becomes unavailable until those
owners clean up through their application services.

## 4. Pagination And Concurrency

Folder-only tree expansion continues to use the existing folder list contract.
The current-folder content API returns a discriminated union of `folder`,
`file`, and `note` rows ordered by `orderKey`, normalized display name, and ID.

The opaque base64url cursor contains a versioned structured payload:

```json
{"v":1,"parentId":"...","childrenVersion":7,"orderKey":10,"name":"...","id":"..."}
```

The server decodes this with a typed parser. If `childrenVersion` differs from
the current parent, it returns `409 LISTING_CHANGED`; Vue clears accumulated
pages and refetches from the beginning. This avoids duplicate/omitted rows when
rename, reorder, move, trash, or restore happens between page requests.

Every mutation takes `expectedVersion`. Batch requests carry each target ID and
expected version plus an idempotency key for destructive retry. The service
locks all rows in deterministic ID order, validates visibility/action/version
for every target, then commits once. A hidden target returns the same 404 as a
missing target; a visible stale target returns `VERSION_CONFLICT`.

## 5. Markdown Notes

Create note inserts the stable document and version 1 atomically. Editing sends
the expected document row version, expected current content version, and whole
Markdown body. Success creates the next immutable version and advances the
document pointers. Restore creates another new version copied from historical
content; it never changes the old row.

The editor uses a bounded plain Markdown source surface plus sanitized preview:
split source/preview on wide screens and a segmented source/preview mode on
mobile. Autosave is debounced and abortable; manual save is always available.
A 409 keeps the local draft, shows current server version metadata, and offers
reload, compare, or explicit retry against the latest version. There is no
automatic merge, TipTap, CRDT, or PagePatch runtime.

## 6. Tags

Tag normalization is owned by one Python domain helper: trim, Unicode NFKC,
casefold for uniqueness, preserve the latest administrator-approved display
form, and enforce length/character bounds. The database stores both display and
normalized values.

Vocabulary mutations require `workspace_admin` or `knowledge_manager`.
Editors may assign existing tags only when `edit` is effective for the target
document. Viewers receive only tags attached to visible documents. Counts are
computed over the policy-filtered document relation. Merge locks source/target,
rewrites relations idempotently, and disables the source tag.

## 7. Trash And Effective Lifecycle

Direct document trash changes its lifecycle, records the original folder, and
increments both document and parent listing revisions. Folder trash continues
to use the existing closure transaction; all descendant documents become
effectively unavailable because an active ancestor chain is required on reads.

The unified trash endpoint returns only top-level directly trashed folders and
documents visible to the actor, ordered by trash time + ID with a stale-aware
cursor. Restore uses the recorded parent when active/authorized; otherwise the
caller supplies an active authorized destination. Name and version conflicts
are typed and leave the row trashed.

Permanent deletion requires active `workspace_admin` membership and the
canonical delete action; platform roles do not count. Folder delete refuses any
remaining descendant folders/documents. Document delete refuses restrictive
dependencies. Every successful or refused destructive action is audited with
safe IDs/counts only.

## 8. API Contracts

```text
GET  /api/v1/workspaces/{workspaceId}/knowledge-capabilities
GET  /api/v1/folders/{folderId}/contents?cursor=&limit=&kind=&tagId=
POST /api/v1/folders/{folderId}/notes

GET   /api/v1/documents/{documentId}
PATCH /api/v1/documents/{documentId}
POST  /api/v1/documents/{documentId}/move
POST  /api/v1/documents/{documentId}/trash
POST  /api/v1/documents/{documentId}/restore
DELETE /api/v1/documents/{documentId}
GET   /api/v1/documents/{documentId}/versions
GET   /api/v1/documents/{documentId}/versions/{version}
POST  /api/v1/documents/{documentId}/versions/{version}/restore
POST  /api/v1/documents/batch/move|trash|restore|tags

GET/POST/PATCH/DELETE /api/v1/workspaces/{workspaceId}/tags/*
POST /api/v1/workspaces/{workspaceId}/tags/{tagId}/merge
PUT  /api/v1/documents/{documentId}/tags
GET  /api/v1/workspaces/{workspaceId}/trash
```

Capability response exposes only business availability:

```json
{
  "upload":{"status":"unavailable","reason":"STORAGE_MIGRATION_PENDING"},
  "download":{"status":"unavailable","reason":"STORAGE_MIGRATION_PENDING"},
  "preview":{"status":"unavailable","reason":"STORAGE_MIGRATION_PENDING"}
}
```

Read routes require an active session and effective workspace/folder action.
Mutations require exact Origin/CSRF; permanent delete and tag vocabulary changes
also require recent authentication. OpenAPI operation IDs are stable and the
generated TypeScript client is the DTO authority.

## 9. Migration And Coexistence

`ima migrate-legacy-knowledge plan|apply|verify|report` uses the existing
checkpoint style and commits per source record or atomic hierarchy unit.

1. Inventory knowledge entity types, roots, trash relationships, payload rows,
   tags, PagePatch histories, collisions, cycles, dangling parents, and file
   metadata/checksums without reading object bytes.
2. Map valid legacy folders to existing target folders by preserved ID and
   verify closure/ACL equivalence; do not recreate Python-owned folders.
3. Import items as file documents with immutable metadata version and
   `fileState=pending`.
4. Import Pages/current text as note documents/version 1. Supported plain patch
   history may become later immutable versions; unsupported history records a
   warning while preserving verified current text. Patch-only unresolved rows
   require review.
5. Normalize/import tags and assignments only for imported visible knowledge
   documents; malformed values are reported, not guessed.
6. Map trash/original parent and verify role/ACL projections, counts, digests,
   IDs, versions, and source fingerprints. Repeat apply must be a no-op.

Cutover deploys the Python API and new SPA artifact together, then blocks the
migrated Zero knowledge mutations. A target error does not fall back to Zero.
Rollback before final freeze restores the previous SPA/API artifact and legacy
writes; it does not reverse-write target note versions into legacy PagePatch.

`kb/ops.ts` is split by concern. Folder/note/tag browser authority leaves this
child. File storage helpers, ingestion/retrieval, and TypeScript MCP consumers
remain named compatibility code owned by later children. Whole-file deletion is
forbidden while those consumers exist.

## 10. Vue Query And UX

One knowledge client/composable layer owns query keys, cursor decoding errors,
Problem Details, cancellation, optimistic rollback, and invalidation. Suggested
keys are workspace + resource + parent/filter/version; components do not parse
raw response fields or maintain a second entity database.

- `FolderTree`: lazy folder-only expansion, roving focus, arrows, Enter/Space,
  accessible context actions, touch fallback, and hidden-node non-disclosure.
- `KnowledgeList`: virtual/paginated mixed content, stable multi-select,
  keyboard ranges, drag/drop and menu move, rename, tags, trash, retry/conflict.
- `NoteEditor`: source/preview, history, local-draft recovery, conflict compare.
- `WorkspaceTags`: vocabulary management and safe visible counts.
- `TrashList`: mixed resources, pagination, restore destination, permanent delete.

The upload command remains visible but disabled from the capability response;
it has no URL, handler, or legacy fallback. Workspace switch cancels old queries
and clears selection/local drafts scoped to the previous workspace.

## 11. Security, Audit, And Errors

All SQL filtering occurs before serialization. Audit/log/error metadata excludes
Markdown, filenames for hidden resources, tag-document pairs for hidden content,
patch bodies, cursor payloads, and database/upstream exception strings.

Stable errors include `DOCUMENT_NOT_FOUND`, `FOLDER_NOT_FOUND`,
`VERSION_CONFLICT`, `LISTING_CHANGED`, `NAME_CONFLICT`, `FOLDER_CYCLE`,
`RESTORE_DESTINATION_REQUIRED`, `DEPENDENCY_EXISTS`,
`STORAGE_MIGRATION_PENDING`, and generic safe validation/authorization errors.

## 12. Validation And Rollback Gate

PostgreSQL tests cover additive/repeat migration, constraints, immutable versions,
listing revisions, concurrency, closure/effective lifecycle, ACL hiding, tags,
trash, dependencies, checkpoints, and cleanup. Component/browser tests exercise
real rendered tree/list/note/tag/trash journeys at desktop and mobile widths.

Before cutover, export source counts/fingerprints, snapshot PostgreSQL and the
legacy SPA/Bun artifact, run equivalence fixtures, and prove the old artifact can
be restored. Do not release the new artifact until the following storage child
makes upload/download/preview available and repeats the cross-slice gate.
