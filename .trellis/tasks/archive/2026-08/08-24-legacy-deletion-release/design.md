# Legacy Deletion and Release Hardening — Design

Evidence: `research/` in this task directory (deletion inventories, dependency
audit, release-gates matrix, ordering constraints, live-reference risks,
deletion-plan-input). This document fixes the technical decisions.

## 1. Phase ordering (why rewire first)

The frontend shell (`/` route, workspace store, login guard, drawers,
invitation flow, admin root) imports `zero-session`; `src/utils/hc.ts`
compiles migrated pages against `src-server` types; `WorkspaceConnectors`
still calls the legacy connector API. Deleting before rewiring breaks the
build, so:

```
B1 frontend rewire → B2 frontend deletion → B3 Bun server/tooling deletion
→ B4 routing/deploy/CI → B5 Python retirement → gates
```

Each phase keeps the repo green (build + lint + tests) so any phase boundary
is a safe stopping point.

## 2. B1 — Frontend rewiring

- `stores/workspace.ts`: list/select/switch via `identityClient`
  (`/api/v1/workspaces`) + TanStack Query; `updateMemberData`/
  `updateLastWorkspaceId` become local-only state or Python equivalents.
- `stores/user-data.ts`, `stores/perfs.ts`, `stores/readonly-state.ts`,
  `composables/require-login.ts`, `composables/ask-knowledge.ts`: off
  `zero-session` onto identity session/cookie state.
- `pages/RedirectToFolder.vue`, `components/MainDrawer.vue`,
  `layouts/InvitationLayout.vue` (accept via identity-client),
  `admin/pages/EmptyPage.vue`.
- `pages/WorkspaceConnectors.vue`: remove legacy connector section; retire
  `CreateConnectorDialog.vue` legacy mode; `utils/mcp-config.ts` (+test) at
  `/mcp`; fix `ConnectorCreatedDialog.vue` hint.
- Gate: lint, `build:front`, `build:admin`, `test:unit`, `test:e2e` green
  (Zero still importable but unused by the shell).

## 3. B2 — Frontend legacy subtree deletion

Per `deletion-inventory-frontend.md`:
- Delete legacy views/routes (`views/*`, `pages/DualViewPage.vue`,
  `/:type(chat|item|folder)` routes); `/chat/:id` becomes a redirect to `/`.
- Delete legacy components/services/stores/composables/utils; delete
  `utils/zero-session.ts`, `composables/zero/*`, ZERO_CACHE_URL config,
  `utils/hc.ts`.
- Relocate still-used pure helpers from `src-shared/utils/{id,validators,
  functions}.ts` into `src/utils/`, then delete `src-shared/`.
- Update legacy-touched tests; quasar dev proxies: `/api` → Python, drop
  `/zero-cache`.
- Gate: full frontend matrix + e2e.

## 4. B3 — Bun server & tooling deletion

- Delete `src-server/`, legacy `scripts/` (mcp-handshake, mcp-live,
  permission-smoke, dev-pg), `drizzle/`, `drizzle.config.ts`,
  `drizzle-zero.config.ts`, `Dockerfile.server`, `dev-db/`.
- package.json: remove `dev:server`, `build:server`, `generate:zero`,
  `test:permissions`, `test:mcp`, `test:mcp-live`, `dev:pg`, `dev:db-*`;
  remove unused deps per `dependency-audit.md` (incl. already-dead
  nodemailer, tokenx, @ai-sdk/openai-compatible, ollama-ai-provider-v2,
  @types/pg); regenerate `bun.lock`.
- Gate: lint, bun test, builds, e2e.

## 5. B4 — Routing, deployment artifacts, CI

- Caddyfile terminal form: all live prefixes → Python; `/api/v1/internal/*`
  404; residual `/api/*` incl. `/api/mcp` → 410/404; drop zero-cache +
  SERVER_URL.
- `scripts/caddy-routing-drill.ts` rewritten to pin the terminal matrix;
  cutover/rollback derivation phases dropped; image pin + checksum evidence
  fields kept.
- `docker-compose.example.yml`: drop server/zero-cache/zero DB/bridge env;
  `.env.example` + README cleaned of coexistence/legacy dev steps.
- `.github/workflows/*`: remove `nyaai-server` build; add backend image
  build/push.
- Gate: `test:caddy-routing`, compose `config` validation, residue-search
  gate.

## 6. B5 — Python legacy retirement

- Remove `api/internal/session_bridge.py`, `api/internal/authorization_
  bridge.py`, model-governance internal router (+ execute/legacy endpoints),
  bridge-token settings; keep Caddy-404 contract for `/api/v1/internal/*`.
- Remove identity `public.user/userData` projection writes, authorization
  legacy workspace guards, `model_governance._legacy_model`/managed_legacy
  adapters (per `deletion-inventory-python-db.md` file:line list).
- Delete legacy importer CLI commands (`migrate-legacy-*`) and their tests;
  keep checkpoint/history tables. `inventory-legacy-mcp` retired with the
  sunset gate complete; legacy MCP inventory code removed.
- Coexistence contract tests replaced by post-deletion invariants
  (terminal 404s, no legacy route, internal-404 retained); conftest
  forced-postgres count updated in the same change.
- Maintenance freeze machinery kept (generic ops tool).

## 7. Data boundary closure

- Final Alembic migration (after `20260828_0010`): drop the 37 `public`
  tables + legacy ACL functions/triggers listed in
  `deletion-inventory-python-db.md`. Downgrade = snapshot restore only,
  documented in the migration docstring. `ima.*` checkpoint/history tables
  untouched.
- Verify: fresh-DB `alembic upgrade head` + repeat run; forced-Postgres
  suite green with updated count.

## 8. Release gates (complete checklist per research/release-gates.md)

Backend: `uv sync --frozen`; ruff format/check; mypy; pytest; forced
Postgres; `alembic check`; `uv run python scripts/check_contract.py`.
Frontend: `bun install --frozen-lockfile`; lint; bun test; test:unit;
build:front; build:admin; test:e2e; test:caddy-routing.
Deployment: compose `config` + clean bootstrap smoke (`ima migrate` +
`bootstrap-admin` on fresh DB); residue-search gate clean.

## 9. Non-goals

- No i18n legacy-key cosmetic sweep.
- No Alembic history squash.
- No pre-cutover snapshot retirement (future data-retention decision).
- No real-cluster deploy; Phase C deploy steps are encoded in the runbook
  update, not executed here.
