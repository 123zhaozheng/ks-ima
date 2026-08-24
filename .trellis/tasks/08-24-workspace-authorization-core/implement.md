# Workspace Authorization Core Implementation

## 1. Preflight And Contract Fixtures

- Refresh CodeGraph and capture affected legacy callers for ACL checks, Zero
  readable queries/mutations, search, RAG, S3/download, connectors, and MCP.
- Add representative legacy fixtures: all four old roles, deep/wide folders,
  inherited/broken/malformed ACLs, direct users, duplicate/missing members,
  cycles, cross-workspace parents, archived workspaces, and permission rows.
- Write the role/action/security matrix and target OpenAPI/error expectations
  before implementation. Record the exact compatibility consumers and deletion
  owner; do not start with a generic shim.

## 2. Additive Schema Migration

- Add `workspace_members`, `workspace_invitations`, `workspace_groups`,
  `workspace_group_members`, `folders`, `folder_closure`, `folder_acls`,
  `folder_acl_entries`, and migration checkpoint/report state.
- Add explicit role/state/action/subject constraints, versions, timestamps,
  composite workspace integrity, normalized names, and query indexes.
- Extend workspace creation so root folder, root ACL, closure self-row, and
  selected workspace admin commit together; migrate existing empty registry
  workspaces through an explicit command rather than startup SQL.
- Test fresh migration, repeat upgrade, downgrade guard, legacy-schema isolation,
  constraints, and exact forced-PostgreSQL collection count.

## 3. Domain And Canonical Policy

- Add enums/value objects for workspace roles, states, ACL actions/subjects,
  subject context, decisions, and safe reason codes.
- Implement one set-based SQLAlchemy CTE/predicate for active membership,
  role/user/group grants, action dependencies, optional root, and closure.
- Build single-folder decision, accessible folder/subtree selection, and future
  resource-anchor composition from the same predicate.
- Add a generated exhaustive matrix test and production-shaped `EXPLAIN` tests;
  reject any N+1 ancestor/resource loop or per-user-resource materialization in
  the target service.

## 4. Workspace Membership And Groups

- Implement member workspace list/detail and separate platform metadata/repair
  authorization boundaries.
- Implement existing-user search/add, invitation issue/list/revoke/accept,
  disable/restore/remove/leave, and role changes with active-user/workspace
  validation, CSRF, versions, audits, and honest SMTP state.
- Use a workspace advisory lock plus row locks for every last-admin-affecting
  operation; add true concurrency tests for demote/disable/remove/leave/repair.
- Implement group CRUD, affected-ACL preview on delete, membership changes, and
  atomic grant cleanup. Test wrong-workspace, inactive member, duplicate, stale,
  and concurrent changes.

## 5. Folder And ACL Application Services

- Implement root/list/tree/breadcrumb and create/rename/reorder operations with
  non-discovering filters and optimistic versions.
- Implement move closure surgery and inherited-anchor recomputation in one
  locked transaction; cover deep subtree, cycle, cross-workspace, stale, sibling
  conflict, concurrent move, and effective-access changes.
- Implement trash/restore/permanent-delete with original location, dependency
  refusal, root protection, authorized fallback destination, and audits.
- Implement ACL read, break-copy-replace, re-enable inheritance, subject search,
  group/direct grants, action implication validation, and permission preview.
- Prove immediate changes for account/member/group/workspace/ACL lifecycle and
  hidden names/breadcrumbs/counts on every public folder path.

## 6. API And Generated Contracts

- Add workspace contracts/router and register it in the application factory;
  extend the existing admin router only for narrow repair/lifecycle integration.
- Give every operation a stable operation ID, generated request/response type,
  bounded pagination/bulk limits, CSRF/recent-auth behavior, and Problem Details
  tests including hidden-resource 404 and version 409.
- Export deterministic OpenAPI, regenerate `src/api/generated/schema.ts`, and
  extend the one central identity/API client plus Vue Query composables. Do not
  add local DTO copies or fetch calls inside components.

## 7. Vue Workspace Administration

- Replace plan/owner/member-limit workspace overview controls with generated API
  member/group/directory-permission tabs and ordinary member metadata.
