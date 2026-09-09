# Journal - zhaozheng (Part 1)

> AI development session journal
> Started: 2026-08-24

---



## Session 1: Plan migration and establish Python foundation

**Date**: 2026-08-24
**Task**: Plan migration and establish Python foundation
**Branch**: `feat/intranet-ima`

### Summary

Indexed and analyzed the repository, created the ten-child Python intranet IMA migration plan, and completed the first child with FastAPI, Alembic, PostgreSQL-backed Procrastinate workers, pgvector plus zhparser images, exact Caddy coexistence routing, generated OpenAPI Vue client integration, executable specs, and full quality/container gates.

### Git Commits

| Hash | Message |
|------|---------|
| `329107f` | (see git log) |
| `2f9535a` | (see git log) |

### Status

[OK] **Completed**


## Session 2: Complete local identity and platform administration

**Date**: 2026-08-25
**Task**: Complete local identity and platform administration
**Branch**: `feat/intranet-ima`

### Summary

Made Python the browser identity authority; added local sessions, TOTP/recovery, platform roles/admin, resumable legacy migration, private Bun bridge, typed Vue account/admin flows, executable specs, forced PostgreSQL coverage, and 12 Playwright journeys; removed Better Auth runtime and redundant auth schema.

### Git Commits

| Hash | Message |
|------|---------|
| `6d420bf` | (see git log) |
| `dde57b9` | (see git log) |

### Status

[OK] **Completed**


## Session 3: Workspace authorization core

**Date**: 2026-08-25
**Task**: Workspace authorization core
**Branch**: `feat/intranet-ima`

### Summary

Implemented Python-owned workspaces, memberships, groups, folder hierarchy, normalized ACLs, canonical set-based policy SQL, resumable legacy authorization migration, fail-closed Bun coexistence, generated Vue administration, and exhaustive PostgreSQL/browser gates; captured executable backend/frontend contracts and archived the child task.

### Git Commits

| Hash | Message |
|------|---------|
| `6b76756` | (see git log) |
| `29ee52d` | (see git log) |

### Status

[OK] **Completed**


## Session 4: Complete central model governance

**Date**: 2026-08-25
**Task**: Complete central model governance
**Branch**: `feat/intranet-ima`

### Summary

Implemented and verified Python-owned model gateways, encrypted credentials, governed models, immutable capability profiles, workspace assignments, guarded inference, Bun target-first compatibility, admin and workspace UI, migration tooling, tests, legacy/commercial cleanup, and executable backend/frontend contracts.

### Git Commits

| Hash | Message |
|------|---------|
| `494de12` | (see git log) |
| `e68cf53` | (see git log) |

### Status

[OK] **Completed**


## Session 5: Knowledge tree and Vue API migration

**Date**: 2026-08-25
**Task**: Knowledge tree and Vue API migration
**Branch**: `feat/intranet-ima`

### Summary

Implemented Python-owned knowledge documents, Markdown versions, tags, unified trash, legacy migration commands, generated Vue API clients, Caddy cutover routes, and desktop/mobile validation. Backend and frontend gates passed; forced PostgreSQL remained blocked by missing local vector extension.

### Git Commits

| Hash | Message |
|------|---------|
| `f603b38` | (see git log) |

### Status

[OK] **Completed**


## Session 6: Object storage and durable ingestion

**Date**: 2026-08-26
**Task**: Object storage and durable ingestion
**Branch**: `feat/intranet-ima`

### Summary

Implemented private S3-compatible upload/download/preview, immutable file replacement/history, bounded parsing, durable parse/chunk/embed/cleanup work, model-governed embeddings, legacy object migration, Vue progress/retry/cancel workflows, and executable storage specs. Verified full backend/frontend/browser gates, isolated PostgreSQL 28/28, and real MinIO upload/copy cleanup.

### Git Commits

| Hash | Message |
|------|---------|
| `8886ed4` | (see git log) |

### Status

[OK] **Completed**


## Session 7: Search conversations and grounded Ask

**Date**: 2026-08-26
**Task**: Search conversations and grounded Ask
**Branch**: `feat/intranet-ima`

### Summary

