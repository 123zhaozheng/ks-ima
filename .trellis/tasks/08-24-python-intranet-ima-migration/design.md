# Python Intranet IMA Target Design

## 1. Decision Summary

| Area | Target decision |
|---|---|
| Product | Private, self-hosted knowledge workspace centered on folders, files, notes, grounded Ask, and MCP access |
| Backend | Python modular monolith using FastAPI/ASGI |
| Worker | Separate process from the same Python package using a durable PostgreSQL-backed task queue |
| Frontend | Retain Vue 3 + TypeScript; use Vite, Quasar during migration, Pinia for local UI state, and TanStack Vue Query for server state |
| API | Versioned REST/JSON under `/api/v1`; OpenAPI-generated TypeScript client; SSE for answer and job progress streams |
| Database | PostgreSQL as source of truth; SQLAlchemy 2 async + Alembic; `pgvector` for embeddings; existing Chinese FTS retained or reimplemented equivalently |
| Blob storage | S3-compatible storage, including MinIO; browser upload/download through short-lived server-authorized tickets |
| Authentication | Local accounts, secure cookie sessions, Argon2id, TOTP, explicit bootstrap CLI |
| Agent authorization | OAuth 2.1 Authorization Code + PKCE for interactive Agents; scoped service principals for unattended Agents |
| MCP | Official Python MCP SDK, Streamable HTTP, thin adapter over the same application services used by REST |
| Permissions | Platform roles plus workspace roles plus folder ACL inheritance; one canonical policy service and set-based SQL filtering |
| Models | Platform-admin-only gateways, secrets, models, and capability profiles; no model selection/configuration for ordinary users |
| Retrieval | ACL-first PostgreSQL FTS + pgvector hybrid retrieval, optional rerank, grounded generation, stable citations |
| Migration | Strangler migration by vertical slice, followed by a controlled write freeze and verified final data cutover |
| Deletion | Zero, Bun/Hono backend, commercial domain, removed entities, user providers, and expired compatibility code are deleted at named gates |

### 1.1 Capability Disposition

| Current capability/domain | Disposition | Target outcome |
|---|---|---|
| Vue 3 knowledge UI | Retain and migrate | Preserve workflows/components; replace data and visual layers incrementally |
| Quasar | Simplify/reevaluate | Keep during migration; change only with the later approved UI system |
| Rocicorp Zero | Replace then remove | REST/OpenAPI, SSE, Vue Query, explicit server business logic |
| Bun/Hono API | Replace then remove | FastAPI modular monolith and Python worker |
| Drizzle/Zero schemas and shared mutators | Replace then remove | SQLAlchemy/Alembic models, application services, generated API DTOs |
| PostgreSQL and Chinese FTS | Retain/migrate | Transaction source plus tested mixed-language FTS |
| JSON application embeddings | Replace | pgvector typed column and vector index |
| S3/MinIO blob storage | Retain behind adapter | Private objects, upload/download tickets, checksums, versioned references |
| Folder entity tree | Migrate | Typed folders, closure table, explicit lifecycle and ACL anchor |
| File `item` | Migrate | Document plus immutable versions, blob, ingestion state, source metadata |
| Lightweight note behavior | Complete | First-class Markdown document with UI/API/MCP/history |
| Page/TipTap/CRDT/pagePatch | Transform then remove | Convert live content to Markdown note where possible; report unsupported data |
| Chat/message branches | Simplify/migrate | Private Ask conversations outside knowledge tree; no general plugin platform |
| Search records/page | Replace | Stateless ACL-first workspace/folder/tag search API and dialog |
| Current RAG modules | Retain behavior, replace implementation | Durable ingestion, FTS+pgvector, rerank, grounded answer, stable citations |
| In-process parsing timers/cron | Replace | Durable PostgreSQL-backed worker jobs and state machine |
| Current folder ACL concept | Retain and normalize | Roles/groups/users, inheritance break, canonical set-based policy service |
| `entityPermission` per-user materialization | Replace | Closure + ACL anchor + normalized grants; no duplicated TypeScript/SQL policies |
| Better Auth local identity | Migrate behavior | Python local auth, Argon2id/TOTP/session security and CLI bootstrap |
| Static connector `ima_` keys | Transform then remove | OAuth user grants plus service principals/client credentials |
| TypeScript MCP server | Migrate | Official Python SDK at `/api/mcp`, same application services as REST |
| MCP client/plugin entity | Remove | Product exposes MCP and never installs/proxies external MCP tools |
| User/workspace providers and model selectors | Replace/remove | Platform-admin gateways/models/profiles; users see business workflows only |
| Public model proxy and price/quota accounting | Replace/remove | Server-side capability profiles and operational usage telemetry only |
| Workspace/member collaboration | Retain and govern | Multi-workspace, platform-owned lifecycle, workspace-admin membership/content |
| Automatic personal workspace | Remove | Account creation has no workspace side effect |
| Admin user/workspace/model pages | Retain and complete | Unified SPA admin center with strict platform capabilities |
| Payment/plan/price/order/quota | Remove | No target tables, routes, jobs, UI, dependencies, or settings |
| Publishing, translation, channel/IM | Remove | No target route/data/UI |
| SearXNG/Jina/gread/public web | Remove | No public egress or public fallback |
| PWA/offline knowledge cache | Simplify | SPA shell only unless approved; never cache protected content for offline use |

