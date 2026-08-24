# Python Foundation Technical Design

## Scope Boundary

This child creates real infrastructure and contracts only. It must not add empty
domain packages or fake endpoints to imply that later features exist.

## Directory Shape

```text
backend/
  pyproject.toml
  uv.lock
  alembic.ini
  migrations/
  src/ima/
    main.py                 application factory entry
    config.py               validated settings
    cli.py                  explicit operational commands
    api/
      app.py
      dependencies.py
      errors.py
      middleware.py
      contracts.py
      v1/system.py
    infrastructure/
      db/
        base.py
        engine.py
        health.py
      tasks/
        app.py
        diagnostic.py
      observability/
        logging.py
        telemetry.py
    workers/
      main.py
    tests/
      unit/
      integration/
      contract/
frontend additions stay in the current `src/` tree for this phase.
deploy/
  compose/
  caddy/
```

Only packages with executable foundation behavior are created. Later child
tasks add domain modules when they implement them.

## Runtime Processes

- API: ASGI server imports `ima.main:create_app`; it does not migrate or start a
  scheduler.
- Worker: imports the same settings/database/task infrastructure and consumes
  durable jobs.
- Migration job: invokes Alembic explicitly before a deployment becomes ready.
- Contract command: creates the app without external side effects, exports
  stable OpenAPI, and compares/generates frontend types.

## Database Isolation

- New application tables use PostgreSQL schema `ima`.
- Alembic version state is stored inside the target schema.
- Task-library tables use an explicitly configured target/job schema.
- Runtime connections do not use a database superuser.
- The first migration creates schemas/extensions and a minimal migration marker
  or diagnostic job infrastructure only; it creates no speculative business
  table.
- Integration tests snapshot legacy public table names before/after migration
  and assert no change.

## Configuration

Settings are immutable after application creation and grouped into structured
objects for application, HTTP, database, task queue, logging, and optional
development CORS. Public origin and proxy rules determine generated URLs; raw
forwarded headers are trusted only from configured proxy networks.

Object-storage settings and an S3 adapter are deliberately not created in this
child. They become mandatory with the first real upload/download workflow in the
`object-storage-durable-ingestion` child, where their behavior can be exercised
instead of remaining unused scaffolding.

Production rejects wildcard origins, missing public HTTPS origin when OAuth is
eventually enabled, debug mode, default secrets, and malformed structured URLs.
This phase records but does not require future auth/model/S3 secrets.

## HTTP Contracts

Foundation endpoints:

```text
GET /health/live             process alive, no dependency access
GET /health/ready            database, migration head, worker heartbeat/lag
GET /api/v1/system/info      build/API version and non-sensitive capabilities
POST /api/v1/system/jobs/diagnostic  development/test-only guarded command
GET /api/v1/system/jobs/{id} development/test-only status
```

Diagnostic job endpoints are excluded/disabled in production unless protected
by an operator-only deployment switch. They exist to prove real durability, not
as placeholder business APIs.

Problem Details fields are `type`, `title`, `status`, `detail`, `instance`,
`code`, `correlationId`, and optional normalized field errors. Internal exception
text and configuration values are not returned.

SSE envelope contract is defined centrally and tested but no fake SSE feature is
served in this phase:

```json
{"id":"opaque","type":"namespace.event.v1","occurredAt":"UTC RFC3339","data":{}}
```

## OpenAPI And Vue Integration

- OpenAPI operation IDs are explicit and stable.
- Export normalizes nondeterministic ordering and writes one checked JSON file.
- A single configured generator creates frontend DTO/client files; generated
  files are not hand edited.
- Vue Query uses a central API client and query key for `systemInfo`.
- The UI may expose build/system info only in an existing diagnostics/about
  location, not as a new marketing or placeholder page.

## Durable Task Spike And Selection Gate

Evaluate the planned PostgreSQL-backed library against:

- supported Python and PostgreSQL versions;
- async enqueue and worker execution;
- retry/backoff and scheduled work;
- idempotent job identity;
- schema/table isolation;
- graceful shutdown and crash recovery;
- worker heartbeat/queue lag inspection;
- maintained license and release activity.

The spike must become either tested production infrastructure or be deleted. If
the planned library fails a criterion, document evidence and choose another
proven library without implementing an ad hoc queue.

## Coexistence Routing

Caddy gives Python only exact foundation paths (`/health/*` and
`/api/v1/system/*`). Existing `/api/v1/chat/completions`, other `/api/*`, and
`/zero-cache/*` continue to current services. A path-level smoke test prevents a
broad `/api/v1/*` match from stealing the legacy chat endpoint.

## Observability

Every request/job log includes timestamp, level, service, build version,
correlation ID, operation, result, and duration. Diagnostic jobs propagate a
correlation ID. Health logs are sampled or suppressed to prevent noise. Values
whose field names/types are secret are recursively redacted.

## Rollback

Remove Python exact-path Caddy matches and stop API/worker. The isolated schema
may remain unused during investigation. No legacy product data or routes were
modified, so business rollback has no data reconciliation step.
