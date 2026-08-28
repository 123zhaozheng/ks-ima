# OAuth Service Principals and MCP Implementation Plan

## Preconditions and Delivery Rules

- Re-read the task PRD, design, evidence, and injected backend/frontend specs
  before implementation. Pin the official Python MCP SDK only after verifying
  the selected version supplies FastAPI-compatible Streamable HTTP and the
  required stateless behavior.
- Keep Python the new authority. Do not modify `public.connector` semantics,
  write legacy connector rows, weaken cookie CSRF, expose internal routes, or
  introduce a Bun/Zero/public-data fallback.
- Each phase includes migration, typed backend/API, generated frontend contract
  where applicable, focused tests, audit/redaction checks, and an explicit
  rollback check. Do not begin legacy removal in this child.

## Ordered Work

### 1. Pin interfaces and configuration

1. Select and lock the official Python MCP SDK/version and the MCP/OAuth
   specification revision after a proof that it works with FastAPI and an
   official Streamable HTTP client in stateless mode.
2. Add typed settings for public HTTPS origin, canonical `/mcp` resource,
   60-second authorization-code expiry, 10-minute access-token expiry, rotating
   refresh families capped at 30 days absolute lifetime, service credentials
   capped at 90 days, rotation overlap capped at 10 minutes, trusted proxies,
   MCP request/body limits, default rate/concurrency policy, and controlled
   legacy alias flag. Deployments may shorten but not exceed these caps.
3. Define transport-neutral OAuth/MCP contracts, normalized human/principal
   `McpActor`, scope enum/tool mapping, safe error codes, OAuth error mapping,
   and redaction fields. Add no FastAPI imports to application services.
4. Verify application factory imports without networking, DB mutation, migration,
   or background work; add dependency lockfile updates only for the selected SDK.

Gate: unit tests prove canonical URL normalization, scope/tool mapping,
credential redaction, trusted-source extraction, and configuration validation.

### 2. Create target schema and repositories

1. Add an `ima` Alembic migration for pre-registered clients/redirects, grants
   and roots, one-time authorization codes, access tokens, refresh families and
   tokens, service principals/roots/credentials, rate/concurrency records, and
   indexes/constraints.
2. Store only peppered digests for authorization code, access/refresh tokens,
   and service credentials; model resource/client/grant binding, expiry,
   lifecycle/revocation epochs, usage, replacement lineage, and finite service
   credential expiry. Add seed/admin mechanics for pre-registered clients only.
3. Use row locks and one transaction for code consumption, refresh rotation and
   replay family revocation, credential rotation/replacement, and mutation plus
   audit. Preserve the existing `ima.audit_events` safe metadata contract.
4. Run fresh/repeat migrations on PostgreSQL; inspect catalog schema and assert
   no write/migration changes touch `public.connector`.

Gate: PostgreSQL tests prove digests-only persistence, uniqueness/indexes,
one-time code behavior, replay handling, finite expiry, atomic races, and safe
audit payloads.

### 3. Implement authorization and credential services

1. Build `McpAuthorizationService` from existing identity digest/session/recent
   auth/rate/audit patterns. Implement enabled pre-registered client lookup,
   exact redirect/resource/scope validation, grant subset/expansion logic, and
   explicit consent persistence.
2. Implement browser-session authorization request validation and code creation;
   bind code to client, redirect, resource, scope, workspace/root, PKCE S256,
   user security state, and expiry. Implement atomic token exchange and safe
   OAuth denial paths.
3. Implement short-lived opaque access validation and rotating refresh issuance.
   Refresh accepts the same or a narrowed grant only; detection of rotated-token
   replay revokes the family. Implement idempotent revoke by token/grant.
4. Implement service-principal create/list/get/rotate/revoke/exchange. Require
   workspace-admin authorization, owner/purpose, workspace/scopes/root, finite
   expiry, and policy validation. Show secret only from create/rotate result.
5. Apply per-token/principal/source token and tool rate/concurrency enforcement,
   optional trusted-proxy CIDR matching, lifecycle checks, and safe audit to all
   allow/deny outcomes.