## 2. Architecture Principles

1. Keep one deployable product, not a microservice estate. API and worker are
   separate processes because workloads differ, but they share domain and
   application code.
2. Put authorization before data exposure. Listing, metadata, search candidates,
   prompt context, citations, downloads, SSE events, background jobs, and MCP
   results are all protected data paths.
3. Keep transports thin. REST, SSE, admin UI, and MCP call the same application
   services; none owns a private copy of business logic.
4. Make domain concepts explicit. Do not keep product state in generic JSON when
   it controls permissions, ingestion, model policy, or lifecycle.
5. Prefer durable state over process memory. Jobs, grants, sessions, parse state,
   revocation, and audit survive restarts.
6. Keep the user surface smaller than the operator surface. Users work with
   folders, documents, notes, Ask, and search; administrators manage systems and
   policies.
7. Every replacement has a deletion gate. Compatibility exists for rollback,
   not as an indefinite second architecture.

## 3. Target Runtime Topology

```text
                         +----------------------+
Browser ---------------->| Caddy / reverse proxy|
                         +----+-------------+---+
                              |             |
                       static Vue SPA       | /api, /api/mcp, OAuth
                                            v
                                  +-------------------+
                                  | Python ASGI API   |
                                  | FastAPI           |
                                  +--+-----+-----+----+
                                     |     |     |
                         SQL/pgvector |     |     | S3 API
                                     v     |     v
                              +-----------+ | +---------+
                              |PostgreSQL | | |MinIO/S3 |
                              +-----+-----+ | +---------+
                                    ^       |
                                    | jobs  | model gateway HTTP
                              +-----+-------v---+
                              | Python Worker   |
                              | parse/embed/etc |
                              +-----------------+

Allowed outbound destinations:
  - configured intranet chat/embedding/rerank gateways
  - configured S3-compatible endpoint
  - configured SMTP relay, if email is enabled
No public fallback endpoints.
```

Deployment profiles:

- `single-host`: Caddy, API, worker, PostgreSQL with pgvector/Chinese FTS, and
  MinIO in Docker Compose.
- `managed-infra`: Caddy/SPA, API replicas, workers, managed PostgreSQL, and an
  internal S3-compatible service.
- API and worker images come from the same source revision. Alembic migrations
  run as an explicit pre-deploy job, never implicitly in every API replica.

## 4. Repository And Module Boundaries

Target top-level shape:

```text
backend/
  pyproject.toml
  alembic.ini
  migrations/
  src/ima/
    main.py
    config.py
    cli.py
    api/
      dependencies.py
      errors.py
      pagination.py
      v1/
      oauth.py
      mcp.py
      well_known.py
    domain/
      identity/
      authorization/
      workspaces/
      knowledge/
      conversations/
      retrieval/
      models/
      connectors/
      audit/
      jobs/
    application/
      commands/
      queries/
      services/
    infrastructure/
      db/
      object_store/
      model_gateway/
      tasks/
      mail/
      observability/
    workers/
      app.py
      tasks/
    tests/
      unit/
      integration/
      contract/
      security/
frontend/
  src/
    api/generated/
    app/
    modules/
      auth/
      workspaces/
      knowledge/
      ask/
      connectors/
      admin/
    components/
    stores/
    router/
deploy/
  compose/
  caddy/
  scripts/
```

Rules:

- Domain modules do not import FastAPI, SQLAlchemy sessions, S3 clients, or Vue
  contract details.
- Application services receive an actor, validated command/query DTO, unit of
  work, policy service, and required ports.
- Infrastructure implements repositories and external adapters.
- API/MCP modules map transport payloads to application DTOs and map domain
  errors to stable transport errors.
- Worker tasks call application services using a recorded system/job actor and
  revalidate the target's current lifecycle and authorization when required.
- Frontend code never imports database-shaped generated types. It consumes the
  OpenAPI client DTOs.

## 5. Python Technology Choices

### 5.1 Core

- FastAPI and Starlette for ASGI, dependency wiring, OpenAPI, streaming, and
  middleware.
- Pydantic 2 plus `pydantic-settings` for boundary validation and configuration.
- SQLAlchemy 2 async with `asyncpg`; repository methods own set-based SQL.
- Alembic for forward-only schema migrations plus explicit data migration
  commands.
- PostgreSQL extensions: `vector`; preserve the repository's mixed/Chinese FTS
  behavior through a versioned database bootstrap and migration test.
- Official `mcp` Python SDK for MCP server and protocol types.
- `httpx` for internal model gateways with explicit timeout, retry, proxy, TLS,
  and destination policy.
- `boto3` for S3-compatible signing and worker object access.

### 5.2 Durable Tasks

Use a proven PostgreSQL-backed task queue compatible with async Python (planned
choice: Procrastinate) so the default deployment does not add Redis. It must
provide durable enqueue, retry/backoff, scheduled execution, concurrency
control, task locks, and inspection. Pin an exact supported version after a
spike verifies Python/PostgreSQL compatibility.

