# Research: Backend and CodeGraph Evidence for Knowledge Tree API

- Query: Map the backend/data domain and CodeGraph consumers for folders, files, Markdown notes, tags, trash, versions/conflicts, authorization/audit reuse, legacy Bun/Zero schema/routes/mutators, current Python foundations, and dependencies on later storage/ingestion/search children. Classify symbols and files as retain, replace, migration-input, temporary compatibility, or delete.
- Scope: mixed (internal code, migrations, task/spec artifacts, and CodeGraph SQLite index)
- Date: 2026-08-25

## Findings

### CodeGraph baseline and freshness

The checked-in local CodeGraph database is `.codegraph/codegraph.db`. It contains
407 files, 5,571 nodes, and 14,324 edges (`contains`, `calls`, `imports`,
`references`, `instantiates`, and `extends`). It indexes 39 `src-server`
files; the queried file rows had no `modified_at > indexed_at` entries. The index
has 398 file nodes, 1,266 functions, 281 methods, 1,944 imports, and 3,766 call
edges. There is no `project_metadata` row and there are 20,000+ unresolved
references, mostly ordinary external/built-in calls; therefore the graph is a
consumer hint, not a complete proof of reachability.

CodeGraph symbol evidence:

- `src-server/schema/schema.ts`: `workspace` 19-38, `member` 39-49,
  `entity` 97-119, `page` 187-212, `item` 233-248, `chunk` 250-264,
  `blob` 265-274, `entityAccess` 410-422, `entityPermission` 424-437,
  and `connector` 439-456 are individually indexed constants.
- `src-shared/mutators.ts` is indexed as one 1,162-line file with the relevant
  symbols `createPage` 478-498, `createItem` 520-543, `createFolder` 590-607,
  `updateEntity` 674-688, `moveEntities` 689-712, `recycleEntities` 934-951,
  `restoreEntities` 952-970, `deleteEntities` 971-985, and export `mutators`
  1110-1161.
- `src-shared/queries.ts` indexes `queries` 45-314. It contains the direct
  folder/tree, note, item, search, workspace, and trash readers described below.
- `src-server/zero/routes.ts` indexes the `/mutate` and `/query` handlers at
  26-48; `src-server/zero/mutators.ts` indexes the server wrapper at 20-68.
- Vue consumers include `FolderTree` 1-169, `TrashList` 1-157,
  `src/composables/zero/query.ts` 43-135, and `VueView` in
  `src/composables/zero/view.ts` 24-137. CodeGraph links `createFolder` to
  `src/views/DirView.vue` and links `useQuery` to `entity-conf` and
  `use-system-info`; template-level links are incomplete, so supplement the
  graph with the `rg` consumer list below.

### Legacy data model and invariants

The original Drizzle migration (`drizzle/20260317054550_public_demogoblin/migration.sql`)
defines the public data model. `entity` is the generic tree: `id`, `rootId`,
`parentId`, `type`, `name`, JSON `conf`, `sortPriority`, `hidden`, and `pubRoot`
(lines 35-47). `workspace` stores the root ID and a separate `trashId`
(263-276). `page` is a note payload keyed by entity ID (158-161), `item` is a
file payload with `text`, `language`, `blobId`, and `mimeType` (72-79), and
`blob` stores content-addressed metadata (`sha256`, proof, size, `refCount`)
(13-19). The entity foreign key `(rootId,parentId)` cascades on delete
(migration lines 377-378), and all typed payload tables reference the same
`(rootId,id)` entity identity (for example `item` 384-385 and `page` 398-400).

There is no first-class legacy tag table: tags are stored in `entity.conf.tags`.
There is no legacy document version/conflict table. `pagePatch` (migration
163-169) is a patch log for pages, not an optimistic document version contract;
the generated Zero schema exposes it as a relation but no target-level version
or conflict state. Trash is represented by moving selected entities under the
workspace trash entity and changing `rootId`/`parentId`, not by a lifecycle
column. The generic tree also contains non-knowledge product entities (chat,
assistant, provider, model, search, translation, MCP plugin, shortcut, and
system folders), so a migration must filter by type and preserve IDs.

### Legacy authorization and audit

The old permission migration (`drizzle/20260824004617_entity_permissions/migration.sql`)
creates per-user `entityPermission` rows with `canView`, `canAsk`, `canEdit`,
`canDelete`, and `canManage` (lines 1-21), plus `kb_acl_*` functions/triggers
and a materialized rebuild on entity/member changes (23-225). The TypeScript
policy helper `src-shared/utils/acl.ts:3-104` uses actions `view`, `ask`,
`edit`, `delete`, `manage`, nearest non-inherited JSON ACL, and the invariant
that `ask` also requires `view` (lines 60-104). `src-shared/table-permission.ts:6-48`
uses `withReadable` against the `permission` relation and broad writable roles.
`src-server/utils/permissions.ts:99-163` adds connector folder scope and a
temporary Python authorization bridge; it maps legacy actions to target actions
at 165-174 and fail-closes malformed/partial/timeout bridge responses at
192-220.

