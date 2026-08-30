# Current-State Architecture Research

## Evidence Baseline

- Branch: `feat/intranet-ima`
- Migration-planning baseline: `6afe5aa`
- Product direction commit: `b8785da`
- First implementation commit: `8e0575a`
- CodeGraph project: `D-code-python-nyaai`
- Full index: 5,137 nodes, 7,780 edges, 635 functions, 64 detected
  routes, 1,128 call edges, and 905 import edges.
- Product source: 278 TypeScript/Vue/JavaScript files and approximately
  25,077 lines under `src`, `src-server`, and `src-shared`.
- Automated baseline: 16 Bun tests pass. ESLint did not finish within the
  observed wait window and was terminated; its status is unknown.

## Current Runtime Topology

```text
Browser (Vue 3 + Quasar + Pinia + Zero client)
  |-- /api/auth, /api/admin, /api/kb, /api/connectors, /api/mcp
  |-- /api/v1/chat/completions (OpenAI-compatible proxy)
  |-- /api/zero/query + /api/zero/mutate
  `-- /zero-cache websocket/http

Caddy
  |-- user PWA on :8080
  |-- admin SPA on :8081
  |-- reverse proxy to Bun/Hono API
  `-- reverse proxy to Rocicorp Zero cache

Bun/Hono API
  |-- Better Auth + Drizzle
  |-- shared Zero queries/mutators
  |-- RAG, file, MCP, connector, search, and admin routes
  `-- in-process cron/timers

PostgreSQL + zhparser
  |-- product/auth data
  |-- generated tsvector fields
  |-- RAG chunks and JSON embeddings
  `-- materialized entity permissions for Zero

S3-compatible object storage
OpenAI-compatible intranet model gateways
```

Deployment currently requires four runtime services: web/Caddy, Bun API,
Rocicorp Zero, and PostgreSQL, plus external S3-compatible storage. Development
adds MinIO. The target can remove Zero and its replica/CVR/change databases.

## Frontend And Product Workflow

The recent UI has already moved toward a knowledge-drive workflow:

1. The workspace opens on the root folder.
2. The drawer exposes the folder tree, Ask, workspace search, tasks, trash, and
   settings.
3. A folder supports create-folder, multi-file upload, folder upload, drag and
   drop, and Ask.
4. A file view shows parse state, preview, extracted text, metadata, download,
   and reparse.
5. Ask creates a personal chat and calls the knowledge endpoint, then renders
   citations that navigate back to files.
6. Workspace settings contain members, invitations, connectors, and model/RAG
   tuning. A separate admin build manages platform users, workspaces, models,
   and global defaults.

The frontend is deeply coupled to Zero: 145 query/mutation/preload call sites
and 17 core files import Zero directly. The highest-cost boundary is not Vue;
it is the shared `src-shared/mutators.ts` (about 1,418 lines), generated Zero
schema (about 2,480 lines), query definitions, optimistic local mutation
behavior, and entity-derived stores.

Recommendation evidence: retain Vue 3 + TypeScript initially, replace Zero with
explicit HTTP/SSE contracts and TanStack Query or an equivalent server-state
layer, then apply the new UI system after workflow migration. A framework
rewrite would combine backend, data, state, and visual rewrites in one cutover.

## Data Model

The current schema still mixes the original commercial workspace with the new
knowledge product:

- Core identity: Better Auth `user`, account, session, verification, two-factor.
- Collaboration: `workspace`, `member`, `workspaceInvitation`.
- Generic tree: `entity` with `rootId`, `parentId`, `type`, name, JSON `conf`,
  hidden/sort fields, and the obsolete `pubRoot`.
- Knowledge/content: `item`, blob, chunk, page/pagePatch, chat/message/toolCall,
  provider/model/assistant, shortcut/search.
- New security: `entityPermission` and `connector`.
- Commercial residue: plan, planPrice, order, payment/quota/reset fields, model
  prices, cost-based usage, and free-model limits.
- Removed-feature residue: page/pagePatch, channel, translation,
  translationRecord, mcpPlugin, publication fields, providers/assistants in the
  content tree, and their generated Zero contracts.

Workspace creation still creates system folders and shortcuts for search,
pages, assistants, providers, and files, and still assigns a default plan and
quota lifecycle. User creation automatically creates a personal workspace.

## Authentication And Administration

- Better Auth provides email/password, Argon2id using Bun, email verification,
  reset email, TOTP, session cookies, and platform admin operations.
- The admin application attempts `POST /admin/aquireRole` when its logged-in
  user is not an admin. The endpoint promotes the caller only if no admin exists.