6. On each bearer request construct `McpActor`, then re-evaluate current active
   account/membership/workspace/folder target authorization. Human actors use
   the existing membership/ACL path. Service principals use a dedicated
   `WorkspaceService` delegated-policy entry point that checks current workspace
   and folder lifecycle, root ancestry, and requested action without creating a
   user membership or ACL subject. Creator/admin authority is never inherited.

Gate: ASGI/PostgreSQL security matrix covers code/PKCE/client/redirect/resource/
scope failures, consent/re-consent, token audience and state, refresh narrowing/
rotation/replay, revoke/user disable/workspace archive/membership/ACL races,
service policy, rate/network, and redaction.

### 4. Expose public OAuth, discovery, and Caddy routes

1. Add explicit stable FastAPI operations for protected-resource metadata,
   authorization-server metadata, authorize, token, revoke, and service-principal
   administration. Use OAuth response forms where mandated and RFC 9457 typed
   Problem Details elsewhere.
2. Serve root and resource-specific protected metadata as needed. Always expose
   canonical public HTTPS issuer/resource values for `/mcp`; do not advertise
   DCR, unsupported grant types, registration endpoints, or metadata-document
   support.
3. Add `/mcp` bearer challenge/error handling and optional `/api/mcp` alias
   behavior that retains one canonical resource audience. Ensure authorization
   header parsing never permits query-string tokens.
4. Add exact Caddy matchers before generic `/api/*`; retain public internal
   route `404`, trusted proxy behavior, request limits, and no bridge exposure.
   Contract tests must also prove the existing explicit Python `/api/v1/workspaces/*`,
   `/api/v1/documents/*`, storage, and search routes keep their current owner and
   are not shadowed by the new OAuth/MCP matchers.

Gate: HTTP/Caddy contract tests assert metadata validity/challenge parsing,
wrong audience/invalid token/insufficient scope behavior, OAuth errors,
canonical URLs, route precedence, `/api/v1/internal/*` `404`, and no private
name/path leaks.

### 5. Build target-backed Python MCP transport and tool parity

1. Mount official-SDK Streamable HTTP transport at `/mcp` with bounded stateless
   request/session policy. Authenticate before dispatch and map protocol errors
   without raw request or credential disclosure.
2. Register tool schemas by scope for workspace list; directory/tree/document/
tag reads; search; Ask; and all currently supported target write operations.
   Tool names/argument compatibility must be documented and tested against the
   retained MCP clients, while their behavior is target service behavior.
3. Implement tools strictly through `WorkspaceService`, `KnowledgeService`,
   `StorageService`, and `SearchService`. Add `SearchService.ask_bounded`, a
   typed non-streaming method that shares browser Ask's authorization, target
   search, citation filtering, model-gateway, cancellation, and persistence
   path while enforcing MCP response limits. Do not consume/parse SSE output,
   call private search helpers from the MCP adapter, copy HTTP handlers, SQL, or
   old KB operations.
4. Carry expected version fields into every target mutation; authorize actual
   parent/source/destination and use target 404/409 behavior. Use bounded inline
   file data or target upload-ticket flow, authorized short-lived download, and
   trash-only deletion.
5. Add cancellation/timeout/body/schema bounds, audit per tool, and per-source/
   principal limits. Recheck authorization before any protected serialization or
   streamed/assembled Ask result.

Gate: official Python and existing Bun SDK Streamable HTTP clients prove
initialize, tools/list, calls, error schemas, stateless behavior, all tools,
read-only hiding, expected-version conflict, cancellation, bounded upload/
download, and target-only call tracing. ACL revoke/archive/membership changes
between token issuance and call deny immediately without legacy fallback.

### 6. Deliver Vue consent and access management

1. Export OpenAPI, regenerate TypeScript types, and extend the central client
   with typed OAuth consent/grant and service-principal operations. Keep OAuth
   browser redirects separate from JSON API persistence.
2. Implement consent login/resume, client/redirect/resource/workspace/root/
   scope/duration/refresh/write display, approve/deny, exact expanded-request
   confirmation, expired session, recent-auth, and safe error states.
