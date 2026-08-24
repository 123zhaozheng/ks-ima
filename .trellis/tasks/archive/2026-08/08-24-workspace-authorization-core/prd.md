# Workspace Authorization Core

## Goal

Deliver the Python-owned workspace and folder authorization foundation for the
intranet knowledge assistant. Platform administrators must govern workspace
lifecycle without gaining knowledge access, while workspace administrators can
manage members, groups, folders, and deterministic inherited ACLs through a
usable Vue workflow. One set-based policy contract must protect direct reads,
lists, legacy coexistence paths, and every later search, RAG, download, job,
OAuth, service-principal, and MCP integration.

## Background

- The Python identity slice already owns local users, browser sessions, CSRF,
  platform roles, workspace registry metadata, and append-only platform audit.
- The legacy Bun/Zero application still stores memberships, folders, JSON ACLs,
  and per-user `entityPermission` rows in `public`; those paths currently use
  N+1 ancestor traversal and a second TypeScript ACL implementation.
- A fresh CodeGraph index at the current branch head contains 404 files, 5,098
  nodes, and 12,699 edges. Its call graph shows `assertCan` protecting Zero
  mutations and `listVisibleEntityIds` feeding legacy search and RAG retrieval.
- This is child 3 of the approved migration roadmap. It depends on the completed
  Python foundation and local identity children. Knowledge documents, tags,
  ingestion, search/RAG, OAuth/service principals, and MCP arrive in later
  children but must consume the contracts established here.

## Requirements

### R1. Workspace Lifecycle And Visibility

- Preserve the existing Python `ima.workspaces` registry and make all lifecycle
  mutations transactional, existence-aware, idempotency-safe where applicable,
  and audited. Only `super_admin` and `platform_admin` may create, archive,
  restore, or permanently delete a workspace.
- Workspace creation must create exactly one root folder with an independent
  root ACL. It must assign at least one active `workspace_admin`, either the
  explicitly selected active user or the creating platform operator when that
  operator is deliberately selected; platform role alone never creates a
  membership.
- An authenticated user may list and open only workspaces where the user has an
  active membership and the workspace is active. Platform registry APIs remain
  separate and return metadata only, never members, groups, folders, ACLs,
  names beneath the root, counts, tags, documents, or policy previews.
- Archival immediately blocks member content operations and invitation
  acceptance. Permanent deletion requires archived state, recent
  authentication, no retained content/job/OAuth dependencies, and a clear
  conflict result rather than cascading unknown future data.

### R2. Memberships, Invitations, And Groups

- Implement workspace roles `workspace_admin`, `knowledge_manager`, `editor`,
  and `viewer`; migrate legacy roles as `owner|admin -> workspace_admin`,
  `member -> editor`, and `guest -> viewer`.
- Membership lifecycle is explicit (`active`, `invited`, `disabled`) with
  grantor, joined/disabled timestamps, and version/concurrency metadata.
  Workspace administrators can search eligible active local users, directly
  add them, issue/revoke single-use expiring invitations to existing accounts,
  disable/restore/remove members, and change roles.
- Workspace invitations never create an account or bypass platform account
  governance. Invite acceptance requires the authenticated local account named
  by the invitation, an active workspace/account, a valid unused token, and an
  atomic membership transition. SMTP absence returns a `manual` delivery state
  and displays the bound link once for manual handoff; it must never report a
  fake send or persist/render the raw token again.
- At least one active `workspace_admin` must remain under concurrent disable,
  remove, leave, and role-change requests. A platform administrator may repair
  workspace-admin assignment through a narrow audited endpoint without
  receiving content access or general membership management authority.
- Workspace administrators can create, rename, and delete local groups and add
  or remove active workspace members. Group deletion removes that subject's ACL
  grants transactionally and reports the affected ACL count before confirmation.
  A user outside the workspace cannot be searched into or added to a group.

### R3. Folder Hierarchy

- Implement Python-owned `folders` and `folder_closure` with one immutable root
  identity per workspace. The root folder ID equals the preserved workspace ID;
  siblings have ordering, folders have active/trashed lifecycle and optimistic
  versions, and the database enforces workspace/parent integrity.
- Implement list/tree/breadcrumb plus create, rename, reorder, move, trash,
  restore, and permanent-delete commands needed to administer the hierarchy.
  Commands must reject root mutation, cycles, cross-workspace parents, name/order
  conflicts, stale versions, unauthorized destinations, and invalid restores.
- Move, trash, restore, and deletion update closure rows and ACL anchors in the
  same transaction. Unauthorized ancestors, names, breadcrumbs, children, and
  counts are omitted and a direct unauthorized lookup returns the same 404
  contract as a nonexistent folder.
