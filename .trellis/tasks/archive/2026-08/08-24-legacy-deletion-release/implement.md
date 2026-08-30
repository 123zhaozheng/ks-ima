# Legacy Deletion and Release Hardening — Implementation Plan

## Preconditions

- Re-read PRD, `design.md`, and the `research/` inventories before each
  phase; they contain exact path lists and file:line references.
- Every phase must end green (lint + builds + tests) so phase boundaries are
  safe stopping points.
- Deletions use `git rm`-equivalent removals; never leave dead stubs.

## Ordered Work

### B1. Frontend rewiring (no deletion yet)

1. Rewire `stores/workspace.ts` onto identity-client + TanStack Query
   (`/api/v1/workspaces`); replace member-data/last-workspace mutators with
   local-only state or Python equivalents.
2. Rewire `stores/user-data.ts`, `stores/perfs.ts`, `stores/readonly-state.ts`,
   `composables/require-login.ts`, `composables/ask-knowledge.ts` off
   `zero-session`.
3. Rewire `pages/RedirectToFolder.vue`, `components/MainDrawer.vue`,
   `layouts/InvitationLayout.vue`, `admin/pages/EmptyPage.vue`.
4. Strip legacy connector section from `pages/WorkspaceConnectors.vue`;
   retire `CreateConnectorDialog.vue` legacy mode; `utils/mcp-config.ts`
   (+test) → `/mcp`; fix `ConnectorCreatedDialog.vue` hint.

Gate: `bun run lint`, `build:front`, `build:admin`, `test:unit`, `test:e2e`
green with Zero unused by the shell.

### B2. Frontend legacy subtree deletion

5. Delete legacy views/routes per inventory; `/chat/:id` → redirect to `/`.
6. Delete legacy components/services/stores/composables; delete
   `utils/zero-session.ts`, `composables/zero/*`, ZERO_CACHE_URL,
   `utils/hc.ts`.
7. Relocate used pure helpers from `src-shared/utils/` to `src/utils/`;
   delete `src-shared/`.
8. Update legacy-touched tests; quasar dev proxies (`/api` → Python; drop
   `/zero-cache`).

Gate: full frontend matrix + e2e.

### B3. Bun server & tooling deletion

9. Delete `src-server/`, legacy scripts, drizzle artifacts,
   `Dockerfile.server`, `dev-db/`.
10. Prune package.json scripts + unused deps per dependency audit;
    regenerate `bun.lock`.

Gate: lint, bun test, builds, e2e.

### B4. Routing, deployment artifacts, CI

11. Rewrite Caddyfile terminal form (live prefixes → Python; internal 404;
    residual `/api/*` incl. `/api/mcp` → 410/404; drop zero-cache).
12. Rewrite `scripts/caddy-routing-drill.ts` + test to pin terminal matrix;
    keep image pin/checksum evidence.
13. Update compose example, `.env.example`, README; rewrite GitHub workflows
    (drop `nyaai-server` build, add backend image build).

Gate: `test:caddy-routing`, compose `config`, residue search.

### B5. Python legacy retirement

14. Remove internal bridges + bridge-token settings (keep internal-404
    contract), identity projection writes, authorization legacy guards,
    legacy model adapters.
15. Delete `migrate-legacy-*` importer commands + tests; retire
    `inventory-legacy-mcp`; keep checkpoint/history tables.
16. Replace coexistence contract tests with post-deletion invariants; update
    conftest forced-postgres count in the same change.
17. Add final Alembic cleanup migration dropping `public.*` tables + legacy
    ACL functions/triggers (downgrade = snapshot restore, documented).

Gate: full backend matrix incl. forced Postgres + `alembic check` on fresh
DB + contract export --check.

### Final. Complete release gate pass

18. Run the whole gate checklist (design §8): backend matrix, frontend
    matrix, e2e, drill, compose config, clean bootstrap smoke, residue
    search. Fix any drift.
19. Annotate both runbooks with sunset-closure notes; keep contract pins
    re-scoped to terminal reality.

## Required Verification

```powershell
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
$env:IMA_REQUIRE_POSTGRES = "1"; $env:IMA_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app"; uv run pytest -m postgres
uv run alembic check
uv run python scripts/check_contract.py
```

```powershell
bun run lint
bun run test
bun run test:unit
bun run build:front
bun run build:admin
bun run test:e2e
bun run test:caddy-routing
```

Residue-search gate: repository-wide searches for `src-server`,
`zero-session`, `ZERO_CACHE_URL`, `drizzle`, `/api/mcp` live references,
`public."` SQL references outside the cleanup migration return nothing
actionable.

## Review Gates

After each phase diff-review for: accidental removal of retained artifacts
(checkpoint tables, runbooks, drill evidence fields), lingering legacy
imports, broken generated-client usage, and secrets/env leakage. Any
deleted behavior that had tests must have those tests deleted or replaced in
the same phase.

## Rollback

Pre-merge rollback = revert commits. Post-deletion recovery is snapshot
restore only (runbook); the cleanup migration's downgrade documents this.