The Python authorization target is already the reusable authority for folder
membership/ACL decisions. `backend/src/ima/application/authorization.py:47-78`
centralizes service mutation and `_audit`; `_require_member` at 95-120
fail-closes inactive account/membership/workspace. Folder reads and mutations
use set-based closure/policy queries (`folders` 1050-1075, `breadcrumbs`
1077-1100, `create_folder` 1102-1183). Rename and move use row locks and
expected versions (`rename_folder` 1213-1287, `move_folder` 1289 onward).
Trash/restore/delete are explicit lifecycle operations, and ACL replacement
validates subject/action dependencies and updates anchors/versions atomically
(the ACL replacement block around 1840-1946). `_audit` stores actor/action/result,
safe reason, IDs, and counts but excludes names/content (`53-78`). Reuse this
service/policy/audit boundary; do not reimplement authorization in a new content
router.

The target schema is folder-only at present. `backend/migrations/versions/20260825_0003_workspace_authorization.py:53-90`
creates `ima.folders`, `folder_closure`, `folder_acls`, and `folder_acl_entries`
with `lifecycle`, `version`, `original_parent_id`, `acl_anchor_id`, and
workspace-scoped constraints. It does not create documents, file versions,
Markdown payloads, tags, blobs, or ingestion rows. `backend/src/ima/api/v1/workspaces.py:323-602`
exposes versioned folder/breadcrumb/move/reorder/trash/restore/delete/ACL APIs;
`backend/src/ima/api/app.py:155-170` mounts them below `/api/v1` while keeping
the private bridge excluded from public OpenAPI/Caddy. `Caddyfile:25-28`
currently routes `/api/v1/workspaces*` and invitations to Python; generic
`/api/*` still goes to Bun (`43-46`).

### Legacy API and mutation surface

`src-server/zero/routes.ts:26-48` is the generic Zero transport. It obtains a
Better Auth session (`15-22`), dispatches arbitrary registered shared mutators,
and evaluates arbitrary shared queries. `src-server/zero/mutators.ts:7-68`
wraps only selected entity mutations with legacy/bridge authorization; it
rejects JSON ACL mutation (`41-50`) because Python is now the mutable ACL
authority, but delegates the rest to `src-shared/mutators.ts`.

The shared mutators are the main replacement target. Knowledge-relevant
operations are:

- `createFolder` inserts a generic `entity` of type `folder`, inherits the
  parent's `rootId`/`pubRoot`, and uses `sortPriority=10` (590-607).
- `createPage` creates an entity of type `page` and an empty `page` row
  (478-498); `createPagePatch` appends a patch row with `userId` (499-512).
- `createItem` creates a type `item`, initializes `conf.parseStatus='queued'`,
  and stores optional MIME/text/language (513-543).
- `updateEntity` changes generic name/hidden/order/avatar (674-688),
  `updateEntityConf` merges arbitrary JSON keys (415-428), and
  `moveEntities` rewrites tree roots/parents and recursively updates `pubRoot`
  (689-737). The latter only checks cycles on the server and has no optimistic
  version contract.
- `recycleEntities` moves selected entities to `workspace.trashId` and changes
  their root/parent (934-951); `restoreEntities` moves direct trash children
  back to a caller-selected folder (952-970); `deleteEntities` permanently
  deletes trash children (971-985). There is no dependent-content check or
  immutable deletion audit in this path.

`src-server/kb/ops.ts` is a mixed compatibility/application layer. Read
operations list/tree entities and expose `conf.tags`/`conf.parseStatus`
(`83-145`), read notes from `page` (`147-158`), and read files from `item` plus
presigned S3 URLs (`160-184`). It also enumerates visible tags from JSON conf
(`186-197`). Writes delegate to Zero mutators (`kbMkdir` 199-211,
`kbCreateNote`/`kbUpdateNote` 213-237, `kbSetTags` 240-249, `kbMove` 251-265,
`kbDelete` 267-280). These should become Python content application services
and versioned REST contracts; preserve IDs and tag values during migration.

`src-server/kb.ts` exposes unversioned `/api/kb/*`: search/ask (40-69), tree,
note/file reads (103-135), create/update note, mkdir, set-tags, move, delete
(137-209), and base64 upload (210-227). `src-server/index.ts:1-24` mounts
`/kb`, `/zero`, `/s3`, and `/mcp`. `src-server/mcp.ts:5-20,30-89` imports
every `kb/ops` operation and exposes the same folder/note/file/tag/delete
surface to API-key clients. Thus deleting `kb/ops.ts` or Zero before the Python
content API and MCP/storage cutovers breaks both browser and agent workflows.

