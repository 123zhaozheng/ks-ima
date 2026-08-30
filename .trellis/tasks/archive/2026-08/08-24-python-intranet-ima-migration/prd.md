# Plan Python Backend Migration for Intranet IMA

## Goal

Produce an evidence-backed, implementation-ready migration plan that turns the
current Nya AI codebase into a self-hosted intranet knowledge assistant with a
Python backend and a separately deployed conventional web frontend. The product
must keep its core RAG and MCP capabilities, simplify end-user workflows, and
provide centralized administration and complete authorization without retaining
commercial plans or per-user infrastructure configuration.

## Background

- The planning baseline is commit `6afe5aa` on branch `feat/intranet-ima`.
- Recent work already moves the product toward an intranet IMA: knowledge
  ingestion and grounded answers, citations, MCP dispatch, entity ACLs, and
  centralized model configuration were added while payment, plans, public
  publishing, and several complex content/editor experiences were removed.
- The current application is primarily a Bun/TypeScript monorepo with Vue 3,
  Quasar, Hono, Drizzle, Rocicorp Zero, Better Auth, PostgreSQL, S3-compatible
  storage, AI SDK integrations, and MCP SDK integrations.
- This task is for repository analysis and migration planning. Product code
  migration requires a later, explicit approval after the final plan review.

## Requirements

### R1. Repository Evidence

- Build a fresh full CodeGraph index before architectural analysis.
- Read the complete repository at architectural depth, including source,
  schemas, migrations, tests, configuration, deployment files, documentation,
  recent commits, and the uncommitted-to-baseline change history.
- Document the current frontend, backend, data, authentication, authorization,
  RAG, MCP, model-provider, storage, job, synchronization, and deployment flows.
- Classify existing capabilities as retain, replace, simplify, migrate, or
  remove, with evidence and dependencies for each decision.

### R2. Target Product

- Target a private/internal IMA-like knowledge assistant rather than a
  commercial multi-tenant AI workspace.
- Preserve the core knowledge workflow: organize internal materials, upload and
  parse files, retrieve relevant passages, generate grounded answers, and show
  usable citations.
- Preserve MCP as an administrator-governed extension capability with a simple
  end-user experience.
- Keep chat, knowledge discovery, and content access approachable for ordinary
  internal users; infrastructure details must not leak into normal workflows.
- Remove subscriptions, pricing, orders, quotas tied to plans, payment
  providers, and other commercialization concepts from the target architecture.

### R3. Backend And Frontend Separation

- Replace the Bun/Hono application backend with a Python backend whose framework
  and internal boundaries are justified from repository evidence and target
  requirements.
- Retain Vue 3 + TypeScript as an independently built and deployed web
  application. Replace Rocicorp Zero with explicit REST/JSON APIs, SSE for
  streamed chat and job progress, and a conventional server-state layer.
- Preserve reusable knowledge workflows and components while allowing the
  visual system and component library to be adjusted when the user supplies the
  intended UI direction.
- Define explicit versioned API, streaming, authentication, error, pagination,
  file-transfer, and background-job contracts between frontend and backend.
- Produce a migration strategy that permits verification and rollback by phase
  rather than relying on a single big-bang replacement.

### R4. Centralized Administration

- One installation may contain multiple department or project workspaces.
- Only platform administrators may create, archive, restore, or permanently
  delete workspaces. Registration or account creation must not automatically
  create a personal workspace.
- Workspace administrators manage membership, directory authorization, content
  governance, tags, and connectors inside workspaces assigned to them. Platform
  administrators do not gain content-read permission merely by holding a
  platform role.
- Only authorized administrators may configure model providers, credentials,
  model catalogs, embedding/reranking/chat defaults, MCP service policy, global
  system settings, and other infrastructure-level integrations.
- Ordinary users select only from administrator-approved capabilities when a
  product workflow genuinely needs a choice; they never enter provider keys,
  endpoints, model names, or low-level model/RAG parameters.
- Platform administrators publish business-facing capability profiles such as
  grounded knowledge Q&A, title generation, summarization, embedding, and
  reranking. A profile owns the underlying model, prompt/policy, limits, and
  parameters.
- Workspaces bind only to administrator-approved profiles. Ordinary users do
  not select a model per chat; the workflow and workspace policy resolve the
  profile automatically.
- Administrative changes must be validated, auditable, secret-safe, and usable
  without editing environment files for routine operations.

### R5. Authorization

- Design a complete authorization model covering at least platform operations,
  workspace membership, knowledge folders/documents, chats, MCP tools, model
  usage, connectors, administrative settings, and audit access.
- Define built-in roles, permission actions, resource scopes, inheritance,
  ownership, explicit grants, inheritance replacement without explicit deny in
  the MVP, and enforcement points.
- Authorization must be enforced server-side for every read, mutation, search,
  retrieval, file access, streamed response, background job, and tool execution;
  frontend visibility is only a usability layer.
- The design must include auditability, least privilege, account lifecycle,
  session/security controls, and a safe bootstrap/recovery path for the primary
  administrator.

### R6. Local Identity And Agent Authorization

- Human users authenticate with application-owned local accounts. The MVP does
  not require OIDC or LDAP login.
- The product must act as an OAuth 2.1 authorization server for external Agent
  platforms that connect to this knowledge service.
- An interactive Agent connection must use Authorization Code + PKCE: the Agent
  opens an authorization URL, the user signs in locally, reviews the requesting
  client, selects an allowed workspace and optional folder roots, chooses an
  administrator-permitted read or read-write scope, approves, and returns to the
  Agent through its validated redirect URI.
