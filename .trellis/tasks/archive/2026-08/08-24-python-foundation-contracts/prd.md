# Python foundation and contracts

## Goal

Establish a production-shaped Python API and durable worker foundation that can
run beside the current Bun application, own an isolated target database schema,
publish deterministic versioned contracts to the retained Vue frontend, and
pass clean-install, migration, quality, image, and health checks before any
business feature is migrated.

## Requirements

### R1. Python Project

- Add a locked, reproducible `backend/` Python project using a supported Python
  release, FastAPI/Starlette, Pydantic 2/settings, SQLAlchemy 2 async, asyncpg,
  Alembic, a PostgreSQL-backed task library, structured logging, and pytest
  tooling.
- Use an application factory with no import-time database mutation, seeding,
  migration, job scheduling, or network calls.
- Establish modular boundaries for API, domain, application, infrastructure,
  workers, and tests without creating empty feature-module placeholders.
- Configure Ruff formatting/lint and strict-enough mypy for all new backend code.

### R2. Configuration And Security Baseline

- Parse structured configuration from environment with fail-fast validation for
  environment, public origin, trusted proxies, database, CORS, and logging.
- Secret values must use secret-aware types and never appear in repr, errors,
  health responses, OpenAPI, or logs.
- Add correlation IDs, trusted proxy handling, request body limits, CORS default
  deny, safe exception mapping, and structured JSON logging.
- Use RFC 9457 Problem Details with stable codes for exposed API errors.

### R3. Persistence And Durable Worker

- Create an isolated `ima` PostgreSQL schema so new migrations cannot alter
  current Drizzle/Zero tables during coexistence.
- Configure Alembic with deterministic naming conventions and an explicit
  migration command; API/worker startup must never auto-migrate.
- Enable/check target PostgreSQL extensions required by the approved design,
  including pgvector and the existing mixed/Chinese FTS contract.
- Select and integrate a proven PostgreSQL-backed durable task library after a
  focused compatibility spike. The worker must start, report readiness, enqueue
  and execute an idempotent diagnostic task, retry safely, and survive restart.
- FastAPI `BackgroundTasks`, detached `asyncio` tasks, in-memory queues, and cron
  inside API replicas are forbidden for durable work.

### R4. API And Frontend Contract

- Establish `/api/v1` conventions for IDs, UTC timestamps, cursor pagination,
  Problem Details, ETag/version, idempotency, and SSE event envelopes.
- Add only real foundation endpoints: liveness, dependency readiness, build info,
  and diagnostic worker readiness. Do not add fake business endpoints.
- Export deterministic OpenAPI JSON and generate a TypeScript client into the
  current Vue project.
- Add TanStack Vue Query and a minimal typed system-info query proving browser
  to Python contract generation without migrating product state prematurely.
- OpenAPI drift and generated-client drift must fail validation.

### R5. Coexistence Deployment

- Add non-root multi-stage API and worker images from the same locked revision.
- Add/update local Compose and Caddy routing so Python foundation endpoints run
  beside the current web/Bun/Zero stack without taking over existing
  `/api/v1/chat/completions`.
- Add liveness/readiness and worker heartbeat/queue-lag health behavior.
- Migration runs as an explicit deployment step before readiness, not in every
  replica.
- Preserve a single routing rollback to the legacy runtime.

### R6. Quality And Completeness

- Add unit, integration, migration, contract, worker restart/retry, redaction,
  and container smoke tests appropriate to this foundation.
- Document developer setup, configuration, migration, API/worker start, contract
  generation, and coexistence deployment commands.
- Remove experimental duplicate scaffolds, unused dependencies, generated drift,
  and temporary spike code before acceptance.
- Do not delete active Bun/Zero/product code in this child task.

## Acceptance Criteria

- [ ] A clean checkout installs from lockfiles and passes backend format, lint,
      type, test, Alembic, and contract checks.
- [ ] A clean PostgreSQL instance gains only the target `ima`/job structures and
      required extensions; current public legacy tables remain unchanged.
- [ ] API and worker start independently from one source revision, run as
      non-root containers, and expose accurate liveness/readiness.
- [ ] A durable diagnostic job executes once, retries a controlled failure, and
      resumes after worker restart without duplication.
- [ ] RFC 9457 errors, correlation IDs, CORS, proxy, body-limit, structured-log,
      and secret-redaction behaviors have automated coverage.
- [ ] OpenAPI export is deterministic; the Vue build consumes its generated
      TypeScript client and completes a real system-info request.
- [ ] Caddy routes only named Python foundation endpoints and leaves the current
      Bun chat/API and Zero paths functional.
- [ ] API, worker, frontend, and coexistence Compose images/builds succeed from
      documented commands.
- [ ] No placeholder business modules/endpoints, import-time side effects,
      in-memory durable jobs, duplicate scaffolds, or unused new dependencies
      remain.
- [ ] Existing product tests still pass; legacy product/runtime deletion is zero
      for this phase.

## Out Of Scope

- Migrating identity, workspace, permissions, models, knowledge content,
  ingestion, Ask, OAuth, MCP, or legacy data.
- Moving or redesigning the existing Vue source tree beyond the generated client
  and minimal foundation query.
- Removing Bun, Hono, Drizzle, Better Auth, Zero, or current product routes.
- S3/object-storage client integration, upload/download tickets, and storage
  readiness; these require real document flows and are owned by the later
  `object-storage-durable-ingestion` child task rather than an unused foundation
  dependency.
