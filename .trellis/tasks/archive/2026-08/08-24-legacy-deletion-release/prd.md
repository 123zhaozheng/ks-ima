# Legacy deletion and release hardening

## Goal

Delete Zero/Bun/commercial/removed-feature residue after rollback acceptance and pass the complete release, security, deployment, and browser gates.

## Scope decisions (2026-08-29)

- System is pre-production with no live user data: rollback-window closure and
  sunset approval are treated as satisfied by the recorded cutover rehearsal +
  drill evidence from `08-24-legacy-migration-cutover`. No manual wait.
- Legacy `public.*` tables ARE dropped by a final Alembic cleanup migration
  (point of no return, accepted pre-production).
- Migration-CLI disposition: delete the legacy-reading importer commands and
  their tests; keep checkpoint/history tables and audit rows as migration
  history.
- Maintenance freeze machinery is kept as a generic ops tool.
- Legacy `/chat/:id` deep links redirect to `/` (safe UX) instead of 404.
- `dev-db`/`dev-pg` legacy developer workflow is deleted; Python dev uses the
  existing compose Postgres.
- TS `@modelcontextprotocol/sdk` dependency is dropped with the legacy MCP
  scripts; Python-side MCP interop tests remain the protocol suite.
- `docker-compose.example.yml` stays the deployment example; gate wording in
  parent docs is corrected rather than promoting files.
- No separate `bun run typecheck` script; the build-time vue-tsc checker is
  the gate.
- i18n legacy-key cosmetic sweep is deferred (out of scope).

## Requirements

1. Frontend rewiring (B1): rewire the surviving shell — workspace store,
   user-data/perfs/readonly stores, login guard, ask-knowledge composable,
   root redirect, main drawer, invitation layout, admin empty page, and the
   legacy connector section of WorkspaceConnectors — onto identity-client +
   TanStack Query (Python API). `mcp-config` points at canonical `/mcp`.
2. Frontend deletion (B2): remove legacy views/routes/components/services/
   stores/composables, Zero runtime (`zero-session`, `composables/zero/*`,
   ZERO_CACHE_URL), `utils/hc.ts`, and `src-shared/` (relocating still-used
   pure helpers first); update quasar dev proxies.
3. Bun server deletion (B3): remove `src-server/`, legacy scripts, drizzle
   artifacts, `Dockerfile.server`, `dev-db/`; prune package.json scripts and
   ~20 unused deps; regenerate lockfile.
4. Routing/deploy/CI (B4): rewrite Caddyfile to terminal form (all live
   prefixes → Python; `/api/v1/internal/*` 404; residual `/api/*` incl.
   `/api/mcp` → 410/404), rewrite the routing drill to pin the terminal
   matrix, update compose example / `.env.example` / README, and fix GitHub
   workflows (drop `nyaai-server` build, add backend image build).
5. Python retirement (B5): remove internal bridges (session/authorization/
   model-governance internal router), bridge-token settings, identity
   `public.user` projection writes, authorization legacy guards, legacy model
   adapters, and the legacy importer CLI commands + tests; update coexistence
   contract tests to post-deletion invariants; update conftest postgres count.
6. Data boundary closure: Alembic cleanup migration (last in chain) dropping
   the 37 `public` tables plus legacy ACL functions/triggers; downgrade
   documented as snapshot restore only.
7. Release gates: full backend matrix (ruff/mypy/pytest/forced-Postgres/
   alembic check/contract check script), full frontend matrix (lint/bun
   test/test:unit/builds/e2e/caddy drill), compose config validation,
   residue-search gate (no legacy references remain), and clean-bootstrap
   smoke (fresh DB `ima migrate` + `bootstrap-admin`).

## Constraints

- All `ima.*` checkpoint/history tables and audit rows are retained.
- Alembic history is not squashed.
- Runbook documents are retained as historical evidence; contract-test pins
  are re-scoped, not deleted silently.
- Pre-cutover snapshot/rollback artifacts remain referenced by docs until a
  future data-retention decision retires them.
- No legacy fallback may remain anywhere after this task; Python is the only
  backend.

## Acceptance Criteria

- [ ] Zero `src-server`, Zero-runtime, drizzle, and legacy frontend files
      remain; residue-search gate is clean.
- [ ] Shell pages work against the Python API (workspace list/switch, login
      guard, invitation accept, connectors/service access UI).
- [ ] Caddy terminal matrix validated by the rewritten drill; legacy routes
      answer 410/404.
- [ ] Cleanup migration applies on a clean and an existing database;
      `alembic check` green; forced-Postgres suite green with updated count.
- [ ] Complete gate checklist passes (backend, frontend, e2e, drill, compose
      config, bootstrap smoke).
- [ ] No unused legacy npm deps remain; lockfile consistent.

## Notes

- See `design.md` and `implement.md`; evidence in `research/` (inventories,
  dependency audit, gate matrix, ordering constraints, live-reference risks).