- Publish the authorization-server and protected-resource metadata required by
  standards-compliant MCP/OAuth clients. Define authorization, token, refresh,
  revocation, and client-registration/metadata behavior explicitly in the
  technical design.
- Access and refresh credentials must be stored and handled safely, bound to the
  intended resource/client/grant, scoped to approved workspace/folders/actions,
  revocable immediately, rotated where applicable, and auditable without
  logging credential material.
- A grant's effective permissions are always the intersection of the user's
  current membership and ACL, the approved grant scope, workspace/folder
  boundaries, client policy, and current platform/workspace switches. Demotion,
  removal, account disablement, workspace archival, or grant revocation must
  take effect without waiting for token expiry.
- The consent screen must use resource names and understandable actions; it must
  not expose low-level OAuth, MCP, model, or infrastructure configuration to
  ordinary users.
- Interactive OAuth is the default Agent connection experience. In addition,
  authorized administrators may create service credentials for unattended
  Agents, server scripts, and scheduled jobs that cannot complete a browser
  consent flow.
- Service credentials are distinct service principals rather than disguised
  user sessions. Creation must require an explicit workspace, optional folder
  roots, an action scope, owner, purpose, expiry, and rotation policy. Secrets
  are displayed once, stored only as non-reversible hashes where possible, and
  support immediate revocation.
- OAuth grants and service credentials must use the same policy service and MCP
  application operations; neither transport may expose a broader or different
  tool implementation.

### R7. Operations And Migration

- Define target persistence, vector retrieval, object storage, task execution,
  configuration, secret management, observability, backup/restore, health
  checks, deployment, upgrade, and rollback approaches suitable for an intranet.
- Provide a data migration map from existing PostgreSQL/Drizzle/Zero/Auth data to
  the target Python-owned schemas, including compatibility risks and validation.
- Separate MVP requirements from later enhancements and identify decisions that
  can be deferred without changing MVP behavior.
- Break implementation into independently verifiable phases with dependencies,
  acceptance gates, validation commands, risky areas, and rollback points.

### R8. Completeness And Code Removal

- Every capability accepted into the MVP scope must be implemented end to end:
  persisted data, backend policy and business logic, API contract, frontend
  workflow, loading/empty/error/permission states, audit behavior, tests,
  deployment configuration, and operator documentation where applicable.
- Placeholder pages, TODO-only handlers, mock responses, hard-coded success
  paths, disabled validation, unimplemented protocol branches, and undocumented
  manual database fixes do not satisfy an acceptance criterion.
- Each migration phase must remove the code it replaces after its cutover gate:
  obsolete routes, tables, generated schemas, shared mutators, components,
  stores, dependencies, environment variables, jobs, localization keys,
  migrations/bootstrap logic, and deployment services must not remain merely
  because deletion is inconvenient.
- Removal must be evidence-driven. Shared utilities or compatibility paths may
  remain only while a named consumer or rollback window still needs them; the
  implementation plan must identify their owner and deletion milestone.
- A phase is not complete until repository searches, dependency analysis,
  builds, tests, and migration checks prove that removed concepts have no live
  references and all in-scope user journeys are functional.

## Acceptance Criteria

- [ ] A fresh full CodeGraph index exists and is used to trace key call and data
      paths rather than relying only on filename inspection.
- [ ] The current-state architecture inventory covers every top-level subsystem
      and cites concrete repository files, routes, schemas, and entry points.
- [ ] A capability disposition matrix explains what is retained, replaced,
      simplified, migrated, or removed and why.
- [ ] `design.md` specifies the target Python/backend and frontend architecture,
      service boundaries, contracts, data flows, security boundaries, and
      deployment topology.
- [ ] The authorization design includes a permission matrix, inheritance and
      ownership semantics, administrator boundaries, enforcement locations, and
      audit requirements.
- [ ] A standards-compliant external Agent can open an authorization link,
      complete local login and scoped consent, exchange the code with PKCE,
      refresh access, call permitted MCP tools, and lose access immediately when
      the grant or underlying human authority is revoked.
- [ ] RAG, ingestion, citations, model governance, and MCP execution each have an
      end-to-end target flow and migration mapping from the current code.
- [ ] Commercialization and per-user infrastructure configuration are explicitly
      absent from the target architecture and migration scope.
- [ ] `implement.md` contains a detailed ordered roadmap with dependencies,
      verification gates, data migration, coexistence/rollback strategy, and
      explicit MVP versus deferred scope.
- [ ] Every implementation phase defines both a feature-completeness checklist
      and a deletion checklist for the legacy code it replaces.
- [ ] The final target contains no live Zero runtime, Bun/Hono backend, plan or
      payment domain, user-managed provider credentials, removed entity types,
      placeholder implementations, or compatibility shims whose documented
      rollback window has expired.
- [ ] All user-owned product decisions that materially affect architecture are
      resolved, and no blocking planning question remains.
- [ ] The final PRD passes a lossless convergence review with no duplicated or
      unresolved brainstorm sections.

## Out Of Scope

- Implementing the Python backend or rewriting the frontend during this planning
  task.
- Commercial billing, subscriptions, pricing tiers, purchases, or usage plans.
- Allowing ordinary users to add arbitrary model providers, credentials, MCP
  servers, or deployment-level configuration.
- Pixel-level UI design before the user supplies the intended visual direction;
  the plan may define information architecture and workflow requirements.
- Direct LDAP/AD login in the MVP; local login is complete and Agent OAuth is a
  resource authorization flow rather than an enterprise SSO login.
- OCR, speech transcription, video indexing, conversation-as-knowledge,
  cross-workspace global search, rich-text collaboration, native mobile clients,
  microservices, public-network connectors, and an MCP client/marketplace.