Implemented workspace-isolated ACL-first FTS/pgvector retrieval, exact ANN lifecycle, optional governed rerank, owner-private conversations, grounded SSE, immutable citations, target Vue Ask, and executable search specs. Verified backend/frontend gates, isolated PostgreSQL 29/29, and desktop/mobile Playwright.

### Git Commits

| Hash | Message |
|------|---------|
| `d1e5813` | (see git log) |

### Status

[OK] **Completed**


## Session 8: OAuth service principals and MCP

**Date**: 2026-08-28
**Task**: OAuth service principals and MCP
**Branch**: `feat/intranet-ima`

### Summary

Completed and verified all seven implementation phases: pinned `mcp==2.1.1` Streamable HTTP transport mounted at canonical `/mcp` with pre-dispatch bearer authentication, OAuth 2.1 authorization-code/PKCE S256 with pepper-digested one-time codes and rotating refresh families, finite service-principal credentials with network/rate/concurrency policy, target-only tool parity through `WorkspaceService`/`KnowledgeService`/`StorageService`/`SearchService.ask_bounded`, Vue consent page and split interactive/service access management, exact Caddy route precedence with legacy `/api/mcp` retained on Bun, safe legacy inventory CLI, coexistence runbook, and a containerized pre-sunset Caddy rollback drill. No `public.connector` mutation, no FastAPI imports in application services, no legacy fallback paths.

### Verification

- Backend: ruff format/check clean, mypy clean (67 files), pytest 200 passed / 40 postgres-selected, forced PostgreSQL gate 40/40 passed with zero skips.
- Frontend: generate:api in sync, vitest 32/32, bun test 26/26, lint 0 errors, build:front/build:admin/build:server passed sequentially, test:mcp passed, test:caddy-routing drill ok (current/pre_sunset_rollback/restored).
- E2E: 42/42 passed on desktop and mobile chromium (first run flaked under concurrent container drills; clean rerun green). Live API probes confirmed RFC 9728/8414 metadata and the 401 `resource_metadata` challenge.
- Remaining environment-blocked evidence: `test:mcp-live` needs the legacy Bun stack's database (not running locally); real Cursor/Claude Desktop client matrix is deferred to the deployed public origin per the runbook.

### Git Commits

| Hash | Message |
|------|---------|
| pending | Commit performed in the later commit phase |

### Status

[OK] **Implementation complete, awaiting commit**

## Session 9: Trellis check — OAuth service principals and MCP

**Date**: 2026-08-28
**Task**: OAuth service principals and MCP
**Branch**: `feat/intranet-ima`

### Review scope

Full working-tree review of the uncommitted WIP against prd.md, design.md, implement.md, and the backend/frontend/identity spec contracts: digest-only secret persistence, audit redaction, no FastAPI in application layer, per-request target re-authorization, delegated entry points, canonical audience, one-time-code and refresh-replay atomicity, RFC 9457 and OAuth token error shapes, Caddy precedence, frontend no-secret persistence, and MCP tool delegation.

### Issues found and fixed

1. `backend/src/ima/application/storage.py` `_authorize` McpActor branch — bare `except Exception` collapsed every delegated-policy denial to a misleading 404 DOCUMENT_NOT_FOUND; now catches `WorkspaceError` and propagates status/code/detail, matching `knowledge.py`.
2. `backend/src/ima/infrastructure/oauth.py` `consume_authorization_code` — code-reuse grant revocation now also bumps `revocation_epoch`, consistent with `exchange_authorization_code_bundle`, `revoke_grant`, and refresh-replay paths.
3. `backend/src/ima/application/oauth.py` `exchange_service_credential` — `authorize_delegated_boundary` WorkspaceError leaked past `/oauth/token`'s McpAuthorizationError catch into the global RFC 9457 handler; now translated to `policy_denied` so the token endpoint returns OAuth JSON (`access_denied`).
4. `backend/src/ima/application/mcp.py` — `_execute` hardcoded a 15s boundary that killed `kb_ask` before its inner bounded 30s budget could complete; `_execute` now takes `timeout_seconds` (default 15s) and kb_ask uses 45s (30s inner < 45s outer < 60s lease TTL), consistent with `_document`.
5. `.gitignore` — Playwright `test-results/` (and report dirs) were untracked-but-not-ignored despite a stale check-ignore match; added explicit ignore entries so e2e artifacts are never committed.

### Re-run verification after fixes

