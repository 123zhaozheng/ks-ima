# Research: Legacy Code Inventory (Bun Server, Routing, Wiring, Tests)

- **Query**: Where is the legacy Bun server, which routes does Caddy still send to it, what env/compose wiring exists, which legacy tests exist?
- **Scope**: internal
- **Date**: 2026-08-28

## 1. Legacy Bun server layout (`src-server/`)

Entry: `src-server/index.ts:18-32` — Hono app with `basePath('/api')`, calls `seed()` and `initJobs()` at
import time, `maxRequestBodySize` 5G. Registered sub-routers:

| Mount | File | Purpose (post-coexistence) |
|---|---|---|
| `/api/zero` | `src-server/zero/routes.ts` | Zero query/mutate endpoint (edge now returns 403, see §2) |
| `/api/s3` | `src-server/s3.ts:40-151` | Legacy file upload `PUT /items/:id` (streams to S3, inserts `blob`, attaches `item.blobId`, `enqueueParse`) and presigned download `GET /items/:id[|/url]` |
| `/api/v1` | `src-server/ai.ts:7-82` | `POST /chat/completions`, `POST /chat/titles` model proxy (legacy chat view) |
| `/api/search` | `src-server/search.ts:14` | Legacy workspace search `POST /` |
| `/api/kb` | `src-server/kb.ts:39-229` | `POST /search /ask /reparse /reindex /list-dir /tree /get-note /get-file /create-note /update-note /mkdir /set-tags /move /delete /upload` |
| `/api/mcp` | `src-server/mcp.ts:95-107` | Legacy Streamable HTTP MCP for `ima_...` connector bearer keys (deliberately retained; NOT an OAuth resource) |
| `/api/connectors` | `src-server/connectors.ts:18-135` | List/create/delete/rotate legacy connector keys |

Supporting modules: `src-server/kb/ops.ts` (348 lines, shared kb operations; writes go through
`src-shared/mutators` into legacy `public.*` tables, `ops.ts:4,204-345`), `src-server/kb/ingest.ts`,
`kb/parse-file.ts`, `kb/retrieve.ts`, `kb/embed.ts`, `kb/rerank.ts`, `kb/chunk-text.ts`, `kb/settings.ts`,
`src-server/mcp-dispatch.ts` (stateless Streamable HTTP transport), `src-server/utils/permissions.ts`
(ACL enforcement, now bridge-first), `src-server/utils/db.ts`, `src-server/utils/config.ts`,
`src-server/utils/rate-limiter.ts`, `src-server/schema/*` (Drizzle schema; `legacy-user.ts` is now a
read-only projection), `src-server/zero/db.ts|mutators.ts|routes.ts`.

Better Auth has been fully removed from `src-server` (no `better-auth` references remain); the only session
adapter is `src-server/auth/session.ts:19-41`, which calls the Python bridge.

### Legacy write surface still live (matters for write freeze)

- `/api/kb` mutations: `create-note`, `update-note`, `mkdir`, `set-tags`, `move`, `delete`, `upload`,
  `reparse`, `reindex` (`src-server/kb.ts`), all writing `public.entity/page/item/blob/chunk` via shared
  mutators (`src-server/kb/ops.ts:204-345`).
- `/api/s3 PUT /items/:id` — creates blob bytes + rows (`src-server/s3.ts:41-131`).
- `/api/mcp` write tools with `readwrite` connector keys (`src-server/kb/ops.ts:300-348`, tool set in
  `src-server/mcp-dispatch.ts`).
- `/api/connectors` create/rotate/delete (`src-server/connectors.ts:48-135`).
- `/api/v1/chat/completions` persists nothing server-side itself, but legacy chat messages historically flow
  through Zero mutators; `/api/zero/*` is already 403 at the edge (§2), which is the existing write-block
  precedent for the Zero path.
