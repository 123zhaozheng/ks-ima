# Python Intranet IMA Implementation Plan

## 1. Execution Contract

This document is the implementation roadmap after the user approves the final
planning summary. Approval of task creation or this draft is not implementation
approval.

The current task remains the parent/integration task. Before implementation,
create the independently verifiable Trellis child tasks listed below and start
only the first unblocked child. Each child owns its code, migrations, tests,
documentation, cleanup list, and rollback point.

Hard completion rules:

1. No accepted feature is complete with a placeholder UI, mock result, TODO
   handler, manual SQL workaround, or missing permission/error/empty state.
2. Every child has a deletion list. Replaced legacy code is deleted after the
   child's cutover and rollback gate.
3. A compatibility path has an owner, feature flag, telemetry, expiry milestone,
   and test. An unnamed permanent shim is a defect.
4. Every data path is authorized on the server. Frontend hiding is not a test.
5. Every public contract is generated or centrally typed and contract-tested.
6. Each child passes its focused checks before integration; the final child
   passes the complete repository, deployment, migration, and browser gates.

## 2. Proposed Trellis Child Task Map

| Order | Child task | Independently verifiable outcome | Depends on |
|---:|---|---|---|
| 1 | Python foundation and contracts | Python API/worker skeleton, DB migrations, OpenAPI client generation, CI and Compose health | planning approval |
| 2 | Local identity and platform administration | local login/TOTP/session/bootstrap and platform user/workspace lifecycle | 1 |
| 3 | Workspace authorization core | centralized workspaces, roles/groups, folder ACL, policy SQL, audit foundation | 2 |
| 4 | Central model governance | admin-only gateways/models/profiles/assignments/secrets and health | 2, 3 |
| 5 | Knowledge tree and Vue API migration | folders/files/notes/tags/trash and reusable Vue UI moved off Zero for this slice | 3 |
| 6 | Object storage and durable ingestion | upload tickets, versions, workers, parsers, chunks, progress/retry | 4, 5 |
| 7 | Search, conversations, and grounded Ask | ACL-first FTS/vector retrieval, citations, SSE Ask, private conversations | 4, 6 |
| 8 | OAuth, service principals, and MCP | browser Agent authorization, headless credentials, complete MCP tool set | 3, 5, 7 |
| 9 | Legacy data migration and final cutover | resumable ETL, equivalence reports, frontend/Bun routing cutover | 2-8 |
| 10 | Legacy deletion and release hardening | Zero/Bun/commercial/removed-feature deletion and full release gate | 9 + rollback window |

The parent task owns cross-child acceptance, the source PRD/design, migration
compatibility matrix, final integration review, and final archive. It is not the
direct implementation target.

## 3. Phase 0 - Planning Approval And Work Breakdown

### Deliverables

- Complete PRD convergence pass with no blocking question.
- User reviews Goal, In Scope, Out of Scope, Acceptance Criteria, Key Decisions,
  Risks/Deferred Items, and artifacts.
- After a subsequent explicit approval, create the child tasks above using this
  task as parent.
- Each child PRD links requirement IDs, exact dependencies, acceptance criteria,
  cleanup gate, and rollback point.
- Curate child-specific `implement.jsonl` and `check.jsonl` rather than copying
  every research file into every child.

### Gate

- Do not run `task.py start` on the parent.
- Start only child 1 after the approval gate.

## 4. Phase 1 - Python Foundation And Contracts

### 4.1 Backend Workspace

- Add `backend/pyproject.toml` with a supported Python version and exact lock.
- Configure FastAPI, Pydantic settings, SQLAlchemy async, asyncpg, Alembic,
  PostgreSQL task queue, httpx, boto3, MCP SDK, Argon2/TOTP dependencies,
  structured logging, telemetry, and test dependencies.
- Add `backend/src/ima` module boundaries from `design.md`.
- Add explicit application factory; no module-import side effects that seed DB,
  run jobs, or mutate settings.
- Add typed settings with structured URLs and secret types. Validate proxy
  headers, allowed origins, issuer, database, S3, gateway allowlist, upload
  limits, and master-key presence at startup.
- Add Problem Details error mapping, correlation IDs, request limits, trusted
  proxy handling, CORS default deny, and safe log redaction.