- Platform administrators can manage users, sessions, bans, passwords,
  workspaces, platform models, and global settings.
- Platform admin status is separate from workspace membership. Existing PRD
  correctly states that platform admins must not automatically read workspace
  content.
- Routine model configuration is split: platform admins configure public
  models, while workspace owner/admin users may create provider gateways,
  credentials, chat/embedding/rerank choices, chunking, fusion, threshold, and
  reindex settings. This conflicts with the requested centralized governance.

Target implications:

- Replace the public first-admin acquisition endpoint with an explicit CLI or
  one-time bootstrap secret.
- Preserve local accounts for bootstrap/recovery; add OIDC/LDAP as a separately
  deployable identity adapter.
- Use secure server-owned sessions and CSRF protection for browser mutations.
- Move provider credentials, model registration, and low-level RAG settings to
  platform administration. Workspaces consume published policies/profiles.

## Current Authorization Model

The repository has three parallel authorization representations:

1. `src-shared/utils/acl.ts` computes actions from workspace role and the nearest
   ancestor whose ACL sets `inherit=false`.
2. `src-server/utils/permissions.ts` recursively loads ancestors for session or
   connector actors and enforces connector folder/read-write constraints.
3. The ACL migration duplicates the algorithm in PostgreSQL functions and
   materializes `entityPermission` rows for Zero read filtering.

Actions are `view`, `ask`, `edit`, `delete`, and `manage`. Default roles are
owner, admin, member, and guest. Connectors are delegated service principals:
effective authority is the creator's current workspace role/ACL intersected
with connector read/write mode, workspace, folder root, expiry, and revocation.

Positive properties to preserve:

- default deny outside membership and scope;
- invisible/not-found behavior for unauthorized resources;
- `ask` also requires `view`;
- owner cannot be locked out by a folder ACL;
- connector credentials are stored as SHA-256 hashes and shown only once;
- connector authority falls when the creator is removed or demoted;
- search, RAG, file download, MCP, and selected Zero mutations call the common
  permission layer.

Gaps and risks:

- TypeScript, SQL, and Zero copies can drift semantically.
- Recursive per-entity/per-ancestor queries create poor scaling behavior.
- The materialization trigger rebuilds an entire workspace after moves or ACL
  changes, increasing lock and write amplification risk.
- `withWritable` still uses broad roles rather than the materialized edit bit;
  only a subset of shared mutators is wrapped by server ACL checks.
- ACL UI can configure only guest actions and a raw user ID; it lacks user/group
  discovery, a complete matrix, explanation, preview, and safe bulk behavior.
- No group/department principal, explicit resource policy version, audit event,
  emergency access workflow, or systematic authorization test matrix exists.

## RAG And File Ingestion

Current flow:

```text
upload metadata -> S3 upload -> parse queued in entity.conf
  -> in-process timer/cron -> fetch object -> parse
  -> split text -> optional embedding gateway -> chunk rows
  -> keyword/vector retrieval -> ACL before rerank/prompt
  -> optional rerank -> grounded model answer -> citations
```

Implemented parsing covers plain text/Markdown/JSON, PDF, DOCX, XLSX, and PPTX.
Images/audio/video are stored but not text-extracted. Chunking, overlap, top K,
threshold, hybrid weighting, embedding model, rerank model, and chat model are
workspace-tunable. Model gateways are OpenAI-compatible and intended to be
intranet-only.

Valuable behavior to port:

- empty retrieval returns a fixed knowledge-gap answer without model use;
- gateway failure returns citation-backed fallback rather than public fallback;
- cited context is explicitly passed with a grounded-answer instruction;
- unauthorized chunks are filtered before reranking or prompt construction;
- keyword-only fallback works when embeddings are unavailable;
- citation payload contains entity, title, path, quote, and score.

Replacement needs:

- durable idempotent jobs with retry, dead-letter state, concurrency limits, and
  worker health instead of an in-memory `Set` and timers;
- typed ingestion/version/status tables instead of JSON `entity.conf` flags;
- pgvector columns and HNSW/IVFFlat indexes instead of JSON vectors and scanning
  up to 8,000 chunks in application memory;
- stable citation identity including document version, chunk, page/sheet/slide,
  and character offsets;
- parser sandboxing/limits, MIME verification, archive-bomb protection, and
  malware scanning hooks;
- batched SQL authorization joins instead of enumerating every visible entity.

## MCP And Connectors