- ruff format/check (edited files + full): clean; mypy (edited files + full `src/ima`): clean.
- Backend pytest: 200 passed / 40 postgres-selected (default); forced postgres gate 240 passed, 0 skipped (`IMA_REQUIRE_POSTGRES=1` against 127.0.0.1:55432).
- Frontend untouched by fixes (backend-only changes); prior green builds/lint/unit/e2e remain valid.

### Remaining risks (accepted, documented in prd/runbook)

- Catch-all `app.mount("/", mcp_transport.app)` returns empty-body 404 for unmatched paths; non-McpAuthorizationError exceptions inside the mounted auth path bypass FastAPI handlers (fail-closed 500).
- `/oauth/consent` SPA route is only served via Caddy try_files.
- External client matrix (Cursor/Claude Desktop) and `test:mcp-live` deferred to deployed public origin per runbook.

### Status

[OK] **Check complete: 5 issues fixed, all verification green, awaiting commit**


## Session 8: OAuth service principals and MCP delivered

**Date**: 2026-08-28
**Task**: OAuth service principals and MCP delivered
**Branch**: `feat/intranet-ima`

### Summary

Audited and verified all 7 phases of the OAuth/MCP plan: OAuth 2.1 authorization server, service principals, target-backed Python MCP tools, consent/access UI, and coexistence runbook. Check session fixed delegated-policy error propagation in storage authorize, revocation_epoch bump on code-reuse grant revocation, OAuth JSON error translation at the token endpoint, per-tool timeout hierarchy under lease TTL, and a gitignore gap. Full backend (ruff/mypy/pytest/forced Postgres) and frontend (unit/lint/builds/e2e 42/42) matrices green. Captured oauth-mcp-contracts spec.

### Git Commits

| Hash | Message |
|------|---------|
| `22950e0` | (see git log) |

### Status

[OK] **Completed**


## Session 10: Trellis check — legacy migration and cutover

**Date**: 2026-08-28
**Task**: Legacy migration and final cutover
**Branch**: `feat/intranet-ima`

### Review scope

Deep review of the uncommitted working tree against prd.md, design.md, implement.md, research evidence (cutover-gaps G1–G12, sibling-task standards), and backend specs: no public.* writes in new migration code, no connector-secret reconstruction/logging, redacted audit payloads, G1 read-time-only checksum normalization with the hex comparison contract intact, freeze guard (super-admin only, audit rows, RFC 9457 503 bridge refusal, migration writes pass), reconcile exit-code gating vs sibling report commands, reingest boundedness/resumability vs ingestion_jobs idempotency keys, fail-closed cutover/rollback drill derivation, and runbook contract pin.

### Issues found and fixed

1. `backend/src/ima/cli.py` `_propagate_legacy_deletions` — trashing target rows for legacy-deleted sources dropped the restore-placement anchors required by the lifecycle contract; now sets `original_folder_id=COALESCE(original_folder_id,folder_id)` on documents and `original_parent_id=COALESCE(original_parent_id,parent_id)` on folders, matching the initial importer and the trash-move reconciliation.
2. `backend/src/ima/cli.py` knowledge apply loop — a complete, fingerprint-equal checkpoint carrying `last_error='legacy_deleted'` was silently skipped, so a legacy row deleted and then recreated stayed trashed in the target forever; the skip branch now routes such checkpoints through `_reconcile_knowledge_delta`, restoring placement or recording review.

### Re-run verification after fixes

- ruff format/check: clean (cli.py reformatted); mypy src/ima: clean (73 files).
- pytest: 230 passed, 48 skipped (default); forced postgres gate: 48 passed, 0 skipped (`IMA_REQUIRE_POSTGRES=1` against 127.0.0.1:55432).
- Frontend/TS untouched by fixes; prior green `bun run test:caddy-routing`, `bun run lint`, `bun run test:unit`, `bun test` remain valid.

### Residual risks (accepted)

- Reingest readiness report aggregates ingestion jobs by version only (across generations); migrated versions are generation 1, so classification is correct for the cutover dataset.
- Identity self-service mutations through the Python API are not freeze-gated by design; the freeze guards bridge-served mutations plus workspace/knowledge/storage service writes, and the identity importer's documented public.user/userData projection remains the sole sanctioned public.* write (pre-existing, spec-pinned).
- Reconcile report can list two findings for the same knowledge source id (row-set drift + recorded review decision); deterministic and gate-safe, just verbose.

