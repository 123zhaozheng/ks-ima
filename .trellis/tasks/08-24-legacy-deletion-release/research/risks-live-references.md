# Research: Risks — Live References and Hidden Couplings to Legacy

- **Query**: Anything still importing legacy modules or assuming Bun/Zero; risks for the deletion.
- **Scope**: internal
- **Date**: 2026-08-29

## 1. Compile-time coupling of migrated frontend to `src-server`

`src/utils/hc.ts` imports `type { AppType } from 'app/src-server/index'` and builds a typed
Hono client. Deleting `src-server/` breaks compilation of every consumer until rewired:

| Consumer | Legacy endpoint called | Migrated-page risk |
|---|---|---|
| `src/pages/WorkspaceConnectors.vue:352,514,531` | `GET /api/connectors`, `POST /api/connectors/:id/rotate`, `DELETE /api/connectors/:id` | HIGH — live page mixes Python service principals with legacy connector keys |
| `src/components/CreateConnectorDialog.vue:165` | `POST /api/connectors` + shows `/api/mcp` hint text | HIGH — used by WorkspaceConnectors |
| `src/stores/workspace.ts:30` | `GET /api/connectors/workspaces` fallback | MEDIUM — shell store |
| `src/components/SearchEntityDialog.vue:174` | `POST /api/search` | LOW (legacy dialog, delete) |
| `src/components/EntityList.vue:404`, `src/views/ItemView.vue:328` | `POST /api/kb/reparse` | LOW (legacy subtree, delete) |

## 2. Zero boots with the app (module-load side effect)

`src/utils/zero-session.ts` constructs `new Zero({ cacheURL: '/zero-cache' })` at import time and
re-creates it on session change; ~20 modules import it (incl. `RedirectToFolder` — the `/` route,
`MainDrawer`, `require-login`, workspace/user-data/perfs stores, InvitationLayout, admin
EmptyPage). Until rewired, the shipped build attempts zero-cache websocket connections even
though `/api/zero*` is 403 and zero-cache is scheduled for removal — deletion without rewiring
breaks login/workspace selection, not just dead pages.

## 3. Legacy URLs surfaced to users in live UI/docs

- `src/utils/mcp-config.ts:15,98` builds `.../api/mcp` URLs shown in connector setup UI;
  `mcp-config.test.ts` asserts them. Must flip to `/mcp`.
- `src/components/ConnectorCreatedDialog.vue:166` hint mentions `http://127.0.0.1:3000/api/mcp`.
- `README.md:18-29` documents the coexistence `/api/mcp` bearer block and legacy dev workflow;
  `test_coexistence.py:111-113` asserts both README phrases — update together.
- `src/utils/functions.ts:66 getItemUrl()` → `/api/s3/items/:id`; no live consumers found —
  delete with legacy subtree.

## 4. Python code that fails loudly if legacy disappears first (ordering risk)

Most legacy readers degrade gracefully (`to_regclass` guards, try/except in
`model_governance._legacy_model`), but these do NOT:
- `cli.py` `inventory-legacy-mcp`/`migrate-legacy-*` apply paths that execute direct
  `public.*` SQL after the existence probe — safe only while probes run first; after table drop
  some sub-reports will raise instead of reporting empty. Audit every legacy SQL site if the CLI
  stays; delete the readers if it does not (recommended).
- `backend/tests/integration/test_postgres_cutover.py` seeds `public.*` fixtures (7 direct
  references) — fails on a clean DB without legacy schema; must be removed together with the
  cleanup migration, and `conftest.py` count (48) adjusted in the same change.
- Identity runtime writes `public."user"` guarded by `to_regclass` — degrades silently, but
  leaves orphan `ima.legacy_identity_projection` rows stuck in `pending` if the write is half-
  removed; delete the whole projection block atomically.

## 5. Tests/configs that pin the CURRENT coexistence state (flip-list)