FastAPI `BackgroundTasks`, bare `asyncio.create_task`, in-memory sets, and cron
inside every API replica are forbidden for ingestion or migration work.

Required queues and concurrency keys:

- `ingest`: MIME validation, extraction, normalization, chunking;
- `embedding`: batches grouped by model profile and dimension;
- `maintenance`: reindex, cleanup, reconciliation, usage aggregation;
- `migration`: resumable legacy import steps.

One document version has one idempotency key. A retry must not duplicate chunks,
blobs, audit events, or model usage.

### 5.3 File Parsers

- Text/Markdown/CSV/JSON/XML: bounded decoding with charset detection and size
  limits.
- PDF: `pypdf`/`pdfplumber` adapter with page metadata. Select the adapter in a
  license and extraction-quality spike.
- DOCX: `python-docx` with paragraph/table metadata.
- XLSX: `openpyxl` in read-only/data-only mode with sheet and cell-range source
  metadata.
- PPTX: `python-pptx` with slide source metadata.
- Images/audio/video remain uploadable and previewable but are not indexed in
  MVP unless an explicit OCR/transcription feature is later approved.
- All archive-based formats enforce uncompressed-size, member-count, nesting,
  and XML entity limits.

## 6. Frontend Architecture

### 6.1 Retained And Replaced

Retain:

- Vue 3, TypeScript, Vite/Quasar build knowledge, router patterns, localization,
  reusable file preview, Markdown rendering, directory interactions, upload
  UX, account forms, and accessible layout behavior.

Replace:

- Zero client, Zero cache connection, generated schema, shared queries and
  shared mutators;
- optimistic mutations that encode server business behavior in the browser;
- direct browser AI SDK/provider construction;
- provider/model/assistant entity pages for ordinary users;
- separate commercial/admin components and obsolete entity routing.

### 6.2 State Model

- TanStack Vue Query owns server state, caching, invalidation, pagination, and
  retry policy.
- Pinia owns only durable local preferences and transient UI state.
- OpenAPI generates TypeScript DTOs. Hand-written duplicate request/response
  interfaces are forbidden except view-only projections.
- Mutations return authoritative resource versions. Optimistic changes are used
  only where rollback is deterministic, such as rename/reorder.
- SSE events invalidate or patch named query keys; they do not form a second
  client-side database.

### 6.3 Information Architecture

User application:

- workspace switcher;
- Files: folder tree plus current folder list;
- Notes: notes live in folders and use a lightweight Markdown editor;
- Ask: private conversation list and grounded Q&A;
- Search: workspace/folder/tag scoped results;
- Trash;
- account and local device preferences.

Workspace administration:

- overview and membership;
- groups;
- folder authorization explorer;
- tags;
- OAuth grants and service credentials;
- workspace audit events;
- assigned model capability profiles shown read-only.

Platform administration:

- users, sessions, disable/restore, password/TOTP reset;
- workspace lifecycle and administrator assignment;
- model gateways, models, capability profiles, health checks, and workspace
  assignments;
- OAuth client policy/registrations;
- system settings, outbound endpoints, storage policy, and audit;
- job health and failed-job operations without exposing secrets.

Use one SPA and one API origin. `/admin/**` is route-gated for usability but all
admin authorization remains server-side.

## 7. API And Streaming Contracts

### 7.1 General Rules

- Base path: `/api/v1`.
- IDs remain opaque strings. Preserve existing IDs during migration where they
  are valid and unique.
- JSON uses camelCase externally and explicit Pydantic aliases internally.
- Timestamps are UTC RFC 3339 strings.
- Errors use RFC 9457 Problem Details with stable `type`, `code`, `status`,
  `detail`, and optional field errors/correlation ID.
- Unauthorized resource discovery returns the same 404 problem as a missing
  resource. Authentication failure is 401; known-client scope failure is 403
  only when this does not reveal protected resource existence.
- Collection pagination uses opaque cursor plus `items` and `nextCursor`.
- Mutable resources expose a version/ETag. Conflicting edits return 409/412.
- Create and destructive retryable operations accept an `Idempotency-Key`.
- OpenAPI is a checked artifact: backend contract tests and frontend generation
  fail CI on drift.

### 7.2 API Families

```text
/api/v1/auth/*                 local login, logout, session, password, TOTP
/api/v1/me                     current user and effective platform capabilities
/api/v1/workspaces             permitted workspace list; admin lifecycle
/api/v1/workspaces/{id}/members
/api/v1/workspaces/{id}/groups
/api/v1/workspaces/{id}/tags
/api/v1/folders/*              tree, list, create, rename, move, trash, ACL
/api/v1/documents/*            file/note metadata, content, versions, lifecycle
/api/v1/uploads/*              create ticket, complete, abort
/api/v1/ingestion-jobs/*       status, retry, cancel, progress stream
/api/v1/search                 ACL-first search
/api/v1/ask                    answer creation and SSE stream
/api/v1/conversations/*        private conversation history and deletion
/api/v1/oauth-grants/*         user/workspace grant management
/api/v1/service-credentials/*  administrator service principals
/api/v1/audit-events           permission-scoped cursor listing/export
/api/v1/admin/*                platform operations and model governance
/api/mcp                       canonical Streamable HTTP MCP resource endpoint
/.well-known/*                 OAuth/MCP metadata
/oauth/*                       authorize, token, revoke, client metadata/register
```