- Add liveness/readiness endpoints with separate DB/S3/job readiness results.

### 4.2 Database And Migration Skeleton

- Create SQLAlchemy metadata naming conventions and base mixins.
- Configure Alembic async environment and extension bootstrap for `vector` and
  Chinese/mixed FTS.
- Separate migration DB credentials from runtime credentials.
- Add migration transaction and downgrade/restore policy documentation.
- Add a clean-database migration test and `alembic check` gate.

### 4.3 API Contract And Frontend Generation

- Establish `/api/v1`, pagination, Problem Details, ETag/version, idempotency,
  time, ID, and SSE conventions.
- Export deterministic OpenAPI JSON.
- Move current frontend to `frontend/` only if the move can be mechanical and
  reviewed independently; otherwise keep `src/` until its slice migration.
- Add OpenAPI TypeScript generation and a typed fetch client.
- Add TanStack Vue Query and query-key factories.
- Keep Pinia only for UI/local preference state.
- Add one vertical health/session example proving frontend -> Python -> DB.

### 4.4 Deployment And CI

- Add Python API and worker multi-stage images running as non-root.
- Add Compose profile with Caddy, API, worker, PostgreSQL extensions, and MinIO.
- Route a versioned Python health/API prefix beside the Bun API.
- Add deterministic lockfile installs and CI caches.
- Add backend format/lint/type/test/migration checks and frontend existing
  lint/type/test/build checks.
- Produce SBOM/image scan inputs and pin base image digests before release.

### Acceptance Gate

- Clean checkout builds API, worker, and frontend.
- Clean database migrates to head and readiness succeeds.
- OpenAPI generation is deterministic and frontend compilation uses generated
  DTOs.
- API and worker run as separate processes from one revision.
- No product feature has switched yet; Caddy rollback is one routing change.

### Deletion Gate

- Remove no legacy runtime yet.
- Delete any duplicate experimental Python scaffolds or temporary generated
  clients created during spikes.

### Rollback

- Remove the new route and containers; legacy runtime/data remains untouched.

## 5. Phase 2 - Local Identity And Platform Administration

### 5.1 Schema And Security

- Implement users, password credentials/hash version, sessions, TOTP secrets,
  recovery codes, platform role assignments, security stamp, and auth audit.
- Implement Argon2id parameters and rehash-on-login.
- Encrypt TOTP secret material; hash session and recovery tokens.
- Add session idle/absolute expiry, rotation, revocation, recent-auth markers,
  source metadata, and concurrency-safe last-activity updates.
- Add login/source rate limits and safe failure messages.
- Add CSRF protection for cookie-authenticated unsafe requests.

### 5.2 Complete User Flows

- Sign in, sign out, current session, password change, forgotten-password reset
  when SMTP is enabled, TOTP enroll/verify/disable, recovery codes, session list,
  and revoke session.
- Admin create/disable/restore user, reset password/TOTP, revoke all sessions,
  assign platform role within hierarchy, and inspect safe auth events.
- Disabled user loses sessions, OAuth grants, and future MCP authority.
- Decide and implement sign-up policy as an administrator setting; default is
  invitation/admin creation for intranet installations.

### 5.3 Bootstrap

- Implement the local CLI first-super-admin flow.
- Refuse unsafe re-bootstrap and prevent removal/demotion of the final super
  administrator.
- Document sealed-secret/container invocation and recovery.

### 5.4 Frontend

- Migrate auth/account/admin user pages to Python API.
- Cover pending, invalid credential, rate limit, disabled, reset unavailable,
  TOTP challenge, recovery, expired session, and CSRF refresh states.
- Do not expose internal role assignment controls to lower platform roles.

### Acceptance Gate

- Browser and API tests cover the complete local identity lifecycle.
- Password/session/TOTP secrets do not appear in logs, responses, or audit.
- Privilege/session changes revoke access immediately.
- No account creation produces a personal workspace.

### Deletion Gate

- After frontend auth cutover and rollback checkpoint, remove Better Auth UI/API
  dependencies and `/api/auth` proxy only when legacy slices no longer require a
  Better Auth session.
- If legacy slices still require it, keep a named session bridge that accepts
  only Python-issued session identity, monitor it, and delete in Phase 9.
- Delete `/admin/aquireRole` immediately when Python bootstrap is active.

