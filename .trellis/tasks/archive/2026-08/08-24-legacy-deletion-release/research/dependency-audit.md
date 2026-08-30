# Research: Dependency Audit — npm/bun deps, Python deps, package.json scripts

- **Query**: Which deps become unused after deletion; which scripts must be removed or repointed?
- **Scope**: internal
- **Date**: 2026-08-29

## 1. npm dependencies removable after deletion (root `package.json`)

Verified by import grep across `src/`, `src-server/`, `src-shared/`, `src-admin`, `scripts/`,
`tests/` (consumers all inside the deletion subtree unless noted):

### Runtime `dependencies`

| Package | Sole consumers | Verdict |
|---|---|---|
| `@rocicorp/zero` | zero-session, composables/zero/*, legacy components | REMOVE |
| `drizzle-orm` | src-server only (+ scripts/mcp-live) | REMOVE |
| `drizzle-zero` | drizzle-zero.config.ts, generate:zero | REMOVE |
| `drizzle-zod` | src-server schema validation | REMOVE |
| `hono` | src-server + `src/utils/hc.ts` | REMOVE (after hc consumers rewired/deleted) |
| `@hono/zod-validator` | src-server | REMOVE |
| `croner` | src-server/jobs | REMOVE |
| `aws4fetch` | src-server/utils/s3.ts | REMOVE |
| `postgres` | scripts/permission-smoke.ts only | REMOVE |
| `nodemailer` | **no consumers anywhere** (already dead) | REMOVE now |
| `ai` | src/utils/chat-tools.ts (types) | REMOVE |
| `@ai-sdk/openai-compatible` | no consumers found (already dead) | REMOVE now |
| `@ai-sdk/provider-utils` | chat-tools.ts (types) | REMOVE |
| `ollama-ai-provider-v2` | no consumers found (already dead) | REMOVE now |
| `@modelcontextprotocol/sdk` | src-server/mcp-dispatch, scripts/mcp-handshake, scripts/mcp-live, PluginContextBtn.vue, src-shared/utils/types.ts | REMOVE (decision: only if no TS-SDK MCP interop test is kept; Python `mcp` SDK covers the server side) |
| `tokenx` | **no consumers** (already dead) | REMOVE now |
| `ky` | services/upload.ts, utils/blob-cache.ts (legacy) | REMOVE |
| `idb` | utils/blob-cache.ts | REMOVE |
| `liquidjs` | utils/template-engine.ts (legacy chat) | REMOVE |
| `hash-wasm` | utils/hash.ts, src-shared/utils/functions.ts (legacy client-side upload hashing) | REMOVE |
| `fflate` | utils/file-parse.ts (MessageInput/ParseFilesDialog) + src-server parse-file | REMOVE if migrated document page does not import it (verify at build; KnowledgeDocumentPage import scan showed no use) |
| `zod` | json-query.ts, right-entity.ts, builtin-plugins/workspace.ts (all legacy subtree) | LIKELY REMOVE — verify `bun run typecheck` after subtree deletion |

### `devDependencies`

| Package | Consumers | Verdict |
|---|---|---|
| `drizzle-kit` | drizzle.config.ts, generate:zero | REMOVE |
| `embedded-postgres`, `@embedded-postgres/windows-x64` | scripts/dev-pg.ts only | REMOVE with dev-pg (also drop both from `trustedDependencies`) |
| `@types/pg` | none (`pg` never imported; smoke test uses `postgres`) | REMOVE now |
| `@types/nodemailer` | none | REMOVE with nodemailer |
| `@types/bun` | bun scripts (drill, static-server) | KEEP |
| `@playwright/test`, vitest stack, happy-dom, @vue/test-utils | live test suites | KEEP |
| `otpauth` | tests/e2e/identity.pw.ts, src/pages/AccountSecurity.vue, identity-client.ts | KEEP |
| `openapi-typescript` | generate:api | KEEP |
| `neostandard` | eslint.config.js | KEEP |

KEEP list (migrated frontend still uses): vue, vue-router, pinia, @tanstack/vue-query, quasar,
@quasar/extras, @quasar/app-vite, @vueuse/core, date-fns, i18n-pro, dotenv (quasar.config),
@material/material-color-utilities, @vue-office/{docx,excel,pdf}, pdfjs-dist, mammoth,
xlsx-republish, katex, lowlight, prism-code-editor, marked, markdown-it-link-attributes,
md-editor-v3, mark.js, workbox-*, @unocss/preset-rem-to-px, unocss, vite plugins, vue-tsc,
typescript, sonda, baseline-browser-mapping.

After removal: regenerate `bun.lock` (`bun install`), and the e2e/build gates prove the lockfile.

## 2. Python dependencies (`backend/pyproject.toml`)

No Python dependency exists solely for legacy. Notes:
- `psycopg[binary]` — imported only by `backend/src/ima/cli.py` (sync conn for the migration
  commands, bootstrap-admin, register-mcp-client, rotate-model-secrets). If legacy
  `migrate-legacy-*` readers are deleted but bootstrap/register/rotate keep psycopg, the dep
  stays. Audit at implementation: keep unless every remaining CLI path is asyncpg.
- `mcp==2.1.1` — Python MCP server (canonical `/mcp`) — KEEP.
- Everything else (alembic, asyncpg, boto3, argon2, aiosmtplib, cryptography, fastapi, httpx,
  procrastinate, pydantic-settings, python-json-logger, sqlalchemy, uvicorn, pyotp, pypdf,
  python-docx, openpyxl) serves the live backend — KEEP.

## 3. package.json scripts

| Script | Verdict |
|---|---|
| `lint` | KEEP — glob `./src*/**` still valid after src-server/src-shared removal |
| `test` (`bun test`) | KEEP — suite shrinks (src-server/src-shared/legacy src tests disappear); remaining: caddy-routing-drill.test.ts, identity-client.test.ts, mcp-config.test.ts (updated), open-created-entity.test.ts (verify), tests/components/*.test.ts |
| `test:unit` (vitest) | KEEP |
| `test:all` | KEEP |
| `test:permissions` | REMOVE (legacy public-table smoke) |
| `test:mcp` | REMOVE (legacy dispatch handshake) |
| `test:mcp-live` | REMOVE (legacy connector live test) |
| `test:caddy-routing` | KEEP — drill must be updated for post-deletion Caddyfile (release-gates §4) |
| `dev:front` / `dev:admin` | KEEP |
| `dev:server` | REMOVE |
| `build:front` / `build:admin` | KEEP (e2e browser gate builds both) |
| `build:server` | REMOVE |
| `generate:zero` | REMOVE |
| `generate:api` | KEEP (OpenAPI client generation) |
| `dev:pg` | REMOVE with script |
| `dev:db-up` / `dev:db-down` / `dev:db-rm` | REMOVE (dev-db compose) or repoint to a Python-dev compose — decision |
| `test:e2e` (playwright) | KEEP |
| `t` (i18n tooling) | KEEP |

Also remove/repoint: `engines` block is npm/yarn flavored (harmless), `trustedDependencies`
drop the embedded-postgres entry if dev-pg goes.

## 4. Environment keys to retire

Tracked `.env.example` keys to remove: `DATABASE_URL` (legacy conninfo; Python uses
`IMA_DATABASE_URL`), `ZERO_*` (8 keys), `SERVER_URL`, `ZERO_CACHE_URL`, `S3_*` (5 keys —
legacy storage; Python uses `IMA_STORAGE_*`). Keys to keep: `SITE_NAME`, `FRONT_URL`,
`ADMIN_URL` (check consumers — quasar config reads env; FRONT/ADMIN URL may be legacy-only),
`PYTHON_API_INTERNAL_URL` (retire with bridge), `IMA_BRIDGE_TOKEN`, `IMA_BRIDGE_TIMEOUT_MS`
(retire with bridge), all `IMA_*` runtime keys stay. Untracked local `.env` additionally carries
`BETTER_AUTH_SECRET`, `ZERO_CVR_DB`, `SEARXNG_URL` — pure residue (file is gitignored; update
documentation/templates only).

## Caveats / Not Found

- `bun.lock` is committed (633KB) — dependency removals must regenerate it in-branch.
- No Python package imports found for legacy-only purposes (the legacy surface was TS).