### 7.3 SSE

All streams emit an event ID, versioned event type, JSON data, and heartbeat.
Reconnect uses `Last-Event-ID` where the stream is resumable.

Ask events:

```text
answer.started
retrieval.completed       counts and safe citation metadata only
answer.delta
answer.citation
answer.completed          usage, model profile alias, final status
answer.failed             stable safe error code
```

Job events:

```text
job.queued
job.started
job.progress
job.completed
job.failed
job.cancelled
```

Before every resume and event emission, the stream verifies that the actor may
still access the conversation/job/resource. Revoked sessions and grants close
the stream.

## 8. Authentication And Session Security

### 8.1 Human Login

- Local username/email and password only for MVP.
- Argon2id password hashes with versioned parameters and rehash-on-login.
- HttpOnly, Secure, SameSite=Lax session cookie with server-side opaque session
  records; rotate on login, password change, privilege change, and TOTP changes.
- CSRF token required for cookie-authenticated unsafe methods.
- Configurable idle and absolute session lifetimes.
- Per-account and per-source login rate limits with audit and safe lockout.
- TOTP recovery codes are one-time hashed values. TOTP secrets are encrypted.
- User disablement revokes sessions, OAuth grants/tokens, and owned service
  principals according to their ownership policy.

### 8.2 Bootstrap And Recovery

- `python -m ima.cli bootstrap-admin` creates the first super administrator from
  interactive input or sealed deployment secret.
- It refuses to run when an active super administrator exists unless an explicit
  recovery flag and database/operator proof are supplied.
- There is no network endpoint equivalent to `/admin/aquireRole`.
- Super administrator deletion/demotion requires another active super
  administrator and recent authentication.

## 9. Agent OAuth And Service Principals

### 9.1 Interactive OAuth Flow

Discovery contract:

```text
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/api/mcp
/.well-known/oauth-authorization-server
/oauth/authorize
/oauth/token
/oauth/revoke
/oauth/register
```

The resource metadata identifies the exact canonical `/api/mcp` absolute URI
and local authorization server. The authorization-server metadata advertises
only authorization code, refresh token, and client credentials grants that are
actually implemented, PKCE S256, supported token authentication methods, and
the three MCP resource scopes. Production issuer and authorization endpoints
must be HTTPS behind Caddy; only loopback development may use HTTP.

1. Agent calls the canonical `https://<origin>/api/mcp` resource and receives a
   401 Bearer challenge with its protected-resource metadata URL.
2. Agent discovers authorization-server metadata and obtains/declares a client
   identity according to supported MCP OAuth metadata/registration rules.
3. Agent sends an authorization request with authorization code, PKCE S256,
   state, exact redirect URI, resource indicator for this MCP endpoint, and
   requested scopes.
4. User signs in locally or reuses a valid local session.
5. Consent shows client identity, workspace, optional folder roots, read/write
   actions, expiry, and data sensitivity warning.
6. Server rejects any request exceeding client policy or user authority.
7. One-time short-lived code is bound to client, redirect URI, PKCE challenge,
   resource, user, and approved grant.
8. Agent exchanges the code with the verifier.
9. Server returns a short-lived resource-bound access token and rotating refresh
   token when the client policy allows offline access.
10. Each MCP request resolves the grant and re-evaluates current user,
    membership, ACL, workspace state, and token scope.

Required protections:

- exact redirect URI comparison, HTTPS except loopback development redirects;
- PKCE S256 required for all clients; no implicit/password grants;
- state handled by clients and issuer/resource/audience validation by server;
- authorization codes are one-time and expire in approximately 60 seconds;
- opaque access tokens have a default 10-minute lifetime, are stored only as
  SHA-256 digests, and are resolved on each MCP request for immediate revocation;
- optional refresh tokens rotate on every use. Reuse of a rotated token revokes
  its full token family;
- refresh token rotation with family reuse detection;
- access/refresh/code values are logged only by prefix/fingerprint, never raw;
- grant and token revocation is immediately checked at MCP entry;
- support administrator pre-registration plus strict, rate-limited RFC 7591
  dynamic client registration for compatible Agent clients;
- do not advertise Client ID Metadata Document support in MVP. Adding it later
  requires HTTPS-only metadata fetching, exact client-ID equality, caching,
  domain trust policy, and SSRF/DNS-rebinding controls;
- arbitrary redirect URI registration is forbidden. HTTPS URIs and native-app
  loopback HTTP redirects use exact matching; wildcards, fragments, and remote
  cleartext HTTP are rejected;
- consent cannot select resources the user cannot currently manage for sharing.

Suggested scopes:

```text
kb:read       permitted workspace/folder/tag discovery, metadata, parsed text,
              search, notes/files, and authorized download
kb:ask        retrieval and grounded answers (also requires effective view)
kb:write      create/update/upload/move/tag/delete-to-trash, with the specific
              resource action checked again for every call
```

`kb:ask` does not imply `kb:write`, and `kb:write` never bypasses a resource's
specific `create_child`, `edit`, `move`, `delete`, or visibility action. ACL
management, permanent deletion, membership management, model administration,
and platform administration are never Agent scopes. `offline_access` is an
authorization-server policy request, not an advertised MCP resource scope.