### Rollback

- Before session bridge deletion, route auth to Better Auth and invalidate Python
  sessions. No dual password writes after the final identity cutover.

## 6. Phase 3 - Workspace Authorization Core

### 6.1 Workspaces, Members, And Groups

- Implement platform-admin-only create/archive/restore/delete.
- Implement workspace admin assignment, member invite/add/disable/remove, role
  changes, locally managed groups, group membership, and last-admin invariant.
- Provide workspace list only for active membership plus platform metadata views
  for authorized admins.
- Platform admin workspace metadata response contains no document/folder data.

### 6.2 Folder Structure And ACL

- Implement folders, closure table, root independent ACL, ACL anchor, normalized
  entries, and versioning.
- Implement create, rename, reorder, move, trash, restore, and permanent-delete
  application services with cycle/cross-workspace/concurrency checks.
- Implement inherit/break/re-enable behavior. Breaking inheritance copies the
  effective grants transactionally.
- Implement principals for workspace role, group, and user with searchable UI.
- Implement permission preview for a selected subject without leaking content.
- Moving a subtree updates closure and ACL anchors atomically and emits audit.

### 6.3 Canonical Policy Service

- Implement one subject context and one action taxonomy.
- Implement reusable SQL expressions for single object, list, subtree, document,
  chunk, audit, and download access.
- Add policy decision reason codes for audit/tests, never exposed as resource
  discovery details to unauthorized users.
- Add optional short-lived decision caching only after versioned invalidation
  tests prove membership/ACL/revocation changes take effect immediately.

### 6.4 Security Matrix

- Generate test cases across platform role, workspace role, group, direct grant,
  inherited/broken ACL, missing membership, archived workspace, OAuth scope,
  service scope, and every resource action.
- Assert the same result through direct policy, REST list/get/write, search
  candidate builder, download authorization, SSE resume, job execution, and MCP
  application services as those layers arrive.

### Acceptance Gate

- Restricted folder name and existence are invisible to unauthorized users.
- Role/group/direct grants and inheritance behavior are deterministic.
- Platform admins cannot read content without explicit membership.
- Move and ACL changes have immediate, transactionally consistent effect.
- Query plans use indexes and set-based joins on a production-like fixture.

### Deletion Gate

- When all current folder readers/writers switch, delete JSON `entity.conf.acl`,
  SQL `kb_acl_*` functions, `entityPermission`, permission rebuild triggers,
  TypeScript ACL implementation, and Zero permission joins.
- Do not leave two active policy engines after equivalence acceptance.

### Rollback

- Preserve a read-only export of legacy entity/ACL rows and an equivalence report.
  Roll back the route slice before dropping old permission structures.

## 7. Phase 4 - Central Model Governance

### 7.1 Secrets And Gateways

- Implement encrypted gateway secrets with key version/nonce and rotation.
- Implement structured, intranet-allowlisted base URLs, TLS settings, timeouts,
  proxy policy, and redirect rejection.
- Implement create/edit/disable/delete-with-dependency-check, secret rotate, and
  connectivity/capability health checks.
- Responses expose only safe metadata and secret presence/fingerprint.

### 7.2 Models And Profiles

- Implement chat, embedding, and rerank model registry with capability-specific
  validation including embedding dimension.
- Implement versioned capability profiles containing all retrieval, prompt,
  gateway, timeouts, and safety settings.
- Publish/disable profile versions and assign workflow profiles to workspaces.
- Prevent destructive model/profile edits when active indexes/assignments depend
  on them; use a replacement/reindex workflow.
- Implement global and per-workspace availability state for clear user errors.

### 7.3 Frontend/Admin

- Build complete admin gateway, model, profile, assignment, health, secret
  rotation, and affected-workspace/reindex views.
- Workspace settings show assigned business profiles read-only.
- Remove all model/provider selectors and low-level RAG controls from user chat
  and workspace UI.

### Acceptance Gate

- Ordinary users and workspace admins cannot read or modify gateway/model
  configuration.
- A platform admin can fully create, validate, publish, assign, rotate, disable,
  and audit a model profile.
- Gateway calls are server-side and restricted to configured intranet endpoints.

### Deletion Gate

- Delete `provider` entities/pages, provider type metadata, browser model SDK
  construction, workspace provider creation, exposed API keys, per-chat model
  selection, public/free-model pricing logic, and workspace RAG tuning UI.