### Status

[OK] **Check complete: 2 issues fixed, all verification green, awaiting commit**


## Session 10: Legacy migration verification, freeze, and cutover tooling

**Date**: 2026-08-29
**Task**: Legacy migration verification, freeze, and cutover tooling
**Branch**: `feat/intranet-ima`

### Summary

Delivered the cutover task: G1 checksum normalization, reconciliation/delta reports with exit-code gating, blob verification, bounded resumable re-ingestion, counts-only conversation archive, maintenance write freeze with audit, caddy drill cutover/rollback phases, runbook with contract pin, and an end-to-end rehearsal gate. Check session fixed trash-restoration anchors in deletion propagation and stale-checkpoint rerun convergence. All gates green (ruff/mypy/pytest/forced postgres 48/48, drill phases ok, frontend lint/unit). Captured legacy-migration-cutover-contracts spec.

### Git Commits

| Hash | Message |
|------|---------|
| `c6eb2fe` | (see git log) |

### Status

[OK] **Completed**


## Session 11: Legacy deletion B1: frontend rewiring verified green

**Date**: 2026-08-30
**Task**: Legacy deletion B1: frontend rewiring verified green
**Branch**: `feat/intranet-ima`

### Summary

Executed and verified phase B1 (frontend rewiring) of legacy-deletion-release: shell stores, login guard, invitation flow, root redirect, drawer, admin empty page, and WorkspaceConnectors now run on identity-client + TanStack Query (Python API); legacy modules left in place but unused by the shell.

### Main Changes

- Rewired workspace/user-data/perfs/readonly stores and require-login/ask-knowledge composables off zero-session onto identity session + vue-query
- InvitationLayout accepts via identityClient.acceptWorkspaceInvitation (contract-verified against Python authorization service)
- Stripped legacy connector section from WorkspaceConnectors; retired CreateConnectorDialog legacy mode; mcp-config + test point at canonical /mcp
- Fixed ambiguous model-governance e2e selector (getByRole tab) that failed mobile-chromium strict mode

### Git Commits

(No commits - planning session)

### Testing

- [OK] bun run lint: 0 errors; bun test 30/30; bun run test:unit 32/32; build:front and build:admin succeeded
- [OK] bun run test:e2e (IMA_E2E_POSTGRES_PORT=55433): 42 passed, exit 0

### Status

[OK] **Completed**

### Next Steps

- B2: delete legacy frontend subtree; rework /folder/:id landing (switchWorkspace, RedirectToFolder, FolderTree) when /:type routes are removed
- B2: remove orphaned CreateConnectorDialog/ConnectorCreatedDialog/DeleteWorkspaceDialog/CreateInvitationDialog and AppFront SearchEntityDialog/NavigationDialog mounts

## Session 12: Legacy deletion B2 + B3: frontend subtree and Bun server deleted

**Date**: 2026-08-30
**Task**: Legacy deletion B2 + B3: frontend subtree and Bun server deleted
**Branch**: `feat/intranet-ima`

### Summary

Completed phase B2 (verified the previously-staged legacy frontend subtree deletion is clean and the route rework is in place) and executed phase B3 (Bun server and tooling deletion plus dependency pruning) of legacy-deletion-release. Zero/src-shared/hc/ZERO_CACHE_URL residue is gone from src/, and the whole-repo vue-tsc check now passes via the build-time checker.

### Main Changes

- Verified B2: /chat/:id redirects to /; switchWorkspace lands on / (folder landing rework); zero-session/src-shared/hc/ZERO_CACHE_URL absent from src/; quasar dev proxies point /api at Python
- B3 deletions: src-server/ (39 files), drizzle/ (8 migration dirs), drizzle.config.ts, drizzle-zero.config.ts, Dockerfile.server, dev-db/, scripts/{mcp-handshake,mcp-live,permission-smoke,dev-pg}.ts, stray Caddyfile;C/
- package.json: removed legacy scripts (dev:server, build:server, generate:zero, test:permissions, test:mcp, test:mcp-live, dev:pg, dev:db-up/down/rm) and ~27 unused deps (zero, drizzle-*, hono, ai/ai-sdk, @modelcontextprotocol/sdk, nodemailer, tokenx, ky, idb, liquidjs, hash-wasm, fflate, zod, postgres, croner, aws4fetch, embedded-postgres, drizzle-kit, @types/pg, @types/nodemailer); regenerated bun.lock (-970 lines)