### 9.2 Service Principals

- Created by workspace admin or higher only when platform policy enables them.
- Required fields: name, owner, purpose, workspace, zero or more folder roots,
  scopes, expiry, rotation deadline, optional network rule.
- Secret is displayed once and stored as a memory-hard or SHA-256 keyed digest
  with server pepper, depending on token entropy and operational design.
- Rotation creates overlap only for a short configured grace period.
- A service principal has no implicit human permissions. It receives only its
  recorded scopes intersected with current workspace/folder policy.
- Platform admin may disable the feature globally without deleting records.
- Headless clients exchange the one-time-displayed client ID/secret through the
  OAuth `client_credentials` grant for the same short-lived, resource-bound
  access token format. They never receive refresh tokens and cannot enter the
  browser authorization-code flow.

## 10. Authorization Design

### 10.1 Subject Types

- human user;
- workspace group (locally managed in MVP);
- OAuth delegated grant (user plus client and approved scope);
- service principal;
- internal job actor carrying originator/resource context;
- platform system actor for narrow maintenance operations.

Platform role never becomes a folder ACL principal automatically.

### 10.2 Platform Roles

| Capability | Super admin | Platform admin | Security auditor |
|---|---:|---:|---:|
| Bootstrap/recover super admins | yes | no | no |
| Manage platform admins/auditors | yes | no | no |
| Manage users and sessions | yes | yes | read audit only |
| Create/archive/delete workspaces | yes | yes | no |
| Assign workspace admins | yes | yes | no |
| Manage model gateways/secrets/profiles | yes | yes | config metadata only |
| Manage OAuth client policy | yes | yes | read only |
| Manage jobs/system settings | yes | yes | read health only |
| View platform audit | yes | policy-limited | yes |
| Read workspace content by platform role | no | no | no |

Any content access by a platform operator requires explicit workspace
membership. Optional emergency access is a separately recorded, reasoned,
time-limited workspace membership grant and never an invisible bypass.

### 10.3 Workspace Roles

| Capability | Workspace admin | Knowledge manager | Editor | Viewer |
|---|---:|---:|---:|---:|
| View/search/ask/download where ACL allows | yes | yes | yes | yes |
| Create/edit/move/delete where ACL allows | yes | yes | yes | no |
| Manage tags | yes | yes | use existing | no |
| Manage folder ACL | yes | yes | no | no |
| Manage members/groups | yes | no | no | no |
| Manage OAuth grants/service credentials | yes | no | no | no |
| View workspace audit | yes | policy-limited | own activity | own activity |
| Assign model profile | no (platform-owned) | no | no | no |

At least one active workspace admin is required. Platform admins can repair
workspace-admin assignment without receiving content permission.

Legacy mapping:

```text
owner, admin -> workspace_admin
member       -> editor
guest        -> viewer
```

### 10.4 Folder ACL

Resource actions:

```text
view_metadata, view_content, download, ask,
create_child, edit, move, delete, manage_acl
```

Rules:

- Root folder always has an independent ACL seeded from workspace roles.
- Child folders inherit the nearest independent ACL by default.
- Breaking inheritance copies the current effective entries as an editable
  starting point; saving creates a replacement ACL, not scattered overrides.
- Entries grant actions to workspace role, group, user, or service principal.
- MVP has no explicit deny entries. Removing a grant or breaking inheritance is
  the restriction mechanism; this avoids allow/deny precedence ambiguity.
- `ask` requires `view_content`; citations require `view_metadata` and
  `view_content`; download additionally requires `download`.
- File and note ACLs follow their folder in MVP. Moving an object changes its
  ACL anchor atomically with the move.
- Unauthorized folders, names, breadcrumbs, result counts, and tag associations
  are treated as nonexistent.

### 10.5 Efficient Evaluation

Use normalized ACL entries and two structural helpers:

- `folder_closure(ancestor_id, descendant_id, depth)` for subtree/scope checks;
- `acl_anchor_id` on folders/documents pointing to the nearest independent ACL.

This avoids materializing every user-resource pair. A set-based query joins:

```text
actor workspace membership and groups
  x resource acl_anchor_id
  x matching role/user/group grants
  x delegated OAuth or service-principal scope roots/actions
```

The policy service owns query builders for accessible folders/documents/chunks.
Single-object checks and collection filters use the same SQL predicates. A
policy contract test executes every action across REST, search, RAG, download,
SSE, job, OAuth, service credential, and MCP paths.

## 11. Target Data Model

The list below names ownership and critical fields, not every audit timestamp.

### 11.1 Identity And Platform

- `users`: local identity, state, display fields, password hash/version, TOTP
  state, security stamp.
- `sessions`: opaque digest, user, idle/absolute expiry, last activity, source
  metadata, revocation.
- `recovery_codes`: user and one-time digest.
- `platform_role_assignments`: user, role, grantor.
- `system_settings`: typed/versioned settings, never arbitrary public JSON.

### 11.2 Workspaces And Authorization

- `workspaces`: id, name, lifecycle state, storage policy, created by platform
  actor. No owner, plan, price, payment, or commercial quota.
