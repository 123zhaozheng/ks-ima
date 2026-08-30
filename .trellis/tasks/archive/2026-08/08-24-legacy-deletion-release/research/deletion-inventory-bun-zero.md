# Research: Deletion Inventory — Bun Server, Zero, Shared Legacy, Dev/Deploy Tooling

- **Query**: Every legacy Bun/Zero artifact to remove, with exact paths and references.
- **Scope**: internal
- **Date**: 2026-08-29

## 1. Legacy Bun server — `src-server/` (39 files, entire directory deletable)

Entry `src-server/index.ts` (Hono app, basePath `/api`). Full tree:

```
src-server/index.ts, ai.ts, connectors.ts, kb.ts, mcp.ts, mcp-dispatch.ts, s3.ts, search.ts
src-server/auth/session.ts (+ session.test.ts)
src-server/jobs/{index,clean-blobs,parse-kb}.ts
src-server/kb/{chunk-text,embed,ingest,model-governance,model-governance.test,ops,parse-file,
               parse-file.test,rerank,retrieve,settings}.ts
src-server/schema/{index,legacy-user,relations,schema}.ts
src-server/utils/{config,db,functions,permissions,rate-limiter,s3,seed,settings}.ts
src-server/zero/{db,mutators,routes}.ts
```

References into `src-server`:
- `src/utils/hc.ts` — `hc<AppType>('/')` typed client imports `app/src-server/index` (compile-time
  coupling; consumers listed in risks file).
- `scripts/mcp-handshake.ts` (imports `src-server/mcp-dispatch`), `scripts/mcp-live.ts` (imports
  `src-server/schema`, `src-server/utils/db`, `src-server/utils/permissions`).
- `drizzle.config.ts` and `drizzle-zero.config.ts` point at `./src-server/schema/index.ts`.
- `package.json` scripts `dev:server`, `build:server`, `generate:zero`.
- `Dockerfile.server` builds `bun run build:server` and copies `./drizzle`.
- `.github/workflows/docker-image.yml` + `docker-image-staging.yml` build/push `Dockerfile.server`
  as `krytro/nyaai-server` (both release and staging workflows).
- `docker-compose.example.yml` service `server` (image `krytro/nyaai-server:latest`) and
  `zero-cache` (`ZERO_QUERY_URL/MUTATE_URL` → `http://server:3000/api/zero/*`).
- Python-side coexistence contract tests assert several `src-server` files still exist (see
  `risks-live-references.md` §2) — must be deleted/rewritten in the same change.

Bun tests inside (`bun test` picks them up): `src-server/auth/session.test.ts`,
`src-server/kb/model-governance.test.ts`, `src-server/kb/parse-file.test.ts`.

## 2. Zero client/server residue

- `src-server/zero/{db,mutators,routes}.ts` (query/mutate endpoints; already 403 at edge).
- `zero-cache` compose service + `zero-cache-data` volume + `zero` database creation in
  `docker-compose.example.yml` init config (`CREATE DATABASE zero;`).
- `drizzle-zero.config.ts` (root) — Zero schema generation config; enumerates every legacy table
  incl. commercial ones (plan, planPrice, order, usage, channel, translation, mcpPlugin...).
- `src-shared/schema.gen.ts` — generated Zero schema.
- Frontend Zero runtime: `src/utils/zero-session.ts`, `src/composables/zero/{query,view}.ts`,
  `src/utils/config.ts` (`ZERO_CACHE_URL`), `quasar.config.ts` dev proxy `/zero-cache`
  (lines 105-109). Full consumer list in `deletion-inventory-frontend.md`.
- Env keys: `ZERO_CACHE_URL`, `ZERO_UPSTREAM_DB`, `ZERO_CHANGE_DB`, `ZERO_CVR_DB` (in local `.env`),
  `ZERO_MUTATE_URL`, `ZERO_QUERY_URL`, `ZERO_*_FORWARD_COOKIES`, `ZERO_REPLICA_FILE`
  (`.env.example:5,19-25`; `package.json dev:db-rm` uses `ZERO_REPLICA_FILE`).
- `docker-compose.example.yml:9` `wal_level=logical` exists solely for Zero replication (dev-db
  compose and `scripts/dev-pg.ts` also set logical replication flags for Zero).
- Caddyfile: `handle_path /zero-cache*` blocks on both listeners (lines 57-59, 115-117) and the
  `@forbidden /api/zero*` 403 blocks (lines 45-50, 106-108).

## 3. `src-shared/` (15 files)

Zero-bound (delete with Zero): `schema.gen.ts`, `mutators.ts`, `queries.ts`,
`table-permission.ts`, `kb-settings.ts`, `utils/zero-to-zod.ts`, `utils/acl.test.ts`.