### Git Commits

(No commits - deletions staged/unstaged in working tree; commit deferred to a later batch)

### Testing

- [OK] bun run lint: 0 errors (425 warnings, all stylistic)
- [OK] bun test: 13 passed / 0 failed
- [OK] bun run test:unit: 32 passed (12 files)
- [OK] bun run build:front and build:admin: succeeded (vue-tsc whole-repo check clean)
- [OK] bun run test:e2e (IMA_E2E_POSTGRES_PORT=55433): 42 passed, exit 0

### Status

[OK] **Completed**

### Next Steps

- B4: rewrite Caddyfile to terminal form; repin scripts/caddy-routing-drill.ts to the post-deletion matrix; update compose example/.env.example/README; fix GitHub workflows (drop nyaai-server build, add backend image build)
- B4: retire remaining ZERO_CACHE_URL/zero-cache references in Caddyfile, compose example, .env.example, README
- B5: Python legacy retirement (internal bridges, legacy model adapters, migrate-legacy-* CLI + tests, coexistence contract tests) — note backend/tests/contract/test_knowledge_coexistence.py still pins src-server files and must be re-scoped there

## Session 13: Legacy deletion B4: terminal routing, deployment artifacts, CI

**Date**: 2026-08-30
**Task**: Legacy deletion B4: terminal Caddy routing, deployment artifacts, CI
**Branch**: `feat/intranet-ima`

### Summary

Executed phase B4 of legacy-deletion-release. The Caddyfile is now the terminal form (all live prefixes → Python, `/api/v1/internal/*` 404, retired legacy prefixes 410, residual `/api/*` 404), the routing drill pins only the terminal matrix, and compose/.env/README/workflows are free of server/zero-cache residue.

### Main Changes

- Caddyfile (both listeners): kept all `@ima_*` exact matchers → `PYTHON_API_URL`; kept internal-404; added `@api_gone` 410 for `/api/{mcp,kb,s3,search,connectors}` + `/api/v1/chat/*`; `@api path /api/*` now answers 404 locally; dropped `SERVER_URL` proxy, `@forbidden` 403 blocks, `/zero-cache*` blocks, and the `ZERO_CACHE_URL` env usage
- scripts/caddy-routing-drill.ts: single `terminal` phase; dropped buildCutoverConfig/buildRollbackConfig derivation, bun/zero markers, and SERVER_URL/ZERO_CACHE_URL container env; kept CADDY_IMAGE pin, imageDigest, caddyfileSha256, fail-closed no-upstream-hit assertions, and the `{ok, image, imageDigest, caddyfileSha256, phases}` evidence shape
- scripts/caddy-routing-drill.test.ts: repinned to GONE_PATHS/NOT_FOUND_PATHS/INTERNAL_PATH constants + digest selection
- docker-compose.example.yml: removed `server` and `zero-cache` services, `zero-cache-data` volume, `wal_level=logical`, `CREATE DATABASE zero`, and web's SERVER_URL/ZERO_CACHE_URL/bridge env (web now only carries PYTHON_API_URL)
- .env.example: retired SITE_NAME/FRONT_URL/ADMIN_URL/DATABASE_URL/SERVER_URL/ZERO_*/S3_*; documented IMA_* keys used by compose; kept PYTHON_API_URL (quasar dev proxy)
- README.md + README.zh-CN.md: removed coexistence `/api/mcp` bearer block and bun dev:server/db-up/zero-cache-dev steps; documented Python-only dev flow (identity-compose Postgres + uvicorn, quasar dev proxy)
- .github/workflows/docker-image{,-staging}.yml: dropped Dockerfile.server/nyaai-server build; added Dockerfile.backend builds published as nyaai-api (target api) and nyaai-worker (target worker) beside nyaai-web
- backend/README.md: replaced the Coexistence section with terminal Deployment routing description

### Git Commits

(No commits — changes left in working tree per workflow)

### Testing