- `workspace_members`: workspace, user, role, state, joined/disabled timestamps.
- `workspace_groups`, `workspace_group_members`.
- `folders`: id, workspace, parent, name, ordering, lifecycle, `acl_anchor_id`.
- `folder_closure`: workspace, ancestor, descendant, depth.
- `folder_acls`: id, folder, version, independent marker.
- `folder_acl_entries`: ACL, subject type/id, action bit set.
- `tags`, `document_tags`.

### 11.3 Knowledge

- `documents`: id, workspace, folder, kind (`file` or `note`), title, lifecycle,
  current version, ingestion summary, created/updated actors.
- `document_versions`: immutable version, source blob, MIME, size, checksum,
  Markdown/text content for notes/extracted content, parser version, source
  metadata, created actor/time.
- `blobs`: object key, checksum, size, reference state, scan/validation state.
- `ingestion_jobs`: document version, state, stage, attempt, progress, safe
  error, timestamps, idempotency key.
- `chunks`: document version, ordinal, text, token count, page/sheet/slide,
  start/end offsets, FTS vector, embedding vector and model/dimension.

`documents` are stable identities. Search and citations point to an immutable
`document_version` and chunk so an answer remains explainable after reindexing.

### 11.4 Conversations

- `conversations`: workspace, owner user, capability profile, title, lifecycle;
  private by default and outside the knowledge folder tree.
- `messages`: conversation, role, content, status, sequence, model profile
  version, safe error, usage.
- `message_citations`: message, document/version/chunk, quote and rank.
- `answer_runs`: question, retrieval/model status, timings, profile versions,
  knowledge-gap marker, origin (web/MCP).

Conversation text is excluded from knowledge retrieval in MVP.

### 11.5 Models

- `model_gateways`: admin metadata, base URL, TLS/egress policy, encrypted secret
  reference, enabled/health state.
- `models`: gateway, remote name, capability (`chat`, `embedding`, `rerank`),
  dimension/limits, enabled state.
- `capability_profiles`: business alias, purpose, selected models, prompt/policy,
  retrieval parameters, timeouts, limits, version, enabled state.
- `workspace_profile_assignments`: workspace, workflow, profile version.

No model/provider records live in the knowledge tree. Secrets never appear in
frontend DTOs, logs, audit detail, generated config, or MCP output.

### 11.6 OAuth, Agents, And Audit

- `oauth_clients`: client identity, metadata source, redirect URIs, policy,
  registration/admin approval state.
- `oauth_authorization_codes`: short-lived one-time digest and binding data.
- `oauth_grants`: user, client, workspace, scopes, expiry/state.
- `oauth_grant_roots`: grant and folder root.
- `oauth_access_tokens`, `oauth_refresh_tokens`: digest/family, binding,
  expiry/revocation/reuse state.
- `service_principals`, `service_principal_roots`, `service_credentials`.
- `audit_events`: append-only actor, auth context, action, resource references,
  result, safe reason, correlation ID, source/time. Secret and content bodies are
  excluded.

## 12. Core Knowledge Flows

### 12.1 Upload And Ingestion

1. User requests an upload ticket for a permitted folder with name, MIME, size,
   checksum when available, and idempotency key.
2. API checks `create_child`, storage policy, extension/MIME/size, and creates a
   pending document/version/blob plus a short-lived S3 upload instruction.
3. Browser uploads directly to S3 when configured; small deployments may proxy
   bounded uploads through API.
4. Browser calls complete. API verifies object metadata/checksum and enqueues
   one durable ingestion job.
5. Worker rechecks document state, reads the object, applies parser limits,
   normalizes text with source locations, creates chunks transactionally, and
   batches embeddings through the assigned profile.
6. Version becomes ready only after searchable chunks commit. Keyword-ready but
   embedding-degraded is an explicit state, not a hidden exception.
7. SSE/polling shows queued, parsing, embedding, ready, degraded, or failed with
   a safe retry action.

Reparse creates a new immutable version. Successful activation swaps
`current_version_id`; old versions remain according to retention policy.

### 12.2 Search

1. Resolve workspace/folder/tag filters and actor scope.
2. Build permitted document/chunk relation in SQL before ranking.
3. Run FTS and pgvector candidates only against permitted rows.
4. Fuse normalized ranks, optionally rerank permitted text through the intranet
   gateway, apply threshold, and group duplicates.
5. Return title/path/snippet only for permitted documents.

No result-count side channel is returned for inaccessible rows.

### 12.3 Grounded Ask

1. Authenticate actor and require `ask` plus content visibility.
2. Persist question/answer-run context and resolve the workspace's administrator
   assigned capability profile.
3. Retrieve permitted chunks as above.
4. If none meet policy, emit the fixed knowledge-gap answer without calling the
   chat model.
5. Construct a bounded prompt containing numbered, versioned sources and a rule
   to use only supplied knowledge.
6. Stream answer tokens. Persist final answer, profile version, usage, timings,
   and immutable citation links.
7. If chat gateway fails, return a safe failure or citation-backed fallback as
   defined by the profile; never call a public fallback.
8. Before emitting citation details, recheck access. Historical answers hide a
   citation whose document access was later revoked.

## 13. MCP Design

The MCP endpoint exposes the currently promised complete tool set:

