# Research: Gate Inventory — Release, Security, Deployment, Browser Gates Post-Deletion

- **Query**: What exactly must pass after deletion; which deployment artifacts must be updated?
- **Scope**: internal
- **Date**: 2026-08-29

## 1. Backend quality gates (run from `backend/`)

Pinned by parent plan §13.3 (`.trellis/tasks/08-24-python-intranet-ima-migration/implement.md:617-663`)
and sibling-task practice:

```powershell
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima          # mypy config: strict, files=["src/ima"] (pyproject.toml)
uv run pytest                # unit + contract suites
$env:IMA_REQUIRE_POSTGRES = "1"; $env:IMA_TEST_DATABASE_URL = "postgresql+asyncpg://..."; uv run pytest -m postgres
uv run alembic check         # schema/model sync gate
uv run ima contract export --check   # deterministic OpenAPI (backend/scripts/export_openapi.py, check_contract.py)
```

Forced-Postgres gate details: `backend/tests/conftest.py:17-29` exits 2 unless exactly **48**
postgres-marked tests are collected when `IMA_REQUIRE_POSTGRES=1`. Deleting cutover/rehearsal or
coexistence Postgres tests REQUIRES updating this count in the same change.

Integration rehearsal service: `docker-compose.example.yml` `ima-integration` runs
`ima migrate && pytest -s -m postgres` against a real Postgres — keep and re-verify after deletion.

## 2. Frontend gates

```powershell
bun install --frozen-lockfile
bun run lint                 # eslint over ./src*/** (includes src-pwa after src-server removal)
bun run test                 # bun test: drill + remaining .test.ts files
bun run test:unit            # vitest component suite (14 files)
bun run build:front          # PWA build (also runs vue-tsc checker + eslint via vite-plugin-checker)
bun run build:admin          # SPA admin build
bun run test:e2e             # Playwright against Python stack
bun run test:caddy-routing   # routing drill (docker + pinned caddy:2.10.2-alpine)
```

DISCREPANCY: parent plan lists `bun run typecheck` and `bun run build`, but package.json has
neither. Type checking today happens inside builds via `vite-plugin-checker` (vueTsc: true,
quasar.config.ts:78-84). Options: add explicit `"typecheck": "vue-tsc --noEmit"` script, or
accept builds as the typecheck gate. Flag for PRD.

## 3. E2E/browser gate pipeline (`playwright.config.ts`, `tests/e2e/`)

`global-setup.ts`: `docker compose -p <proj> -f backend/tests/integration/identity-compose.yml up`
→ `uv run ima migrate` → `seed_identity_e2e.py` → `register-mcp-client` x2 → uvicorn
`ima.main:app` → `bun run build:front` + `build:admin` → static-server serves `dist/pwa` and
`dist/spa` proxying `/api/*` + OAuth routes to Python. Suites: identity, knowledge-tree,
grounded-ask, model-governance, oauth-consent; projects chromium desktop + Pixel 7 mobile.
Parent §13.3 additionally wants desktop/mobile screenshot review (no overlap/overflow) and all
PRD acceptance scenarios incl. restricted-folder non-disclosure.

Browser gate implication: after frontend legacy deletion, BOTH Quasar builds must still compile
and the five Playwright suites must pass without any Bun/Zero service running.

## 4. Caddy routing drill gate (`scripts/caddy-routing-drill.ts`)

Current phases: `current | cutover | pre_sunset_rollback | restored`; pins
`CADDY_IMAGE='caddy:2.10.2-alpine'`, `PYTHON_PATHS`, `BUN_PATHS=['/api/mcp','/api/legacy-check']`,
`ZERO_PATHS=['/zero-cache/replica']`, `INTERNAL_PATH`. Post-deletion the drill and its test must
be rewritten to pin the NEW terminal routing (no Bun upstream, no zero-cache, `/api/mcp` 410 or
absent, `/api/*` either Python or 404/410) — the `cutover`/`pre_sunset_rollback` derivation
phases become obsolete or invert. Contract tests `test_coexistence.py` assert drill internals
(`buildCutoverConfig`, `'410'`, `'terminal'`, `pre_sunset_rollback`) — update in the same change.

## 5. Deployment artifacts that MUST change