- Delete obsolete provider/model localization and dependencies.

### Rollback

- Keep legacy provider tables read-only until Ask/ingestion uses Python profiles
  and the final data validation checkpoint passes.

## 8. Phase 5 - Knowledge Tree And Vue API Migration

### 8.1 Knowledge Schema And Services

- Implement documents, immutable versions, file/note kinds, tags, document tags,
  trash lifecycle, and optimistic version checks.
- Implement folder list/tree/breadcrumb and document list/detail APIs with the
  canonical policy filter.
- Implement lightweight Markdown note create/read/edit/history/restore.
- Implement file metadata and pending/ready/failed states before ingestion is
  attached.
- Implement tag create/rename/merge/delete and tag assignment permissions.

### 8.2 Vue Migration

- Replace folder tree, list, breadcrumbs, item routing, notes, tags, trash, and
  workspace switching with generated API + Vue Query.
- Preserve keyboard, drag/drop, multi-select, upload entry, mobile layout, and
  permission-aware actions.
- Add complete loading, empty, pagination, stale/conflict, deleted, archived,
  retry, offline/error, and access-revoked states.
- Keep file preview disabled with an explicit pending state only until Phase 6;
  this child is not accepted as the full file workflow until its declared
  dependency completes.

### 8.3 Contract And Browser Tests

- Folder deep tree, pagination, rename conflict, move cycle, cross-workspace,
  trash/restore, permanent delete admin policy, note concurrent edit, tags,
  and restricted folder invisibility.

### Acceptance Gate

- Folder/file/note/tag/trash workflows work end to end without Zero.
- Notes are a complete Markdown feature, not a restored TipTap shell.
- All list and navigation state comes from the Python API.

### Deletion Gate

- Delete migrated Zero queries/mutators/stores and old entity routes/components
  with no remaining consumer.
- Delete Page/TipTap/CRDT/pagePatch code and data adapters after Page-to-note
  migration tests pass.
- Remove removed entity types from frontend unions and menus rather than hiding
  their buttons.

### Rollback

- Route the knowledge slice to the legacy frontend/API before the final write
  cutover. Do not run both as active writers after Phase 9.

## 9. Phase 6 - Object Storage And Durable Ingestion

### 9.1 Upload/Download

- Implement create/complete/abort upload tickets, bounded proxy fallback,
  checksum/object metadata verification, idempotency, and abandoned-upload
  cleanup.
- Implement private download authorization and short-lived S3 URL/content
  disposition.
- Implement storage accounting as operational capacity, not a commercial plan.
- Add per-deployment and per-workspace file/total storage policy managed by
  platform admins.

### 9.2 Worker Pipeline

- Implement durable state machine: queued, validating, extracting, chunking,
  embedding, ready, degraded, failed, cancelled.
- Implement parser adapters and archive/MIME/size/time limits.
- Persist source metadata for PDF pages, spreadsheet sheets/ranges, and slides.
- Implement versioned chunking and embedding batches with idempotent replacement.
- Implement retry/backoff, cancellation, dead-letter view, safe error classes,
  admin retry, and automatic recovery after worker restart.
- Implement reparse and reindex as new job/version operations.

### 9.3 Frontend

- Complete upload file/folder/drop flows with bounded concurrency and individual
  progress/retry/cancel.
- Complete preview/download/extracted text/source metadata/reparse states.
- Show keyword-ready/embedding-degraded distinctly from failed.

### Acceptance Gate

- PDF, DOCX, XLSX, PPTX, text, Markdown, JSON/CSV fixtures ingest with correct
  source metadata and survive worker/API restart.
- Unsupported media remains safely previewable/downloadable and is explicitly
  non-indexed.
- Unauthorized download and job status are indistinguishable from missing.
- Retry/cancel/reparse do not duplicate versions, chunks, blobs, or audit events.

### Deletion Gate

- Delete Bun parsing job, in-memory enqueue set, `entity.conf.parseStatus`, JSON
  embeddings, old S3 upload/finalize/download routes, browser parse fallbacks,
  reset/cleanup jobs whose target no longer exists, and unused parser packages.

### Rollback

- Existing objects are retained. Database mapping and checksums allow the legacy
  downloader to be restored before final cutover.