| File | Pins | Action |
|---|---|---|
| `backend/tests/contract/test_coexistence.py` | Caddy legacy catch-all, `/api/mcp` exclusion, runbook phrases, drill internals, README `/api/mcp` | Rewrite as post-deletion invariants (terminal routing, no legacy upstream) |
| `backend/tests/contract/test_knowledge_coexistence.py` | Existence of `src-server/kb/ops.ts`, `kb.ts`, `kb/ingest.ts`, `kb/retrieve.ts`, `s3.ts`, `mcp.ts` | Delete (keep the "migrated client has no Zero/Bun fallback" tests — they stay true) |
| `backend/tests/contract/test_search_coexistence.py` | Existence of `src-server/kb/retrieve.ts`, `src/views/ChatView.vue` | Delete/rewrite |
| `scripts/caddy-routing-drill.test.ts` | current+rollback phase shape | Rewrite with drill |
| `.trellis/spec/backend/identity-platform-contracts.md` | "Python writes only the legacy public.user/userData projection, Bun keeps reading it" | Spec update via update-spec after deletion |
| `.trellis/spec/backend/workspace-authorization-contracts.md:58-62` | legacy fallback read path for bridge | Spec update |
| `.trellis/spec/backend/legacy-migration-cutover-contracts.md` | migrate-legacy CLI behavior incl. "reported even when legacy tables absent" | Keep/reduce per CLI decision |

## 6. Deployment/CI risks

- `.github/workflows/docker-image.yml` + `docker-image-staging.yml` build `Dockerfile.server`
  (`krytro/nyaai-server`) on every release — deleting the Dockerfile without updating workflows
  breaks release CI. Conversely, NO workflow builds `Dockerfile.backend`; the Python images are
  compose-built only — release-publishing gap to fix in this task.
- `docker-compose.example.yml` `web` service still carries bridge env (`IMA_BRIDGE_TOKEN`,
  `PYTHON_API_INTERNAL_URL`, `IMA_BRIDGE_TIMEOUT_MS`) that Caddy never consumes — residue.
- Compose `db` init creates the `zero` database; removing it changes fresh-install behavior
  (harmless, but the cleanup migration runs against `app` only — `zero` DB removal is a
  deployment-level step).
- Pinned Postgres-test count (`conftest.py:24` = 48) turns any test deletion into a hard gate
  failure until updated.

## 7. Environment/local-state residue

- Untracked local `.env` carries `BETTER_AUTH_SECRET`, `SEARXNG_URL`, `ZERO_CVR_DB` and legacy
  `DATABASE_URL`/`S3_*` — gitignored, but `.env.example` (tracked) needs the legacy keys
  removed or fresh-checkout docs stay misleading.
- Stray empty dir `Caddyfile;C/` at repo root (drill/shell artifact) — remove.
- `quasar.config.ts.temporary.compiled.*.mjs` root artifacts (gitignored) — clean locally.
- `dist/`, `test-results/` local outputs (gitignored).

## 8. Behavioral risks of the deletion itself

- Removing legacy connector UI from `WorkspaceConnectors` while operators still hold legacy
  keys: the sunset gate (pending==0, reissue/revoke decisions) MUST be evidenced first —
  otherwise users lose visibility of still-active keys.
- Chat removal: no conversation migration exists (accepted counts-only archive). Deep links
  `/chat/:id` will 404 post-deletion; decide redirect (to `/`) vs NotFound.
- `InvitationLayout` rewiring: accept-invite currently goes through Zero mutators; the Python
  invitation acceptance endpoint exists (identity-client `AcceptTokenRequest`) — verify parity
  (role, perfs) during rewiring.
- i18n: legacy keys remain in `i18n/zh-CN.json`/`zh-TW.json`; harmless but flagged by parent
  plan 13.1 (localization keys removal) — optional sweep.
- `bun.lock` (committed) must be regenerated after dependency removals or
  `bun install --frozen-lockfile` gates fail inconsistently.

## Caveats / Not Found

- No backend module imports TS/legacy at runtime (Python↔legacy coupling is SQL-only).
- No references to legacy found in `tests/e2e/*` (suites are Python-stack only).
- `src/utils/open-created-entity.ts`(+test) serves legacy creation flows; no migrated consumer
  found — delete both.