- [OK] bun run test:caddy-routing: exit 0, `"ok": true`, single `terminal` phase with 36 route evidences (live → python 200; gone → 410; residual/internal → 404; zero upstream hits), imageDigest `caddy@sha256:4c6e...`, caddyfileSha256 `15cb5a...`
- [OK] bun test: 9 passed / 0 failed (drill contract repinned)
- [OK] bun run lint: 0 errors (425 pre-existing stylistic warnings)
- [OK] docker compose -f docker-compose.example.yml config: parses (with IMA_BRIDGE_TOKEN/IMA_MODEL_* set); no zero/server/wal_level/SERVER_URL in resolved output
- [OK] Residue grep (tracked files, excl. .trellis): zero-cache, ZERO_*, SERVER_URL, Dockerfile.server, nyaai-server, wal_level → no matches; `/api/mcp` only in docs/ runbooks + historical DESIGN.md
- [OK] Surviving Python contract assertions (test_coexistence Caddyfile/compose checks, test_search_coexistence Caddy checks) verified against new artifacts — all pass

### Status

[OK] **Completed**

### Next Steps

- B5: re-scope backend/tests/contract/test_coexistence.py (drill buildCutoverConfig/buildRollbackConfig/'pre_sunset_rollback' tokens and README `"url": ".../api/mcp"` assertion now fail by design) and backend/tests/integration/test_postgres_cutover.py drill-token block (~lines 760-890)
- B5: test_search_coexistence.py still pins src-server/kb/retrieve.ts and src/views/ChatView.vue (absent since B2)
- B5: retire IMA_BRIDGE_TOKEN/IMA_BRIDGE_TIMEOUT_MS from compose/.env.example together with the bridge-token settings; refresh backend/README.md opening paragraph (still says "owns only /health/* and /api/v1/system/* in this phase")
- Local untracked state to clean on the dev machine: gitignored `.env` (legacy keys — regenerate from .env.example) and `.dev-pg/` data dir
- Final: runbook sunset-closure annotations + full gate matrix (implement.md steps 18-19)




## Session 12: Complete legacy deletion release (final phase B5 + all gates)

**Date**: 2026-08-30
**Task**: Complete legacy deletion release (final phase B5 + all gates)
**Branch**: `feat/intranet-ima`

### Summary

Finished the legacy deletion release: removed Python bridges/projections/migrate-legacy CLI, dropped 37 legacy public tables via cleanup migration 20260829_0011, passed the full backend+frontend gate matrix, and archived the task.

### Main Changes

- Removed api/internal bridges, legacy application modules, migrate-legacy/inventory-legacy-mcp CLI; added cleanup migration dropping legacy public tables + ACL functions
- Rewrote legacy-migration-cutover spec to terminal state; updated database-guidelines spec with forced-Postgres gate contract
- Annotated runbooks and docs (workspace-authorization, DESIGN, model-governance) with sunset-closure evidence

### Git Commits

| Hash | Message |
|------|---------|
| `84d7508` | (see git log) |

### Testing

- [OK] Backend: ruff format/check, mypy, pytest 180 passed, forced-Postgres 38 tests green, alembic upgrade head + check clean, contract check OK
- [OK] Frontend: lint 0 errors, bun test, test:unit 32, builds, e2e 42/42, caddy drill ok:true; compose config valid

### Status

[OK] **Completed**

### Next Steps

- Consider archiving parent task 08-24-python-intranet-ima-migration (was 9/10; deletion-release was the last child)
- Deploy phase C (change-controlled): apply cleanup migration in target env, terminal Caddyfile, post-deploy smoke matrix


## Session 13: Frontend UX overhaul (ima-style) — Phases 0-5 complete

**Date**: 2026-08-30
**Task**: Frontend UX overhaul (ima-style) — Phases 0-5 complete
**Branch**: `feat/intranet-ima`

### Summary

Rebuilt the front app on Tencent ima's design philosophy: left-rail shell, composer home with scope control, streaming conversations with clickable highlighted citations, three-pane knowledge workspace, Semi-inspired tokens, chrome109 build target. Full matrix green incl. 46 e2e tests.

### Main Changes