3. Replace/evolve workspace connector management into distinct interactive
   connection guidance and service access management. Interactive users receive
   the canonical discovery/resource URL, connected grants, and revoke actions.
   Workspace admins get create/list/details/one-time display/rotate/revoke for
   finite delegated credentials and safe last-use/policy summaries.
4. Test generated DTO use, no secret persistence/logging, role/capability UX,
   validation/conflict/access-revoked handling, keyboard behavior, and responsive
   desktop/mobile layout.

Gate: Vitest and Playwright prove exact consent display and re-consent, refusal,
expired/recent-auth handling, one-time secret disappearance, rotate/revoke,
role limitations, browser storage redaction, and no mobile overlap/overflow.

### 7. Coexistence release, interoperability, and sunset readiness

1. Route canonical `/mcp` to Python and retain legacy `/api/mcp` only behind the
   documented temporary policy. Keep existing legacy tests green during this
   window and ensure the new endpoint never calls legacy services/data.
2. Test discovery-guided OAuth in an official SDK client, a Cursor-compatible
   Streamable HTTP configuration, Claude Desktop through the supported remote
   bridge, and one generic configurable client. Verify refresh and reauthorization.
3. Add safe legacy deprecation audit/telemetry and an inventory/report for
   connector credential/config consumers. Define operator steps to reissue a
   compliant principal credential or revoke/report each legacy key.
4. Rehearse rollback: switch Caddy/deployment to retained legacy behavior and
   confirm old semantics remain usable before sunset. Record the DB/deployment
   snapshot requirement for post-sunset recovery.

Gate: coexistence suite, real-client interoperability, migration inventory, and
rollback drill evidence are recorded; no legacy deletion begins until explicit
sunset approval.

## Required Verification

Run the focused commands as the slice lands, then the full affected checks:

```powershell
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
$env:IMA_REQUIRE_POSTGRES = "1"; uv run pytest -m postgres
```

```powershell
bun run generate:api
bun run test:unit
bun run test:e2e
bun run lint
bun run typecheck
bun run build:front
bun run build:admin
bun run build:server
bun run test:mcp
bun run test:mcp-live
```

Exact project command names must be confirmed from current package scripts
before execution. Backend tests must include a forced PostgreSQL run with zero
skips for the new security gate; frontend/admin builds run sequentially because
they share Quasar generation state.

The automated matrix must include:

- fresh/repeat Alembic migration and `ima` catalog assertions;
- direct HTTP discovery/challenge/OAuth error coverage and deployed Caddy route
  precedence/internal-404 coverage;
- PKCE S256, state/issuer, exact redirect/client/resource binding, one-time code
  and concurrent exchange tests;
- access/refresh/revoke/resource mismatch/narrowing/replay/family revoke tests;
- disabled client/user, security stamp, membership, folder ACL, archive, folder
  root, credential rotation/revoke/expiry, and revoke-versus-tool race tests;
- token/service rate, concurrency, CIDR, and spoofed forwarded-header tests;
- target read/search/Ask privacy tests, no model/public/legacy fallback, and
  every read/write MCP tool's positive/negative/version/cancel/error path;
- official Python and Bun SDK protocol suites plus Cursor-compatible, Claude
  Desktop remote, and generic client interoperability evidence;
- Vue generated-contract, consent/service UI, storage-redaction, and desktop/
  mobile Playwright coverage; and
- legacy coexistence, connector inventory/reissue-or-revoke report, Caddy
  rollback drill, and source scans proving no accidental duplicate/legacy path
  was introduced.

## Review Gates and Rollback

Before moving to the next phase, review the diff for raw-secret/content logging,
implicit broadening, non-atomic lifecycle state, direct ACL/SQL/S3 operations in
tools, browser token persistence, a second audience, or `public.connector`
mutation. Require a test that demonstrates each security-sensitive negative
condition rather than treating a hidden UI control as proof.

Rollback before legacy sunset disables the Python canonical route only through
the recorded Caddy/deployment change and restores the retained endpoint. Schema
migrations are additive and disabled/revoked records remain auditably retained;
do not attempt ad hoc secret reconstruction or silent conversion. After the
legacy cleanup milestone, restore only from the accepted pre-cutover snapshot
and prior deployment.