- Folder creation and all target writes go through Python. During the bounded
  coexistence window, any legacy folder projection required by the still-live
  knowledge UI is written from the same transaction and has an explicit owner,
  equivalence test, telemetry, rollback point, and deletion milestone in the
  `knowledge-tree-vue-api` child.

### R4. ACL Model And Semantics

- Use actions `view_metadata`, `view_content`, `download`, `ask`,
  `create_child`, `edit`, `move`, `delete`, and `manage_acl`. ACL entries are
  grants only; MVP has no explicit deny or allow/deny precedence.
- The root folder always has an independent ACL. The default root grants are:
  `workspace_admin` and `knowledge_manager` receive all actions; `editor`
  receives all except `manage_acl`; `viewer` receives `view_metadata`,
  `view_content`, `download`, and `ask`.
- Child folders inherit the nearest independent ACL through `acl_anchor_id`.
  Breaking inheritance copies the current effective normalized grants before
  editing; replacing an independent ACL is an atomic versioned operation.
  Re-enabling inheritance removes the child ACL only after repointing the whole
  subtree to the nearest parent anchor in the same transaction.
- ACL subjects in this child are workspace roles, local workspace groups, and
  active workspace users. The schema and policy subject context must have a
  deliberate extension point for later service principals, but no placeholder
  service-principal endpoint or grant is exposed before that child exists.
- `ask` is effective only with `view_content`; a citation requires both
  `view_metadata` and `view_content`; download requires those two plus
  `download`. Future documents inherit their containing folder ACL in MVP.
- ACL editing includes searchable subject selection, grouped action controls,
  inherited/effective-source display, destructive-change confirmation, version
  conflicts, and a permission preview for one selected workspace subject.
  Preview reveals only folders/paths that subject may view and never reveals a
  hidden name as an explanation.

### R5. Canonical Policy Service

- Implement one transport-independent actor/subject context and one action
  taxonomy. Human authority is the intersection of active account, active
  workspace, active membership, role, groups, and matching ACL grants.
  Platform roles are deliberately absent from folder grant resolution.
- Single-resource checks and collection filtering must use the same set-based
  SQL predicate over membership/groups, `acl_anchor_id`, and normalized ACL
  entries. Policy APIs/query builders must support folder, subtree, and root
  scope now and expose composable hooks for later document/chunk/download/job/
  delegated/service scopes without granting those future actors prematurely.
- Policy failures return internal stable reason codes for tests and audit, but
  public folder/resource APIs collapse hidden/not-member/not-granted cases to
  non-discovering 404 responses. Mutation conflicts that reveal no hidden
  resource may use 409; unauthenticated requests remain 401.
- No decision cache is introduced in this child unless membership, group, ACL,
  account disablement, and workspace archival invalidation are proven atomic
  and immediate. Correct uncached evaluation is the required baseline.

### R6. Legacy Authorization Cutover And Removal

- Add a resumable, idempotent workspace authorization slice migration with
  plan/apply/verify/report behavior and per-record checkpoints for workspaces,
  members, folders, closure, groups if present, and JSON ACLs. Preserve valid
  IDs; reject/report cycles, cross-workspace parents, missing users, malformed
  ACLs, and conflicting roots without guessing.
- All new membership/group/folder/ACL writes use Python. A bounded compatibility
  adapter may keep still-live Bun/Zero readers consistent, but it must derive
  from target state, fail closed, be equivalence-tested for every action, and
  be owned for deletion by `knowledge-tree-vue-api`.
- Delete replaced client-side ACL editing and duplicate ACL parsing as soon as
  their consumers move. Delete legacy JSON ACLs, `kb_acl_*` functions,
  permission rebuild triggers, `entityPermission`, TypeScript policy code, and
  Zero permission joins only when the named remaining legacy readers have moved;
  a live compatibility consumer is not redundant code and must be documented.
- No two independently mutable policy sources may govern the same routed
  resource. Legacy residue scans and CodeGraph affected-path checks must
  classify every retained authorization symbol and its deletion owner.

### R7. API, Vue, Audit, And Operations

- Publish versioned generated OpenAPI contracts for member workspaces,
  memberships/invitations, groups, folders, ACL replacement/inheritance,
  subject search, and permission preview. Use the existing cookie/CSRF client
  and Problem Details contract; do not introduce handwritten duplicate DTOs.
- Build a complete workspace administration experience using Vue, Quasar, and
  Vue Query: member/group tabs, folder permission explorer, loading/empty/error/
  retry/stale/archived/access-revoked states, keyboard-accessible dialogs, and
  permission-aware controls. Backend authorization remains authoritative.