- Implement searchable add/invite, role/state changes, leave/remove, group CRUD
  and membership, affected-grant confirmation, loading/empty/error/retry/stale/
  archived/access-revoked states, and capability-aware controls.
- Replace `FolderAclDialog.vue` with the normalized ACL editor: inheritance,
  effective source, role/group/user picker, all actions, preview, confirmation,
  conflict reload, keyboard/focus/labels, desktop and mobile layouts.
- Add concrete Vitest component assertions and Playwright journeys for all four
  workspace roles plus nonmember platform admin and repair behavior.

## 8. Legacy Authorization Slice Migration

- Implement `ima migrate-legacy-authorization plan|apply|verify|report` with
  fingerprints, per-record commits/checkpoints, resumability, idempotency, safe
  errors, role mapping, folder/ACL normalization, and equivalence report.
- Route all membership/group/folder/ACL target writes through Python. Add the
  named target-derived compatibility projection/adapter for the exact remaining
  Bun/Zero knowledge consumers, with batch behavior, deadline, fail-closed
  result, metrics, and action equivalence tests.
- Remove legacy ACL mutation UI/routes and duplicated parsing whose consumers
  have moved. Keep only proven live compatibility readers, annotate their owner
  in code/spec, and add residue assertions so new code cannot depend on them.
- Update Caddy/Compose/config/operator docs for exact public and private routes;
  prove the private authorization bridge is absent from OpenAPI/public routing.

## 9. Security And Audit Review

- Trace member and platform-admin requests through session, API, application,
  policy SQL, database, projection, and response. Verify no platform-role
  content bypass and no frontend-only enforcement.
- Assert audit/Problem/log/OpenAPI/browser storage never contain invitation raw
  values, names/paths hidden by ACL, content, email/display search results in
  denial metadata, or internal policy details.
- Exercise permission changes concurrently with list/get/move/preview and prove
  transactionally consistent old-or-new results, never a mixed hierarchy.

## 10. Validation Commands

Backend:

```text
cd backend
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest -m postgres
uv run python scripts/export_openapi.py --check
```

Frontend/coexistence:

```text
bun run generate:api
bun run lint
bunx vue-tsc --noEmit
bun test src src-server src-shared
bun run test:unit
bun run build:front
bun run build:admin
bun run build:server
bun run test:e2e
codegraph affected <changed authorization source files>
```

Database/security gates:

- fresh and repeat Alembic; authorization migration plan/apply/repeat/verify;
- forced PostgreSQL has zero skipped required tests;
- `EXPLAIN` uses closure/member/ACL indexes on deep/wide fixture;
- role/action/subject/transport matrix is exhaustive for current paths;
- CodeGraph/residue scans classify `entityPermission`, `kb_acl_`, JSON `acl`,
  `utils/acl`, `permissions.ts`, Zero `permission` relations, old roles, plan,
  owner, TODO/placeholder/mock/skip, and undocumented compatibility calls;
- OpenAPI/generated files have no drift and all three production builds pass.

## 11. Deletion Gate And Executable Spec

- Delete every replaced legacy UI, mutation, parser, relation, generated symbol,
  script, localization key, and dependency once no live consumer remains.
- For each retained legacy authorization reader, record exact caller, reason,
  fail-closed/equivalence test, telemetry, rollback owner, and deletion in
  `08-24-knowledge-tree-vue-api`; unclassified residue fails the task.
- Run `trellis-check`, fix all findings, then add executable backend and frontend
  workspace-authorization specs with signatures, invariants, error matrix,
  tests, and wrong/correct examples. Re-run the full affected gate before commit.

## 12. Rollback Point

- Preserve the pre-cutover database/deployment snapshot and a read-only legacy
  workspace/member/folder/ACL export plus equivalence report.
- Before the knowledge-tree child closes the compatibility window, rollback by
  restoring the snapshot and previous routes/artifacts. Do not reverse-sync
  partially mutated target state into legacy tables.
- Do not drop legacy permission structures in this child while a documented live
  Zero/Bun consumer still requires them. Drop them only with that consumer's
  route cutover and verified backup.