### Files, ingestion, search, and later-child dependencies

The current file path is split across three concerns:

1. Metadata mutation creates an `item` entity through Zero (`kbUploadFile`
   `src-server/kb/ops.ts:300-323`).
2. Blob storage uses S3 and content-addressed `blob` rows, either through the
   direct MCP base64 helper (`325-347`) or browser resumable/checksum upload in
   `src-server/s3.ts:40-109` and `src/utils/knowledge-upload.ts:91-105`.
3. `src-server/kb/ingest.ts:12-137` tracks parse state in `entity.conf`, reads
   S3, parses bytes, chunks text, optionally embeds, and writes `chunk` rows;
   it uses an in-process `Set`/timer (`76-84`) and workspace reindex loop
   (`86-103`). `src-server/kb/retrieve.ts:130-200` filters visible IDs, folder,
   tags, and ACL before FTS/vector retrieval and reranking.

The later `object-storage-durable-ingestion` child must own blob/upload tickets,
immutable document versions, parser jobs/state, chunks, and durable retries;
the later search/RAG child must own FTS/pgvector retrieval, stable citations,
reranking, and Ask. This child should define content identity/version and API
contracts that those children consume, but must not duplicate their storage or
retrieval implementations. The existing `chunk`, `embedding`, and `parseStatus`
fields are migration inputs only.

### Vue/Zero consumer map

The direct Zero consumer scan found the following knowledge-tree readers/writers:

- Folder/tree navigation: `src/components/FolderTree.vue:89-160` calls
  `queries.workspaceFolders`; `src/stores/workspace.ts:51-54` preloads
  `queries.entity`, `entityAccesses`, and `recentItems`; generic directory
  rendering and move/delete/rename/tag controls live in
  `src/components/EntityList.vue:278-572`.
- Note/file views: `src/views/ItemViewWrapper.vue:26` calls `queries.fullItem`;
  `src/views/ItemView.vue:300-357` calls `updateItem`; page/entity views and
  `src/composables/entity-conf.ts:26-49` mutate/read generic entity JSON.
- Trash: `src/components/TrashList.vue:73-94` calls `queries.listTrash` with
  cursor-like `start`/limit; `135-153` invokes permanent delete and restore.
- Upload: `src/utils/knowledge-upload.ts:66-105` creates folders and items via
  Zero, then uses the old `/s3/items/:id` flow. This is a cross-slice blocker
  for deleting Zero or the old item schema.
- Generic state: `src/composables/zero/query.ts:65-135` materializes a reactive
  Zero view, while `src/composables/zero/view.ts:24-137` applies Zero changes.
  `src/stores/entity.ts`, `local-entities.ts`, `recent-entities.ts`, and
  `workspace.ts` depend on those query/cache semantics. The reusable Vue
  workflow is worth retaining, but its data hooks and stores must move to the
  generated `/api/v1` client/TanStack Vue Query boundary.

### Disposition and deletion gates