```text
kb_list_workspaces
kb_list_dir
kb_get_tree
kb_search
kb_ask
kb_get_note
kb_get_file
kb_list_tags
kb_mkdir
kb_create_note
kb_update_note
kb_upload_file
kb_move
kb_set_tags
kb_delete
```

Rules:

- Tool visibility is derived from token/service-principal scopes; individual
  calls still reauthorize resources.
- `kb_get_file` returns parsed content/metadata plus a short-lived authorized
  download ticket, not object-store credentials.
- `kb_upload_file` uses bounded inline content only for small payloads. Larger
  payloads use an upload-ticket resource/link flow documented for clients.
- `kb_delete` moves to trash; permanent deletion is not an Agent tool.
- Every call has validated schema, stable machine-readable errors, timeout,
  cancellation, correlation ID, rate/concurrency limit, and audit event.
- Read and write tools call application services used by REST. No SQL or S3 code
  exists in MCP handlers.
- Contract tests use the official SDK and cover OAuth discovery/PKCE, service
  credential auth, read/write tool lists, folder bounds, ACL changes, revocation,
  expiry, malformed input, cancellation, and protocol-version behavior.

The MVP pins and advertises one tested MCP specification revision. The Python
and TypeScript interoperability clients are upgraded and pinned together; a
protocol upgrade is a contract change with a full authorization test run.

## 14. Model Governance

Platform administrators manage four layers:

1. Gateway: intranet endpoint, secret, TLS, allowed capabilities, health.
2. Model: remote name, capability, limits, embedding dimension, enabled state.
3. Capability profile: business workflow and safe parameters.
4. Workspace assignment: which profile version serves each workflow.

Administration workflow is complete only when it supports create, validate
connectivity, edit, disable, rotate secret, view safe health, publish new profile
version, assign workspaces, identify affected indexes, trigger controlled
reindex, and audit every change.

Ordinary users see only business workflow names and availability. They cannot
override model, endpoint, prompt policy, temperature, top K, threshold, chunk
size, embedding, rerank, or provider headers.

Secret storage uses envelope encryption with an environment/secret-manager
master key and per-record nonce/version. Rotation supports decrypt-old and
encrypt-new during a bounded transition. APIs return only presence/fingerprint,
never ciphertext or raw value.

## 15. Audit, Observability, And Operations

### 15.1 Audit

Minimum audited actions:

- login success/failure, logout, password/TOTP/session changes;
- user/role/workspace/member/group lifecycle;
- folder ACL changes and permission-sensitive moves;
- upload, download ticket, create/edit/delete/restore/reparse;
- search and Ask metadata (not full query/body by default);
- OAuth consent/token/refresh/revoke and service credential lifecycle;
- every MCP tool call;
- model gateway/profile/assignment/secret changes;
- job retry/cancel and migration/operator actions.

Audit is append-only to application roles, cursor-paginated, retention-managed,
and exportable by authorized auditors. Sensitive content, password, TOTP, OAuth
code/token, API key, model key, and raw Authorization headers are always redacted.

### 15.2 Telemetry

- Structured JSON logs with correlation, actor kind/ID, route/tool, workspace,
  result, duration, and safe error code.
- Metrics: request/SSE/MCP rate and latency, auth failures, policy denials,
  ingestion queue age/failures, parser time, chunks, embedding/rerank/chat
  latency/failures, token usage, search/Ask knowledge gaps, S3 errors, DB pool.
- OpenTelemetry traces across API, task enqueue/worker, model gateway, DB, and
  S3 with prompt/document contents excluded.
- `/health/live`, `/health/ready`, and worker heartbeat/job-lag checks.

### 15.3 Backup And Restore

- PostgreSQL point-in-time or scheduled backups plus tested restore procedure.
- Versioned S3 bucket or coordinated object backup.
- Restore validation reconciles blob references, document versions, chunks,
  ACL anchors, grants, and audit sequence.
- Secrets/master keys have a separate protected recovery procedure.

## 16. Migration And Compatibility

### 16.1 Strangler Boundaries

Run the Python API alongside Bun during migration behind Caddy. Route one
versioned slice at a time. Do not dual-write the whole legacy model indefinitely.

Suggested slice order:

1. Python foundation, auth read compatibility, platform administration shell.
2. Workspace/member/group and authorization model.
3. Folder/document read APIs and frontend server-state replacement.
4. Upload/ingestion/search/RAG.
5. conversations and complete Ask UI.
6. OAuth/service principals/MCP.
7. final writes, data cutover, Zero and Bun removal.

### 16.2 Data Transformation

Key mappings:

```text
Better Auth user/account/TOTP -> users/local credentials/TOTP
workspace                    -> workspaces (drop plan/payment/quota ownership)
member roles                 -> workspace_members mapped roles
entity folder                -> folders
entity item + item/blob       -> documents/document_versions/blobs
item with note marker/text    -> note document/current version
chat/message                  -> private conversations/messages where retained
entity.conf.tags              -> tags/document_tags
entity.conf.acl               -> folder_acls/folder_acl_entries
connector                     -> service principal + credential/root scope
chunk JSON embedding          -> chunks pgvector, normally rebuilt
platform provider/model       -> gateway/model/profile after admin validation
page/pagePatch                -> note conversion only when live data exists;
                                otherwise archive/report then delete
plan/price/order/payment/etc. -> no target table
channel/translation/mcpPlugin/pubRoot/search records -> no target table
```