## 10. Phase 7 - Search, Conversations, And Grounded Ask

### 10.1 Retrieval

- Implement FTS query parsing/ranking with Chinese/mixed fixtures.
- Implement pgvector embedding dimension/index migrations and filtered search.
- Implement normalized hybrid fusion, threshold, top K, deduplication, and
  optional rerank from capability profile.
- Ensure policy SQL filters candidates before text reaches embedding/rerank/chat.
- Implement folder/tag filters and stable citation paths/version/source ranges.
- Add query plan/latency fixture and model gateway timeout/degradation behavior.

### 10.2 Conversations And Ask

- Implement private conversations outside the knowledge tree, messages,
  answer-runs, citations, cancellation, retry, title generation profile, and
  retention/deletion.
- Implement fixed knowledge-gap response without chat-model invocation.
- Implement grounded prompt and server-side model calls only.
- Implement SSE persistence/resume/cancel/access-revocation behavior.
- Implement citation-backed failure behavior according to profile policy.
- Exclude conversations from the knowledge corpus.

### 10.3 Frontend

- Complete Ask entry from workspace/folder/file context.
- Complete conversation list, new question, streaming, stop, retry, failure,
  knowledge-gap, citations, navigate-to-source, and access-revoked states.
- Remove model selector and plugin/tool configuration from ordinary users.

### Acceptance Gate

- Grounded answers cite immutable source versions and navigate correctly.
- Restricted content never appears in candidates, prompts, answers, paths,
  citations, counts, logs, or telemetry.
- Gateway/embedding/rerank failures follow documented no-public-fallback behavior.
- Search and Ask meet agreed production-like performance budgets.

### Deletion Gate

- Delete `/api/v1/chat/completions` Bun proxy, AI SDK browser execution, usage
  price/quota accumulation, old search route/records, builtin workspace plugin,
  plugin toggles/tool-call client architecture not used by Ask, and related
  shared mutators/types.

### Rollback

- Keep old conversation data export/read-only view until migration verification;
  new conversations are not dual-written.

## 11. Phase 8 - OAuth, Service Principals, And MCP

### 11.1 OAuth Authorization Server

- Implement protected-resource and authorization-server metadata with canonical
  HTTPS issuer/resource behind trusted proxy handling.
- Implement 401/403 Bearer challenges with safe metadata/scopes.
- Implement administrator pre-registration and strict rate-limited DCR.
- Implement exact redirect validation for HTTPS and loopback-native clients.
- Implement Authorization Code + PKCE S256, explicit local consent, resource
  indicator binding, one-time 60-second code, issuer response, and denial.
- Implement opaque 10-minute access tokens, optional rotating refresh families,
  reuse detection, revoke, immediate status lookup, and redaction.
- Do not advertise Client ID Metadata Document support in MVP.

### 11.2 Connected Agents UX

- Complete user flow from Agent authorization URL through login, client identity,
  workspace/folder/scopes/expiry consent, approve/deny, exact redirect, and
  connected-Agent grant list/revoke.
- Exact-subset repeat grants may skip consent only under documented policy;
  broader folder/write requests always require consent.
- Workspace admins can revoke workspace grants without seeing token material.

### 11.3 Service Principals

- Implement admin create, one-time secret display, client-credentials exchange,
  folder/scope/expiry/network policy, usage metadata, rotation grace, revoke,
  and owner/contact.
- No refresh token or authorization-code flow for service principals.

### 11.4 MCP

- Mount official Python Streamable HTTP server at canonical `/api/mcp`.
- Register the full read/write tool set according to token scopes.
- Map all tools to the existing Python knowledge/search/Ask application services.
- Implement bounded inline and ticket-based uploads, short-lived downloads,
  structured errors, timeout/cancel, rate/concurrency limits, and audit.
- Preserve legacy `ima_` keys behind a disabled-by-default compatibility switch
  only for migration testing; do not expose new legacy-key creation in final UI.

### Acceptance Gate

- Official SDK client completes metadata -> DCR/pre-registration -> PKCE consent
  -> token -> tools -> refresh -> revoke.
- Wrong issuer/resource/client/redirect/verifier/code/scope/token state is denied.
- Grant/user/member/ACL/workspace changes take effect on next request.
- Service credentials obtain short access through client credentials and cannot
  enter user flow or obtain refresh.