- Audit successful and rejected workspace lifecycle, membership, group, folder,
  ACL, repair, invitation, and migration actions using safe IDs/counts/version/
  reason metadata. Do not store folder names, paths, ACL subject display names,
  invitation tokens, content, or secrets in audit/log/error metadata.
- Add operator documentation for initial workspace-admin assignment, repair,
  migration, verification, rollback, audit interpretation, and compatibility
  adapter removal. Routine operation must not require manual SQL.

### R8. Completeness And Quality

- Add unit, forced-PostgreSQL integration, migration, concurrency, OpenAPI drift,
  generated-client, Vue component, and Playwright tests. Required PostgreSQL
  tests may not skip; query plans run against a production-shaped deep/wide
  fixture and must use the intended closure/ACL indexes and set-based joins.
- Generate a matrix covering every workspace role/action plus role, group, and
  direct grants; inherited/broken ACLs; missing/disabled membership; disabled
  account; archived workspace; direct/list/breadcrumb/subtree endpoints; and
  the compatibility path. Later children extend the same matrix for documents,
  search/RAG, download, jobs, OAuth, service principals, SSE, and MCP.
- No accepted flow may be a TODO, placeholder, mock-only path, hidden skip,
  hard-coded success, undocumented manual repair, or frontend-only permission
  check. Every replacement must satisfy its deletion gate.

## Acceptance Criteria

- [x] AC1 (`R1`): Platform lifecycle and member workspace-list APIs enforce the
      separate platform/content boundaries; a platform admin without explicit
      membership cannot retrieve any folder, ACL, path, count, or preview.
- [x] AC2 (`R1`, `R2`): Workspace creation/repair establishes an explicit active
      workspace admin, and concurrent demote/disable/remove/leave operations can
      never leave an active workspace without one.
- [x] AC3 (`R2`): Existing-account add/invite/accept, role/state lifecycle, group
      lifecycle, group membership, SMTP-unavailable behavior, and safe errors
      work end to end through the Vue UI, generated API, database, and audit.
- [x] AC4 (`R3`): Root/create/rename/reorder/move/trash/restore/delete and
      tree/breadcrumb APIs maintain correct closure/anchor data, reject cycles,
      cross-workspace and stale mutations, and have complete UI states.
- [x] AC5 (`R4`, `R5`): Every action resolves identically for role, group, direct,
      inherited, and independent ACL grants through direct policy checks and
      set-based list filters; ask/citation/download dependencies cannot be
      bypassed.
- [x] AC6 (`R3`, `R5`): Unauthorized folder IDs, names, ancestors, descendants,
      breadcrumbs, counts, and preview explanations are indistinguishable from
      nonexistent resources at every public endpoint.
- [x] AC7 (`R4`): Breaking inheritance copies the effective grants, ACL replace
      detects stale versions, re-enabling inheritance repoints the subtree, and
      folder moves change effective access atomically.
- [x] AC8 (`R5`): Account disablement, membership/group/ACL changes, and workspace
      archival affect the next authorization decision without a stale cache or
      token-expiry delay.
- [x] AC9 (`R6`): Workspace authorization plan/apply/verify/report is resumable
      and idempotent, reports malformed/conflicting records safely, preserves
      valid IDs, and proves target/legacy equivalence for routed legacy data.
- [x] AC10 (`R6`): Replaced ACL code is deleted; each retained compatibility
      symbol has a real live consumer, fail-closed test, telemetry, rollback
      owner, and `knowledge-tree-vue-api` deletion milestone.
- [x] AC11 (`R7`): Audits and logs cover mutations/denials without names, paths,
      tokens, secrets, or content; operators can migrate, repair, verify, and
      roll back without manual SQL.
- [x] AC12 (`R8`): Ruff, mypy, all backend tests, forced PostgreSQL with zero
      skips, OpenAPI export/generation/drift, ESLint, `vue-tsc`, Bun/Vitest,
      PWA/Admin/Server builds, Playwright role journeys, residue scans, and
      query-plan assertions pass.

## Out Of Scope

- Document/version/blob/tag schemas and the complete knowledge list/note/file
  UI migration; `knowledge-tree-vue-api` owns those and removes the bounded
  folder/permission compatibility projection.
- Object storage, ingestion workers, parsing, chunks, embeddings, FTS/vector
  retrieval, conversations, grounded answers, citations UI, and downloads.
- OAuth consent/tokens, service-principal credentials, MCP endpoints/tools, and
  their runtime scope intersections. This child defines extension contracts and
  no usable credential or phantom principal.
- Model gateways, model/profile assignment, connector credentials, LDAP/OIDC,
  explicit deny ACLs, document-specific ACL overrides, cross-workspace search,
  public sharing, billing, plans, quotas, or per-user infrastructure settings.