| Artifact | Change |
|---|---|
| `Caddyfile` | Remove `@api → {$SERVER_URL}` catch-all, `@forbidden /api/admin* /api/zero*`, `/zero-cache*` blocks on both listeners; decide `/api/mcp` terminal status (410 per cutover JSON precedent) and residual `/api/*` policy (404/410 or Python); remove `SERVER_URL`/`ZERO_CACHE_URL` env usage |
| `docker-compose.example.yml` | Remove `server`, `zero-cache`, `zero-cache-data` volume, `CREATE DATABASE zero`, `wal_level=logical`, `SERVER_URL`/`ZERO_CACHE_URL`/bridge env on `web` |
| `Dockerfile.server` | Delete |
| `.github/workflows/docker-image.yml`, `docker-image-staging.yml` | Remove `nyaai-server` build/push steps; today NOTHING builds/pushes `Dockerfile.backend` images — add `ima-api`/`ima-worker` image publishing to make the release deployable |
| `.env.example` | Remove legacy keys (see dependency-audit §4) |
| `README.md` | Remove coexistence connector block (`/api/mcp` bearer), legacy dev workflow (`zero-cache-dev`, `bun dev:server`, `bun dev:db-up`); document Python-only dev/deploy; contract test asserts README phrases (`preferred protected resource .../mcp` keep; `"url": ".../api/mcp"` must go) |
| `docs/oauth-mcp-coexistence-runbook.md`, `docs/legacy-cutover-runbook.md` | Keep as historical evidence; contract-test pins on their text must be re-scoped (or documents amended with sunset closure notes) |
| `drizzle.config.ts`, `drizzle-zero.config.ts`, `drizzle/` | Delete |
| `dev-db/`, `scripts/dev-pg.ts` | Delete or repoint (decision) |

## 6. Security gates (parent §13.3 + design §17)

- SBOM / dependency / image vulnerability review (lockfiles pinned; base image digests).
- No public egress in a network-restricted test (model gateway allowlists `IMA_MODEL_ALLOWED_*`).
- Non-root containers (verify `Dockerfile.backend` USER), readiness/worker-lag checks.
- TLS/OAuth metadata readiness (issuer must be HTTPS-capable; intranet HTTP caveat in parent
  risks table — document deployment requirement).
- Secret-safety regression: no raw credentials in logs/errors/audit/metrics (existing suites).
- Dead code + unused production dependencies removed (this task's residue-search §13.2 list).
- Removal of internal bridge endpoints shrinks attack surface; keep the Caddy
  `/api/v1/internal/*` public-404 rule as defense in depth (still asserted by contract tests).

## 7. Residue-search gate (parent §13.2)

Case-insensitive searches that must come back clean (or documented target-domain reason):
`@rocicorp/zero, zero-cache, ZERO_, src-server, hono, drizzle-zero, planPrice, planId, payment,
stripe, wxpay, order, quotaUsed, resetQuota, translation, channel, mcpPlugin, pubRoot, pagePatch,
tiptap, searxng, r.jina.ai, gread, createProvider, provider-options, chat/completions` — plus
this repo's additions: `/api/mcp` (only historical docs allowed), `SERVER_URL`,
`ZERO_REPLICA_FILE`, `BETTER_AUTH`, `krytro/nyaai-server`.

## 8. Discrepancies between parent plan and repo reality

- Parent §13.3 `docker compose -f deploy/compose/compose.yml {config,build,up}` — repo has no
  `deploy/` dir; the live artifact is `docker-compose.example.yml`. Gate should be rewritten to
  the real file (or the file promoted to `deploy/compose/compose.yml` as part of this task).
- Parent `uv run ima migrate-legacy verify --report <artifact>` — actual CLI verbs are
  per-slice (`migrate-legacy-identity verify`, etc.) plus the cutover family
  (`migrate-legacy report-all|blob-verify|reconcile-report|reingest ...`). After deletion these
  legacy-reading commands may be removed (decision in python-db inventory §2e), so the release
  gate should reference them only as PRE-deletion acceptance evidence.
- Migration DB credential separation and `alembic check` remain valid gates.

## Caveats / Not Found

- No CI workflow runs tests/lint today (only image builds); release gates are operator-run
  commands. Adding CI is an optional hardening item, not currently wired.
