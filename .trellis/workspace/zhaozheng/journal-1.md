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