| Symbol/file/domain | Disposition | Evidence and gate |
|---|---|---|
| Vue 3 knowledge workflow (`FolderTree`, `EntityList`, `ItemView`, `TrashList`, upload UI) | retain, then migrate | Existing user workflows are valuable; replace only Zero data hooks and old entity DTOs. |
| Python `WorkspaceService`, `infrastructure.db.authorization`, folder contracts/API, `_audit` | retain and extend | Canonical membership, ACL, closure, version, fail-closed decisions, and audit already exist. |
| `ima.folders`/closure/ACL tables | retain; extend with content relations | Folder authorization is target authority. Add document/content references without weakening workspace/ACL invariants. |
| `src-server/schema/schema.ts` generic `entity`, `page`, `item`, `blob`, `chunk` | migration-input, then replace/delete by slice | Legacy public rows contain IDs/content. Keep read-only until verified copy and child cutovers. |
| `src-shared/schema.gen.ts` and `src-server/schema/relations.ts` | replace, then delete | Generated Zero schema/relations encode old table names and permissions; regenerate only while legacy readers remain. |
| `src-shared/mutators.ts`, `src-shared/queries.ts`, `src-shared/table-permission.ts` | replace by explicit Python API contracts, then delete | They are the generic Zero business/data surface used by many Vue files. Remove only after all listed call sites are migrated. |
| `src-server/zero/routes.ts`, `zero/db.ts`, `zero/mutators.ts` and `zero-cache` config | temporary compatibility, then delete | Browser subscriptions and shared mutators still depend on them; cutover requires Vue Query/API plus MCP/legacy-read rollback window. |
| `src-server/kb.ts` and `kb/ops.ts` | temporary compatibility adapter, split by concern | Folder/note/tag operations move in this child; file/blob/upload waits for storage child; search/ask waits for search/RAG child; MCP currently imports all. |
| `src-server/mcp.ts` and `connectors.ts` | retain temporarily, then migrate to later Python MCP/service-principal slice | Agent tools are live consumers of every KB operation; do not delete with browser cutover. |
| `entityPermission`, `kb_acl_*`, `src-shared/utils/acl.ts`, permission relations/materialization triggers | temporary authorization bridge/migration-input, then delete | Python is sole mutable ACL authority. Delete only after every Zero reader, Bun KB/search/RAG reader, and bridge fallback is gone; this is explicitly owned by this child after route cutover. |
| `pagePatch` | migration-input; transform supported content to Markdown/version history | It is a patch log, not a version/conflict contract. Preserve or report unsupported patch histories before deletion. |
| `entity.conf.tags` and `entity.conf.parseStatus` | migration-input/temporary compatibility | Tags and parse state are untyped JSON. Copy tags to explicit target relation and parse state to ingestion child; retain fallback reads only during cutover. |
| `src-server/kb/ingest.ts`, `kb/retrieve.ts`, `kb/chunk-text.ts`, embeddings | retain behavior as migration reference, not target implementation | Later durable-ingestion/search children own jobs, chunks, vectors, ACL-first retrieval, rerank, and citations. |
| `src-server/s3.ts`, `utils/s3.ts`, browser blob upload | temporary compatibility until storage child | Existing checksums/S3 behavior must remain for rollback; target uses ticketed/versioned storage. |
| commercial/system entity types, providers/assistants/search/translation/MCP plugin | migration input or delete by approved domain scope | Generic entity tree mixes unrelated product domains; do not migrate them as knowledge files. Verify active consumers before removal. |

## Related specs

- `.trellis/spec/backend/workspace-authorization-contracts.md`: canonical
  actions, closure/anchor invariants, same-subject action dependencies,
  optimistic conflicts, fail-closed bridge, migration checkpoints, and required
  residue tests.
- `.trellis/spec/backend/database-guidelines.md`: SQLAlchemy 2 async/Alembic,
  PostgreSQL `ima`/`ima_jobs`, and prohibition on foundation migrations owning
  legacy `public` tables.
- `.trellis/spec/backend/python-foundation-contracts.md`: Python owns exact
  foundation paths until a later business-slice child migrates them; startup
  must not mutate schema.
- `.trellis/spec/frontend/openapi-client-contracts.md` and
  `.trellis/spec/frontend/workspace-authorization-contracts.md`: generated
  client, explicit server state, loading/error/conflict states, and no mutable
  JSON ACL state in Vue.
- `.trellis/tasks/archive/2026-08/08-24-workspace-authorization-core/design.md:227-250`:
  bounded legacy authorization adapter and the explicit deletion gate for
  `entityPermission`, JSON ACL, SQL functions/triggers, TypeScript policy, and
  Zero permission relations.
- `.trellis/tasks/archive/2026-08/08-24-python-foundation-contracts/design.md:82-84`:
  object storage/S3 intentionally belongs to the later durable-ingestion child.

## External references

- Rocicorp Zero package in the repository: `@rocicorp/zero` and generated
  Drizzle Zero schema; deployment pins `rocicorp/zero:0.26.1` in
  `docker-compose.example.yml:138-149`.
- Existing runtime libraries are internal repository dependencies; no external
  API documentation was required for this evidence pass.

## Caveats / Not Found

- The current task has only a TBD `prd.md`; no task-local `design.md` or
  `implement.md` was present during this research pass. This file records
  evidence and dispositions, not an implementation plan.
- Python currently has folder authorization and lifecycle APIs, but no target
  document/note/file/tag/version/blob/ingestion schema. The knowledge child
  must add those contracts while preserving existing folder/ACL behavior.
- CodeGraph has no project metadata row and unresolved external references;
  use the explicit `rg` consumer list and test imports as the deletion checklist.
- `src-server/kb/ops.ts` has both migration-domain and later-child behavior in
  one file. A whole-file delete is unsafe; split or wrap by operation group and
  keep a rollback adapter until storage and search/RAG cutovers are verified.
- Legacy audit is not a content audit: `entityAccess` is a recent-access table,
  `pagePatch` is a patch log, and the Python `ima.audit_events` contract is the
  reusable safe audit mechanism. Do not treat either legacy table as a complete
  version/conflict history.
- No destructive operation was performed; only the specified research file was
  written.
