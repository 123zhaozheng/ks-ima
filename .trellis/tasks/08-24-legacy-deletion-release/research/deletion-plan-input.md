# Research: Deletion Plan Input — Ordered Phases, Gate Checklist, Retention List

- **Query**: Consolidated input for PRD/design: recommended deletion phases, gate checklist, what stays until post-sunset.
- **Scope**: internal (synthesis of sibling research files in this directory)
- **Date**: 2026-08-29

## 0. Scope reality check (important for PRD sizing)

This task is NOT mostly "rm -rf". The frontend shell is still Zero-bound: the `/` route,
workspace selection, login guard, drawers, invitation flow, and the admin root all import
`zero-session`, and `WorkspaceConnectors` (live page) still calls the legacy Bun connector API
via a typed Hono client compiled from `src-server`. The deletion therefore has three coupled
jobs:

1. **Rewire** the surviving shell/stores/pages onto identity-client + TanStack Query (Python API).
2. **Delete** the legacy subtree: src-server (39 files), src-shared Zero modules, legacy
   views/components (~40+ files), Zero runtime, drizzle, legacy scripts, Bun Dockerfile,
   compose services, Caddy legacy routes, legacy env keys, legacy npm deps (~20 packages).
3. **Close the data boundary**: Alembic cleanup migration dropping 37 public tables + legacy
   SQL functions, retire Python bridges/projections/legacy adapters, terminal Caddy routing.

Evidence files: `deletion-inventory-bun-zero.md`, `deletion-inventory-frontend.md`,
`deletion-inventory-python-db.md`, `dependency-audit.md`, `release-gates.md`,
`ordering-constraints.md`, `risks-live-references.md`.

## 1. Preconditions (gate before any merge/deploy)

- [ ] Rollback acceptance recorded; rollback window formally closed (parent Final Acceptance:
      user/operator acceptance + verified backup; `docs/legacy-cutover-runbook.md`).
- [ ] Maintenance freeze EXITED (`ima maintenance freeze exit`, audit event) — runbook success
      path gap, see ordering-constraints §6.
- [ ] MCP sunset gate evidenced: `uv run ima inventory-legacy-mcp verify --mapping-file
      approved-mcp-decisions.json` exit 0 (pending == 0); every consumer reissued/revoked.
- [ ] Sunset approval recorded: fresh DB snapshot triple (id+checksum, object inventory, image
      digests + Caddyfile SHA-256) and explicit authorization to remove compatibility routes.
- [ ] `migrate-legacy report-all` archived as final legacy-state evidence.

## 2. Recommended ordered phases

### Phase B1 — Frontend rewiring (no legacy deletion yet; keeps rollback-buildable)
1. Rewire `stores/workspace.ts` (list/select/switch via identity-client `/api/v1/workspaces`,
   TanStack Query; replace `updateMemberData`/`updateLastWorkspaceId` mutators with Python
   equivalents or local-only state).
2. Rewire `stores/user-data.ts`, `stores/perfs.ts`, `stores/readonly-state.ts`,
   `composables/require-login.ts`, `composables/ask-knowledge.ts` off zero-session.
3. Rewire `pages/RedirectToFolder.vue` (root), `components/MainDrawer.vue`,
   `layouts/InvitationLayout.vue` (accept via identity-client), `admin/pages/EmptyPage.vue`.
4. Strip legacy connector section from `pages/WorkspaceConnectors.vue` + retire
   `CreateConnectorDialog.vue` legacy mode; point `utils/mcp-config.ts` (+test) at `/mcp`;
   fix `ConnectorCreatedDialog.vue` hint.
5. Gate: `bun run lint`, `build:front`, `build:admin`, `test:unit`, `test:e2e` green with Zero
   still importable but unused by the shell.

### Phase B2 — Frontend legacy subtree deletion
6. Delete legacy views/routes (`views/*`, `pages/DualViewPage.vue`, `/:type(chat|item|folder)`
   routes; decide `/chat/:id` redirect vs 404).
7. Delete legacy components/services/stores/composables/utils per
   `deletion-inventory-frontend.md` §4; delete `utils/zero-session.ts`,
   `composables/zero/*`, `utils/config.ts` ZERO_CACHE_URL; delete `utils/hc.ts`.
8. Relocate still-used pure helpers from `src-shared/utils/{id,validators,functions}.ts` into
   `src/utils/`, then delete `src-shared/`.
9. Update legacy-touched tests (`mcp-config.test.ts`, `WorkspaceConnectors.vitest.ts`; drop
   `open-created-entity.test.ts` if its helper went) and quasar.config dev proxies (`/api` →
   Python, drop `/zero-cache`).
10. Gate: full frontend matrix + e2e (release-gates §2-3).

### Phase B3 — Bun server & tooling deletion
11. Delete `src-server/`, legacy `scripts/` (mcp-handshake, mcp-live, permission-smoke, dev-pg),
    `drizzle/`, `drizzle.config.ts`, `drizzle-zero.config.ts`, `Dockerfile.server`, `dev-db/`.
12. package.json: remove scripts (`dev:server`, `build:server`, `generate:zero`,
    `test:permissions`, `test:mcp`, `test:mcp-live`, `dev:pg`, `dev:db-*`), remove deps per
    dependency-audit §1 (incl. already-dead: nodemailer, tokenx, @ai-sdk/openai-compatible,
    ollama-ai-provider-v2, @types/pg), regenerate `bun.lock`.
13. Gate: `bun run lint`, `bun run test` (drill still passes or is updated in B4), builds, e2e.