- AppShell rail + route remap; deleted MainDrawer/TaskPanel/hue engine/GroundedAskPage; tokens.css theme; chrome109 target
- KnowledgeWorkspace three-pane with create-note/upload/new-folder/tag filter; DocPreview with sanitized markdown + highlight
- AskComposer/ConversationView/HistoryPage with SSE streaming, citation sup marks, save-as-note; i18n parity 1086 keys both locales
- Spec captured: .trellis/spec/frontend/ux-design-language.md; e2e rewritten (46 tests)

### Git Commits

| Hash | Message |
|------|---------|
| `650765f` | (see git log) |

### Testing

- [OK] lint 0/0, test:unit 59, vue-tsc clean, builds chrome109, e2e 46/46, caddy drill, backend ruff/mypy/pytest green

### Status

[OK] **Completed**

### Next Steps

- User manual UX review in browser; fix visual nits
- Optional follow-up: backend folder-scope param for /ask (scope chip is UI-only today)


## Session 14: Frontend UX overhaul: audit fixes + self-service workspace + Apple-style polish

**Date**: 2026-08-30
**Task**: Frontend UX overhaul: audit fixes + self-service workspace + Apple-style polish
**Branch**: `feat/intranet-ima`

### Summary

Session summary was not supplied.

### Main Changes

- Fixed all browser-audit P0s: KB folder/note/upload ID wiring, tree refresh, dialog stacking, first-run onboarding with self-service POST /workspaces, signup gating via /auth/capabilities, localized error mapping
- Owner feedback R7/R8: right preview panes collapse by default; Ask home recentered as ChatGPT/Claude-style hero with elevated composer card

### Git Commits

| Hash | Message |
|------|---------|
| `b6588a2` | (see git log) |

### Testing

- [OK] vue-tsc clean, eslint 0/0, front+admin builds, backend 181 unit/contract, e2e 46/46, curl smoke of self-service workspace create, browser screenshots of centered home and collapsed KB preview

### Status

[OK] **Completed**

### Next Steps

- User self-testing in browser; address any further feedback, then archive 08-30-frontend-ux-overhaul


## Session 15: 移除工作区概念，知识库一等公民与极简UX重构

**Date**: 2026-08-31
**Task**: 移除工作区概念，知识库一等公民与极简UX重构
**Branch**: `feat/intranet-ima`

### Summary

全栈移除工作区概念：数据库/后端/前端改名知识库，角色简化为 owner/editor/viewer，删除邀请/用户组/文件夹ACL/标签/回收站；新增分享链接体系（只读/读写）；MCP 改用户级授权可枚举全部知识库；模型配置仅管理员可见；设置与账户合并为单页。并发子智能体分波实施：后端 245 测试、前端 37 测试、双目标构建、真实冒烟（含 OAuth+MCP 链路）全部通过；修复拒绝审计随事务回滚丢失的缺陷。

### Git Commits

| Hash | Message |
|------|---------|
| `c24ed33` | (see git log) |
| `15e2753` | (see git log) |
| `7bfb99c` | (see git log) |
| `afd3f84` | (see git log) |
| `080dc07` | (see git log) |

### Status

[OK] **Completed**


## Session 16: 管理后台中文化与模型一键接入

**Date**: 2026-08-31
**Task**: 管理后台中文化与模型一键接入
**Branch**: `feat/intranet-ima`

### Summary

删除 i18n 全面中文化；模型配置重写为服务商卡片+一键拉取/导入（真实厂商logo、能力识别、维度校验）；审计页中文分组；知识库切换即时刷新并暴露分享入口；本地 mock OpenAI 网关全链路实测通过。

### Git Commits

| Hash | Message |
|------|---------|
| `80a93e2` | (see git log) |
| `fbb2361` | (see git log) |
| `0e12c53` | (see git log) |
| `fe26ff3` | (see git log) |
| `b3f861d` | (see git log) |
| `9cc63af` | (see git log) |

### Status

[OK] **Completed**


## Session 17: Simplified model scene configuration and fixed Chinese UI

**Date**: 2026-09-09
**Task**: Simplified model scene configuration and fixed Chinese UI
**Branch**: `feat/intranet-ima`

### Summary

Removed 'Knowledge Base Assignment' tab, simplified scene config with direct model dropdowns per capability type, fixed KnowledgeBasesPage icon/button text to display Chinese labels instead of English fallback

### Git Commits

| Hash | Message |
|------|---------|
| `c4ff55f` | (see git log) |

### Status

[OK] **Completed**