- All 15 MCP tools pass positive and authorization/cancellation/error cases.
- Logs/browser history/audit contain no raw credential.

### Deletion Gate

- Migrate existing connectors to service principals or explicitly revoke/report
  them.
- Delete Hono MCP, TypeScript SDK server, connector API-key creation UI, `ima_`
  bearer resolver/hash utilities, compatibility switch, and SDK dependency after
  migration acceptance.
- Delete all MCP client/plugin remnants if any remain.

### Rollback

- During the bounded compatibility window, Caddy can restore Hono `/api/mcp` and
  old keys. After legacy credential deletion, rollback requires the pre-cutover
  database snapshot and deployment.

## 12. Phase 9 - Legacy Data Migration And Final Cutover

### 12.1 Migration Tooling

- Add `ima migrate-legacy plan`, `apply`, `resume`, `verify`, and `report`.
- Persist migration runs, step checkpoints, source/target IDs, warnings, and
  checksums. Every step is idempotent and resumable.
- Build versioned legacy fixtures covering every retained/removed table/type,
  ACL inheritance, malformed JSON, duplicates, dangling references, blobs,
  password/TOTP, connectors, pages, and commercial records.

### 12.2 Transformation Steps

1. Inventory source schema/version, row counts, object keys/checksums, extensions,
   and unexpected values; refuse unknown destructive migration.
2. Import users/password/TOTP compatibility and platform roles; invalidate old
   sessions.
3. Import workspaces without plans/payments/quotas and map member roles.
4. Build folders/closure/ACLs, verify no cycles/orphans, and compare legacy
   permission fixtures.
5. Import files/notes/blobs/tags and version metadata; convert live Pages to
   Markdown notes when possible and report unsupported content explicitly.
6. Import retained private conversations/messages/citations according to the
   approved retention rule.
7. Convert legacy connectors to disabled service principals pending admin
   rotation, or revoke them with a report; never recover raw old secrets.
8. Import platform model metadata but require admin secret/profile validation.
9. Reparse/rechunk/reembed current document versions with the target pipeline.
10. Produce removed-domain archive/count report, not target commercial tables.

### 12.3 Verification

- Row counts by mapped domain; source-to-target ID coverage; referential and
  closure integrity; blob existence/checksum; ready document/chunk counts;
  password verification fixture; ACL equivalence matrix; model assignment;
  OAuth/service state; audit sequence.
- Compare representative folder lists, document reads, search, Ask, download,
  and MCP results for every role/restriction.
- Treat any inaccessible-source leak, missing retained content, corrupt blob, or
  unmapped active user/workspace as a blocker.

### 12.4 Cutover Runbook

- Rehearse on production-size sanitized copy and record duration/capacity.
- Announce freeze; stop legacy jobs/writes; take DB/object/deployment backup.
- Run delta migration and verification; deploy final frontend; switch Caddy.
- Execute role/Agent/operator smoke matrix and monitor error/queue/policy metrics.
- Keep old tables/services read-only and deployment artifact available for the
  defined rollback window.
- Record approval before cleanup child begins.

### Acceptance Gate

- Migration report has no blocking/unexplained row.
- All user, admin, restricted, OAuth, service, and operator journeys pass on
  migrated data.
- Python is the sole writer and Vue no longer connects to Zero/Bun.

### Rollback

- Stop Python writes, restore final legacy snapshot if necessary, restore prior
  frontend/Caddy/Bun/Zero deployment, and document the failed verification.

## 13. Phase 10 - Legacy Deletion And Release Hardening

### 13.1 Runtime/Code Deletion

- Remove `src-server`, Zero server/cache/config, Drizzle runtime/generator,
  generated Zero schema, shared queries/mutators/table permissions, Bun server
  build, old Dockerfile, and Zero Compose databases/volumes from active config.
- Remove payment/plan/price/order/quota/reset/payment-provider code, schema,
  routes, admin UI, localization, tests, env, dependencies, and jobs.
- Remove channel, translation, Page/CRDT/TipTap, public publishing, SearXNG/Jina,
  gread/GitHub extension, MCP client/plugin, provider entity, assistant entity,
  obsolete search record, and shortcut remnants.