- Legacy cron jobs start in-process: `cleanBlobs` hourly at :20 (`0 0 * * * *` crontab field order per croner:
  every hour), `parseKb` every 15s (`src-server/jobs/index.ts:18-24`). **`cleanBlobs` deletes S3 objects for
  `refCount=0` rows** (`src-server/jobs/clean-blobs.ts`) — a live hazard to legacy blobs during/after
  migration until freeze; parseKb keeps writing parse state into `entity.conf`/`chunk`.

## 2. Caddy routing state (`Caddyfile`, root of repo)

Two listeners `:8080` (user PWA) and `:8081` (admin), each with identical Python-first matcher order:

- Python (`{$PYTHON_API_URL}`): `/health/*`, `/api/v1/system/*`,
  `/api/v1/auth/* /api/v1/account/* /api/v1/admin/*`,
  `/mcp /.well-known/oauth-protected-resource[...] /.well-known/oauth-authorization-server /oauth/authorize[...] /oauth/token /oauth/revoke /api/v1/oauth/*`,
  `/api/v1/workspaces[...] /api/v1/workspace-invitations[...] /api/v1/folders/* /api/v1/documents/*` plus
  storage matchers (`upload-ticket`, `/documents/*/file[...]`, `/documents/*/ingestion`)
  (`Caddyfile:10-37`, mirrored `:72-99`).
- Explicit 404 for `/api/v1/internal/*` (`Caddyfile:40-43,101-104`).
- Explicit 403 for `/api/admin* /api/zero*` on :8080 (`Caddyfile:45-50`) and `/api/zero*` on :8081
  (`Caddyfile:106-108`). **Zero query/mutate is already blocked at the edge.**
- Legacy catch-all: `@api path /api/*` → `reverse_proxy {$SERVER_URL}` (`Caddyfile:52-55,110-113`).
  Everything not matched above still goes to Bun: **`/api/mcp`, `/api/s3/*`, `/api/v1/chat/*`, `/api/search`,
  `/api/kb/*`, `/api/connectors/*`**.
- `zero-cache` websocket still routed (`Caddyfile:57-59,115-117`) though its upstream mutate/query endpoints
  are 403.
- Matcher ordering (Python matchers before `@api`, internal-404 before `@api`) is pinned by contract test
  `backend/tests/contract/test_coexistence.py:5-33`; `/api/mcp` must NOT appear in the Python MCP matcher
  (`:26-28`).

## 3. Env / compose wiring

`docker-compose.example.yml`:

- `db` (custom Postgres image with zhparser, `Dockerfile.postgres`; init creates `app` + `zero` DBs and
  `zhparser` extension, `:179-187`), `wal_level=logical` for Zero (`:9`).
- `server` = legacy Bun image `krytro/nyaai-server:latest` (`:19-41`) with `DATABASE_URL`, `S3_*` legacy
  storage env, **`PYTHON_API_INTERNAL_URL: http://ima-api:8000`** and **`IMA_BRIDGE_TOKEN`** — the legacy
  server cannot authenticate or authorize without the Python bridge.
- `ima-api` / `ima-worker` / `ima-migrate` (Alembic pre-deploy job, `:101-115`) / `ima-integration`
  (`:117-133`). Python env: `IMA_DATABASE_URL` (same physical `app` database as legacy), `IMA_TASK_SCHEMA=ima_jobs`,
  `IMA_STORAGE_*`, `IMA_BRIDGE_TOKEN`, `IMA_MODEL_KEY_RING`/`IMA_MODEL_CURRENT_KEY_VERSION`/
  `IMA_MODEL_FINGERPRINT_KEY`, model egress allowlists (`:43-99`).
- `web` (Caddy + both frontends) with `SERVER_URL`, `ZERO_CACHE_URL`, `PYTHON_API_URL` (`:135-150`).
- `zero-cache` (`:152-173`) with upstream/mutate URLs into Bun and cookie forwarding.
- Dev-only: `dev-db/docker-compose.yml`, `scripts/dev-pg.ts`, `.env`/`.env.example` (legacy `DATABASE_URL`,
  `ZERO_*`, `S3_*` + bridge vars).

Bridge endpoints (Python-internal, never public):
- `POST /api/v1/internal/session/introspect` — fail-closed cookie-session introspection,
  `backend/src/ima/api/internal/session_bridge.py:16-26`; consumed by `src-server/auth/session.ts:19-41`.