Migration preserves user/workspace/folder/document IDs. It records a mapping
table for transformed or invalid IDs. Blob object keys are reused when checksums
and metadata verify; no blind copy is required.

Passwords are migrated only if the stored Argon2id PHC format verifies in the
Python implementation; otherwise affected users enter a forced reset path.
Legacy sessions are not migrated. TOTP secrets are migrated only after a format
compatibility test; recovery codes are reissued.

### 16.3 Final Cutover

1. Announce maintenance and block legacy writes.
2. Take database/object inventory and backup.
3. Run resumable final delta import.
4. Rebuild closure/ACL anchors, FTS, and pgvector indexes.
5. Run count/checksum/relationship/permission equivalence reports.
6. Execute smoke journeys as platform admin, workspace admin, editor, viewer,
   restricted user, OAuth Agent, and service Agent.
7. Switch Caddy `/api` including `/api/mcp` to Python and deploy the final Vue
   build.
8. Keep legacy services and tables read-only for the rollback window.
9. After acceptance and backup, delete Zero/Bun services, legacy tables/code,
   dependencies, configuration, and compatibility routes in a named cleanup
   migration.

Rollback before cleanup switches Caddy and frontend artifact back and restores
the final legacy-write snapshot if any Python writes occurred. After cleanup,
rollback is database/object restore plus previous deployment, not an ad hoc
schema downgrade.

## 17. Security Boundaries

- Caddy exposes only the SPA, versioned API, MCP, OAuth metadata/endpoints, and
  health endpoints appropriate to the network.
- Admin routes share the API origin but require platform capabilities.
- Object storage is private. Every download uses a short expiry after policy
  check and safe content disposition.
- Model gateway/S3/SMTP destinations are parsed structured URLs and checked
  against administrator allowlists; redirects and DNS/IP changes cannot escape
  the configured intranet policy.
- Request, upload, extracted text, archive, chunk, prompt, model output, and SSE
  sizes are bounded.
- HTML/Markdown rendering is sanitized; filenames and content disposition are
  safe; SVG preview is isolated or sanitized.
- Database users are least privilege; migration and application credentials are
  separate. Application SQL uses parameters.
- Dependency lockfiles, image scanning, SBOM, and pinned base images are part of
  release verification.

## 18. Test Strategy

### 18.1 Backend

- Unit: policy resolution, inheritance, scope intersection, token lifecycle,
  chunking, fusion, citation mapping, parser normalization, state machines.
- Integration: PostgreSQL extensions/indexes, repositories, migrations, task
  retries/idempotency, S3/MinIO, gateway fakes, session/CSRF.
- Contract: OpenAPI snapshots/generated client, Problem Details, pagination,
  ETag/idempotency, SSE event schemas, MCP official client.
- Security matrix: every subject/role/action/resource path over REST, search,
  RAG, download, SSE, OAuth, service principal, worker, and MCP.
- Migration: representative legacy fixtures containing every retained and
  removed table/type, malformed/conflicting rows, ACL trees, blobs, passwords,
  TOTP, connectors, pages, and commercial residue.

### 18.2 Frontend

- Component tests for permission-aware controls, forms, upload state, citations,
  consent, credential one-time display, and errors.
- Integration tests against generated API mocks for cache invalidation and SSE.
- Playwright journeys for every role at desktop and mobile widths.
- Accessibility checks for keyboard navigation, focus, labels, dialogs, contrast,
  reduced motion, and screen-reader status updates.
- No hidden-button test counts as authorization proof; server rejection is
  asserted separately.

### 18.3 Completeness And Deletion Gates

Each slice defines:

- positive, empty, loading, error, retry, permission, cancellation, concurrent,
  and recovery behavior;
- API/UI/job/audit/deploy/documentation completion;
- searches for legacy symbols/routes/env/dependencies;
- unused dependency and dead-code checks;
- production builds and clean-install/clean-database smoke test.

## 19. Explicitly Removed Target Concepts

The final product has no:

- payment, plan, price, order, purchase, commercial quota, or cost UI/domain;
- public publishing, public knowledge marketplace, web search/crawl, Jina page
  fetch, GitHub gread, translation, channels/IM, MCP client/plugin marketplace;
- complex TipTap/CRDT/page-patch editor;
- user/workspace-created provider gateway or exposed provider credential;
- browser-side direct model provider call;
- Zero cache, Zero query/mutate endpoint, replica database, generated Zero
  schema, or shared frontend/server mutator;
- automatic personal workspace creation;
- network endpoint for first-admin promotion;
- placeholder pages or tools for accepted MVP capabilities.

## 20. Deferred Without Changing MVP

The following are excluded rather than partially implemented:

- direct LDAP/AD authentication and automatic directory group synchronization;
- OCR, speech transcription, and video indexing;
- public Internet connectors or MCP client/marketplace;
- collaborative rich-text editing;
- conversation text as retrieval corpus;
- cross-workspace/global knowledge search;
- mobile native clients;
- microservice decomposition.