- Remove browser provider/model SDK logic and direct AI calls.
- Remove unused public assets/packages only after reference and license audit.
- Squash/generated migrations only if repository release policy explicitly
  permits; otherwise add one destructive cleanup migration and keep history.

### 13.2 Residue Searches

Run case-insensitive searches for at least:

```text
@rocicorp/zero, zero-cache, ZERO_, src-server, hono, drizzle-zero,
planPrice, planId, payment, stripe, wxpay, order, quotaUsed, resetQuota,
translation, channel, mcpPlugin, pubRoot, pagePatch, tiptap, searxng,
r.jina.ai, gread, createProvider, provider-options, chat/completions
```

Every remaining match has a documented target-domain reason. Generated build,
archive, fixture, and migration-history matches are classified separately.

### 13.3 Full Release Gate

Backend commands (final exact commands are pinned in `pyproject.toml`):

```text
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy backend/src
uv run pytest
uv run alembic check
uv run ima contract export --check
```

Frontend commands:

```text
bun install --frozen-lockfile
bun run lint
bun run typecheck
bun run test
bun run build
bun run test:e2e
```

Deployment/migration commands:

```text
docker compose -f deploy/compose/compose.yml config
docker compose -f deploy/compose/compose.yml build
docker compose -f deploy/compose/compose.yml up -d
uv run ima migrate-legacy verify --report <artifact>
```

Also verify:

- clean install and clean database bootstrap;
- restore drill on a disposable environment;
- non-root containers, readiness/worker lag, TLS OAuth metadata;
- no public egress in a network-restricted test;
- SBOM/dependency/image vulnerability review;
- Playwright desktop/mobile screenshots with no overlap/overflow;
- all acceptance scenarios from PRD including restricted-folder non-disclosure;
- official MCP OAuth and service-principal interoperability suite;
- no placeholder/TODO/mock behavior in accepted modules;
- dead code and unused production dependencies removed.

### Final Acceptance

- Python API/worker and Vue SPA are the only application runtimes.
- All PRD functions are complete, authorized, tested, deployable, documented,
  and usable without infrastructure knowledge.
- All named legacy concepts are absent from live code/schema/config/runtime.
- Rollback window is closed only after user/operator acceptance and verified
  backup.

## 14. Cross-Phase Review Gates

At the end of every child task:

1. Re-read the child PRD/design/implementation slice.
2. Run focused tests and the affected global lint/type/build subset.
3. Trace data from UI/MCP through API/application/policy/repository/DB and back.
4. Verify positive and negative authorization cases.
5. Verify secrets and restricted content do not enter logs/errors/audit/metrics.
6. Check migration/rollback for data-changing work.
7. Search for old and duplicate implementations.
8. Use `trellis-check`; fix findings before parent integration.
9. Update project specs with real conventions learned from the completed slice.
10. Commit the child with its tests, migration, docs, and deletion together.

## 15. Principal Risks And Mitigations

| Risk | Mitigation and gate |
|---|---|
| Four simultaneous rewrites | Retain Vue; migrate vertical slices; keep Caddy rollback |
| Permission leak during search/RAG | Canonical set-based policy SQL before candidates; transport matrix tests |
| OAuth client incompatibility | Pin MCP revision; pre-registration + strict DCR; official SDK contract suite |
| OAuth SSRF via client metadata | Do not advertise CIMD in MVP; add only with explicit SSRF/trust design |
| Worker loses/duplicates ingestion | Durable queue, idempotency keys, immutable versions, restart tests |
| Large vector scan | pgvector dimension/index and production-like query-plan gate |
| Password/TOTP incompatibility | Preflight fixture; verify PHC/secret format; forced reset with report if needed |
| Legacy generic entity data cannot map | Inventory, explicit active/removed mapping, Page conversion report, no silent drop |
| Long dual-stack period | Named slice owner/expiry; no broad dual write; final freeze and cleanup task |
| Model secret leakage | Envelope encryption, response redaction, structured logs, secret tests |
| Intranet deployment uses HTTP | Production OAuth readiness fails without trusted HTTPS issuer |
| Admin becomes implicit reader | Separate platform/workspace roles; explicit membership/emergency grant only |
| Scope expands through "full implementation" | Full means every accepted requirement is complete; deferred items remain explicitly out of scope |