- `POST /api/v1/internal/authorization/{decide,batch,member}` — fail-closed ACL bridge,
  `backend/src/ima/api/internal/authorization_bridge.py`; consumed by `src-server/utils/permissions.ts:46,124-155,192-223`
  (bridge unavailable/malformed → deny; legacy fallback read path exists per spec
  `.trellis/spec/backend/workspace-authorization-contracts.md:58-62`).
- Model governance bridge: `internal_router` at `/api/v1/internal/model-governance/*` inside
  `backend/src/ima/api/v1/model_governance.py:519+` (managed chat/embedding/rerank execution incl.
  `execute/legacy/chat`), mounted in `backend/src/ima/api/app.py:255`; consumed by
  `src-server/kb/model-governance.ts:18`. Legacy RAG/chat model calls therefore already execute through
  Python model governance.

Consequence: **the legacy Bun server is already a thin reader/writer dependent on Python for identity and
authorization.** Any rollback that removes Python also kills legacy browser sessions (legacy `session` rows
were deleted by identity migration).

## 4. Legacy tests and drills still in the repo

Bun tests (`bun test`):
- `src-server/auth/session.test.ts` — bridge session adapter behavior.
- `src-server/kb/model-governance.test.ts`, `src-server/kb/parse-file.test.ts`.
- `src-shared/utils/acl.test.ts` — legacy ACL semantics.
- `src/utils/identity-client.test.ts`, `src/utils/mcp-config.test.ts`, `src/utils/open-created-entity.test.ts`.
- `scripts/caddy-routing-drill.test.ts` — routing drill contract (see precedents file).

Vitest (`bun run test:unit`): `tests/components/*.vitest.ts` (14 files, incl. WorkspaceConnectors, OAuthConsent,
KnowledgeTree, GroundedAskPage) — configured in `vitest.config.ts`.
Playwright (`bun run test:e2e`): `tests/e2e/{identity,knowledge-tree,grounded-ask,model-governance,oauth-consent}.pw.ts`
against the Python stack (`playwright.config.ts`, seed via `backend/scripts/seed_identity_e2e.py`).
Scripts: `scripts/permission-smoke.ts`, `scripts/mcp-handshake.ts`, `scripts/mcp-live.ts`,
`scripts/caddy-routing-drill.ts`, `scripts/dev-pg.ts` (`package.json` scripts block).

Python-side coexistence tests that pin legacy retention (they FAIL if legacy files disappear before the
deletion task): `backend/tests/contract/test_coexistence.py`, `test_knowledge_coexistence.py`,
`test_search_coexistence.py` (assert `src-server/kb/retrieve.ts`, `src/views/ChatView.vue` still exist,
legacy `/api/mcp` semantics preserved, etc.).

## 5. Frontend state relevant to cutover

- Vue app still at repo-root `src/` (the planned `frontend/` holds only `frontend/generated/` OpenAPI output).
- Migrated slices use generated clients: `src/api/ima-client.ts`, `knowledge-client.ts`, `grounded-client.ts`.
- Legacy residue still compiled: `src-shared/{schema.gen.ts,mutators.ts,queries.ts,table-permission.ts,kb-settings.ts}`,
  legacy views `src/views/{ChatView,EntityView,ItemView,...}.vue`, Zero components (145 Zero call sites per
  parent research). Chat (`ChatView.vue`) is the named retained legacy consumer
  (`backend/tests/contract/test_search_coexistence.py:4-13`).
- `quasar.config.ts` still proxies `/zero-cache` in dev (`quasar.config.ts:105-107`).

## Caveats / Not Found

- `src-server` is not under `backend/`; deletion of it belongs to the follow-up
  `08-24-legacy-deletion-release` task, not this cutover task (`.trellis/tasks/08-24-legacy-deletion-release/prd.md`).
- No runtime feature flag in Bun to disable writes; write-freeze must be enforced at Caddy/deployment level
  or by stopping the service (see design-input file).