### Phase B4 — Routing, deployment artifacts, CI
14. Rewrite `Caddyfile` to terminal form (all live prefixes → Python; `/api/v1/internal/*` 404;
    residual `/api/*` incl. `/api/mcp` → 410/404; drop zero-cache + SERVER_URL).
15. Rewrite `scripts/caddy-routing-drill.ts` + test to pin the terminal matrix; drop
    cutover/rollback derivation phases; keep image pin + checksum evidence fields.
16. Update `docker-compose.example.yml` (drop server/zero-cache/zero DB/bridge env),
    `.env.example`, `README.md` (remove coexistence block + legacy dev steps).
17. Update `.github/workflows/*`: remove `nyaai-server` build; add backend image build/push.
18. Gate: `bun run test:caddy-routing`, compose `config` validation, residue-search gate
    (release-gates §7).

### Phase B5 — Python legacy retirement
19. Remove `api/internal/session_bridge.py`, `api/internal/authorization_bridge.py`,
    model-governance `internal_router` (+ execute/legacy/* endpoints), bridge-token settings;
    keep the Caddy-404 contract for `/api/v1/internal/*`.
20. Remove identity `public.user/userData` projection writes (+ `legacy_identity_projection`
    insertion logic; table kept as history), authorization legacy workspace guards,
    `model_governance._legacy_model`/managed_legacy_* adapters.
21. Decide + apply migration-CLI disposition (recommended: delete legacy-reading commands and
    their tests; keep checkpoint tables).
22. Replace coexistence contract tests with post-deletion invariants; update
    `conftest.py` postgres count (currently 48); keep freeze feature or simplify per decision.
23. Add Alembic cleanup migration dropping the 37 public tables + ACL functions/triggers
    (downgrade = snapshot restore, documented in migration docstring).
24. Gate: full backend matrix incl. forced-Postgres, `alembic check` on clean DB,
    contract export --check, `ima-integration` compose run.

### Phase C — Deploy & destructive close (change-controlled, post-merge)
25. Deploy: `ima-migrate` applies cleanup migration; web/api/worker images; terminal Caddyfile.
26. Post-deploy verification: terminal-route evidence (410/404), health/readiness, smoke matrix
    (platform admin, workspace admin, editor, viewer, restricted-folder user, OAuth agent,
    service principal), Playwright desktop/mobile screenshot review.
27. Deferred/last: orphan legacy S3 key purge and pre-cutover snapshot retirement (data-retention
    approval); runbook status notes "sunset complete".

## 3. Complete gate checklist (what "pass the complete release" means)

Backend (from `backend/`): `uv sync --frozen`; `ruff format --check .`; `ruff check .`;
`mypy src/ima`; `pytest`; forced-Postgres `pytest -m postgres` (update conftest count);
`alembic check` (clean-DB migrate to head); `ima contract export --check`.

Frontend: `bun install --frozen-lockfile`; `bun run lint`; `bun run test`; `bun run test:unit`;
`build:front`; `build:admin`; `test:e2e` (5 suites, desktop+mobile); `test:caddy-routing`.

Security: SBOM/dependency/image vulnerability review; no-public-egress network test (model
allowlists); non-root image check; TLS/OAuth metadata readiness; secret-safety suites;
dead-code/unused-dep removal proven.

Deployment: compose `config` + `up` smoke on clean environment; clean-install + clean-database
bootstrap (`ima migrate` + `bootstrap-admin`); restore drill on disposable environment
(post-deletion recovery = snapshot restore, rehearsed); residue-search gate clean.

Browser/PRD: all PRD acceptance scenarios incl. restricted-folder non-disclosure; official MCP
OAuth + service-principal interop; no placeholder/TODO/mock behavior; desktop+mobile layout
review.

## 4. Retention list (what survives this task)

- All `ima.*` schemas incl. checkpoint/history tables (`legacy_*_migration`,
  `legacy_identity_projection`, `legacy_model_governance_migration`,
  `legacy_knowledge_migration`) and audit rows — migration history policy.
- Alembic migration history (no squash without explicit release-policy approval).
- `docs/legacy-cutover-runbook.md` + `docs/oauth-mcp-coexistence-runbook.md` as historical
  evidence (contract-test pins re-scoped, documents optionally annotated with closure).
- Maintenance freeze machinery (decision item — generic ops tool; kept unless PRD says remove).
- `Dockerfile.postgres` (zhparser image), `Dockerfile.web`, `Dockerfile.backend`.
- `scripts/caddy-routing-drill.ts` (rewritten), `tests/e2e/*`, vitest suite, identity-client
  tests.
- Pre-cutover snapshot + retained Bun image digest + rollback.json: retained until data-retention
  approval retires them (they are the post-deletion recovery substrate).

## 5. Explicit decisions the PRD must make

1. Migration-CLI disposition after cutover: keep historical commands vs delete legacy readers
   (affects pre-deletion-rollback capability if window were reopened — moot after closure).
2. Freeze machinery: keep as generic maintenance tool vs delete with bridges.
3. `/chat/:id` legacy deep links: redirect to `/` vs 404.
4. `dev-db`/`dev-pg` developer workflow: delete vs provide a Python-dev compose equivalent.
5. `@modelcontextprotocol/sdk` (TS): drop entirely vs keep for an MCP interop test harness.
6. Promote `docker-compose.example.yml` to `deploy/compose/compose.yml` (parent gate wording)
   vs fix the gate wording.
7. Add explicit `bun run typecheck` script (`vue-tsc --noEmit`) vs rely on build-time checker.
8. i18n legacy-key sweep: in scope vs deferred cosmetic.