The current product already provides a stateless official-SDK Streamable HTTP
MCP server at `/api/mcp`. Read keys expose eight tools and read-write keys expose
seven more:

- discover/read: list workspaces, list directory, get tree, search, ask, get
  note, get file, list tags;
- write: mkdir, create/update note, upload, move, set tags, delete to trash.

The same `kb/ops.ts` operations back Web and MCP routes. Tests validate SDK
handshake, tool visibility, cross-workspace rejection, folder-root rejection,
revocation, expiry, and read/write tool sets.

Target implications:

- Keep the official Python MCP SDK and Streamable HTTP.
- Make MCP a thin transport adapter over application services; do not duplicate
  business logic in tool handlers.
- Replace base64 file upload with an upload-ticket or multipart flow for large
  files while retaining small-text note tools.
- Add per-key rate/concurrency limits, audit events, last-used metadata,
  optional IP/network policy, structured error codes, protocol/version tests,
  and immediate revocation checks.
- Do not add an MCP client, marketplace, proxy, or public-network tool.

## Search, Chat, And Model Calls

There are currently two model execution paths:

- Browser AI SDK -> `/api/v1/chat/completions` -> configured upstream gateway.
- Server RAG -> direct chat/embedding/rerank gateway calls.

The chat proxy still contains free-model rate limits, plan quotas, token prices,
workspace cost accumulation, and public-model semantics. The browser still has
provider conversion logic for user/workspace providers. Target architecture
should make all inference server-side through a model gateway abstraction and
publish only safe model aliases/capabilities to the frontend.

## Recent Change Disposition

Already substantially implemented and reusable as behavior/specification:

- simplified folder/file/Ask information architecture;
- file parsing and preview;
- knowledge retrieval and grounded citations;
- server-side MCP and connectors;
- folder ACL semantics and permission smoke tests;
- removal of visible payment, plans, publishing, translation, channel, complex
  TipTap/editor, and MCP-client experiences;
- platform and workspace model settings pages.

Incomplete or inconsistent and therefore migration inputs, not target code:

- obsolete tables, types, queries, mutators, system folders, localization keys,
  quota jobs, and admin plan components;
- user/workspace provider configuration and browser-side model execution;
- Zero-specific permission materialization and shared mutator architecture;
- production-ready background processing, vector indexing, audit, secret
  encryption, outbound-network enforcement, and operational health.

## Planning Conclusions

1. The domain should remain a modular monolith for the MVP: one Python API
   deployable plus one worker deployable sharing application/domain modules.
   RAG, MCP, administration, and identity are modules, not microservices.
2. PostgreSQL remains the transactional source of truth and should gain
   `pgvector`; S3-compatible storage remains the blob layer.
3. Zero should be removed. Explicit REST/JSON APIs, SSE for chat/job events, and
   short polling where sufficient are easier to authorize, test, and operate.
4. Vue 3 + TypeScript will be retained. Zero and its generated/shared data layer
   will be replaced with explicit REST/SSE contracts and conventional
   server-state management.
5. Authorization must have one policy service and one set-based SQL projection
   strategy, with all transports calling the same application services.
6. Platform-admin capability and workspace-content capability must remain
   separate. Central administrators govern infrastructure without implicit
   knowledge access.
7. The migration should use a strangler approach and a short final write freeze,
   preserving IDs and old tables for rollback rather than dual-writing two
   structurally different content models for a long period.
8. Completeness and deletion are hard delivery gates: no in-scope placeholder
   behavior is acceptable, and replaced code/data/configuration must be removed
   after its named cutover and rollback window.
9. Workspace governance will remain multi-workspace but centrally controlled:
   platform administrators alone own workspace lifecycle; workspace
   administrators own membership, ACL, content, tags, and connectors; account
   creation does not create a personal workspace; platform roles do not imply
   content access.
10. Human identity will use local accounts for the MVP. External Agent
    platforms will connect through a first-class OAuth 2.1 Authorization Code +
    PKCE consent flow backed by local login, MCP authorization metadata, scoped
    grants, refresh/revocation, and dynamic reduction against the approving
    user's current knowledge permissions.
11. Agent authentication will be dual-mode: interactive clients use OAuth by
    default; administrators may issue tightly scoped, expiring, rotatable
    service-principal credentials for unattended Agents and scripts. Both modes
    call the same authorization and MCP application services.
12. Model governance will be profile-based and centralized. Platform
    administrators own gateways, secrets, models, prompts/policies, limits, and
    RAG parameters; workspaces bind approved business profiles; ordinary users
    do not select or configure models per chat.