Pure utilities still imported by the live frontend (must be relocated into `src/`, not blindly
deleted): `utils/id.ts` (`genId`, `randomId` — used by InvitationLayout, CodeEditor, md-props,
quote), `utils/validators.ts` (types used by AAvatar, AvatarPanel, DenseItem, EntityTypeSelect,
functions.ts...), `utils/functions.ts` (diff/pick via state-proxy, typeAvatar via defaults),
`utils/types.ts` (Context — zero-only after deletion; Plugin types — legacy chat only),
`utils/acl.ts` (only consumer: legacy EntityList), `src-shared/utils/acl.test.ts` (bun test).
Verify per-symbol usage at implementation time; relocate-then-delete is the safe order.

## 4. Legacy Drizzle DDL and runtime

- `drizzle/` — 8 legacy migration dirs (`20260317054550_public_demogoblin`,
  `20260317054607_create_trigger`, `20260317054632_insert_data`, `20260415115542_init_fts`,
  `20260428130734_cloudy_ultimates`, `20260716233024_unique_member_workspace`,
  `20260821000000_connector`, `20260824004617_entity_permissions`), each with
  `migration.sql` + `snapshot.json`. `Dockerfile.server` copies `./drizzle` into the image.
- `drizzle.config.ts` (drizzle-kit config) — delete with drizzle-kit.
- Parent plan 13.1 policy: "Squash/generated migrations only if repository release policy
  explicitly permits; otherwise add one destructive cleanup migration and keep history."
  Alembic history (`backend/migrations/versions/20260824_0001..20260828_0010`) contains no
  `public.*` references (grep verified) — a new cleanup migration can drop the legacy schema
  objects without touching history.

## 5. Legacy dev tooling and deployment residue

- `Dockerfile.server` (legacy Bun image), `Dockerfile.postgres` (custom zhparser image; keep —
  `db` service still needs zhparser for `ima` FTS), `Dockerfile.web` (keep — builds both frontends
  + Caddyfile; no legacy content except the Caddyfile it copies), `Dockerfile.backend` (keep).
- `docker-compose.example.yml`: delete `server` and `zero-cache` services, `zero-cache-data`
  volume, `CREATE DATABASE zero;` init line, `wal_level=logical` command, `SERVER_URL` and
  `ZERO_CACHE_URL` env on `web`, and the bridge env on `web` (`PYTHON_API_INTERNAL_URL`,
  `IMA_BRIDGE_TOKEN`, `IMA_BRIDGE_TIMEOUT_MS` — only used by Caddy? verify: Caddy does not use
  them; they are residue of an earlier bridge-through-Caddy design).
- `dev-db/docker-compose.yml` (legacy dev DB compose; `package.json dev:db-up/down/rm`).
- `scripts/dev-pg.ts` (embedded Postgres with Zero replication flags; `dev:pg` script).
- `.dev-pg/` local data dir (gitignored).
- `.github/workflows/docker-image.yml` and `docker-image-staging.yml`: both build
  `Dockerfile.server` (`nyaai-server`) and `Dockerfile.web`; no `Dockerfile.backend` build/push
  exists yet. Deletion task must remove the server build step and add backend image publishing
  (gate item).
- Stray artifact at repo root: `Caddyfile;C/` (empty dir, created 2026-08-29; likely a misfired
  shell redirect of the drill) — remove.
- `quasar.config.ts.temporary.compiled.*.mjs` (8 files at root) are gitignored build artifacts;
  harmless but can be cleaned.

## 6. Legacy scripts (`scripts/`)

| Script | Verdict | Why |
|---|---|---|
| `scripts/mcp-live.ts` | DELETE | Creates legacy connectors via drizzle against `public.connector`, hits `/api/mcp` |
| `scripts/mcp-handshake.ts` | DELETE | In-process handshake against `src-server/mcp-dispatch` |
| `scripts/permission-smoke.ts` | DELETE | Inserts rows into `public.user/member/entityPermission` |
| `scripts/dev-pg.ts` | DELETE (decision) | Zero-shaped dev DB; Python tests use `IMA_TEST_DATABASE_URL` + identity-compose |
| `scripts/caddy-routing-drill.ts` + `.test.ts` | KEEP, UPDATE | Post-deletion Caddyfile must be re-pinned (see release-gates.md §4) |

## Caveats / Not Found

- No other runtime references to `src-server` besides those listed (grep `from 'app/src-server` /
  `../src-server` across src/, scripts/, tests/).
- `src-pwa/` has no legacy dependencies (service worker only).
