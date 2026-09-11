# Python Foundation Contracts

## 1. Scope / Trigger

Apply this specification to Python API/worker startup, configuration, health,
Alembic migrations, PostgreSQL task processing, Docker/Compose wiring, and any
change to `/health/*` or `/api/v1/system/*`.

The foundation coexists with Bun/Zero. Python owns only exact foundation paths
until a later Trellis child migrates a business slice. This prevents a broad
proxy or migration from silently taking over live product behavior.

## 2. Signatures

### HTTP And Commands

```text
GET  /health/live
GET  /health/ready
GET  /api/v1/system/info
POST /api/v1/system/jobs/diagnostic
GET  /api/v1/system/jobs/{job_id}

ima check-config
ima migrate
ima check-worker
ima worker
python -m ima.workers.main
```

Liveness checks only the process. Readiness checks database access, Alembic
head, and the configured Worker heartbeat. Diagnostic endpoints return 404
unless `IMA_DIAGNOSTIC_JOBS_ENABLED=true`. `ima worker` delegates to
`ima.workers.main.run`; it is not a second Worker implementation.

### Database

```text
ima.alembic_version
ima_jobs.diagnostic_job(
  id uuid primary key,
  idempotency_key varchar(128) unique,
  status queued|running|succeeded|failed,
  attempts integer,
  correlation_id varchar(64),
  created_at timestamptz,
  updated_at timestamptz
)
ima_jobs.worker_heartbeat(worker_name primary key, heartbeat_at timestamptz)
ima_jobs.procrastinate_*
```

Required extensions are `vector` and `zhparser`. Legacy `public` tables are not
owned by foundation migrations.

## 3. Contracts

### Environment

| Key | Default | Contract |
|---|---|---|
| `IMA_ENVIRONMENT` | `development` | `development|test|staging|production` |
| `IMA_BUILD_VERSION` | `dev` | Non-secret build identifier |
| `IMA_PUBLIC_ORIGIN` | local HTTP | Absolute HTTP(S); production requires HTTPS |
| `IMA_DATABASE_URL` | development URL | Secret async SQLAlchemy PostgreSQL URL |
| `IMA_TASK_DATABASE_URL` | database URL | Optional dedicated task URL |
| `IMA_DATABASE_SCHEMA` | `ima` | Identifier only |
| `IMA_TASK_SCHEMA` | `ima_jobs` | Identifier and task search path |
| `IMA_CORS_ORIGINS` | empty | CSV absolute origins; no wildcard |
| `IMA_TRUSTED_PROXIES` | empty | CSV IP/CIDR values |
| `IMA_MAX_BODY_BYTES` | 25 MiB | `1..536870912`; declared and streamed bodies |
| `IMA_DIAGNOSTIC_JOBS_ENABLED` | false | Enables diagnostic HTTP endpoints |
| `IMA_DIAGNOSTIC_QUEUE` | `diagnostic` | `[A-Za-z0-9._-]+`; register/defer/consume |
| `IMA_WORKER_NAME` | `diagnostic-worker` | `[A-Za-z0-9._-]+`; worker and heartbeat identity |
| `IMA_WORKER_HEARTBEAT_SECONDS` | 15 | Heartbeat interval |
| `IMA_WORKER_LAG_WARNING_SECONDS` | 120 | Readiness maximum heartbeat age |

Settings are immutable and `IMA_`-prefixed only. The legacy root `.env` must
not inject unprefixed `DATABASE_URL` into Python.

### Response, Errors, And Queue

Success DTOs use camelCase aliases and UTC RFC 3339 timestamps. Errors use
`application/problem+json` with `type`, `title`, `status`, `detail`, `instance`,
`code`, `correlationId`, and optional field `errors`. Every response carries
`X-Correlation-ID`; secrets and internal exception text are never returned.

The API inserts one diagnostic row per idempotency key and defers only after a
new insert. Task registration, defer, Worker queue filter, Worker name,
heartbeat write, and readiness lookup use the same validated settings. The
Compose integration gate uses a distinct queue/name while a normal Worker runs.

The task connector is built once in `create_task_app` and needs two things:
`PsycopgConnector(kwargs=...)` must be a **mapping** (Procrastinate spreads it
into psycopg's connect call, so omitting it crashes the Worker with
`argument after ** must be a mapping, not NoneType`), and it sets
`-c search_path=<IMA_TASK_SCHEMA>` so the queue resolves its tables. Because the
migration creates the `ima_jobs` schema in the **main** database, leave
`IMA_TASK_DATABASE_URL` unset unless a dedicated task database also carries that
schema; pointing it at a maintenance database (`postgres`) fails with
`procrastinate_*_v1 does not exist`.

## 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Production origin is HTTP | Configuration fails |
| Wildcard/malformed CORS or invalid identifier | Configuration fails |
| Declared or streamed body exceeds limit | 413 Problem Details |
| Database unavailable or Alembic not at head | Readiness 503; liveness 200 |
| Configured heartbeat absent/stale | Readiness 503 |
| Diagnostic feature disabled | Diagnostic routes return 404 |
| Duplicate idempotency key | Return original job; do not defer again |
| Controlled first failure | Retry; attempts=2; final success |
| Required extension missing | Migration fails closed |
| `IMA_REQUIRE_POSTGRES=1` without DB/two Postgres tests | Test collection fails |
| Unexpected exception | Redacted log and generic 500 Problem Details |

## 5. Good / Base / Bad Cases

- Good: Caddy sends `/api/v1/system/info` to Python while
  `/api/v1/chat/completions` still reaches Bun.
- Base: diagnostics are disabled and API is not ready until its named Worker
  writes a current heartbeat.
- Bad: API startup runs Alembic or creates a detached/in-memory task.
- Bad: the normal Worker can consume integration-queue jobs.
- Bad: a green integration command silently skipped PostgreSQL tests.

## 6. Tests Required

1. Unit settings, recursive redaction, and both declared/chunked body limits.
2. OpenAPI/Problem Details/correlation contract tests.
3. Exact Caddy path test preserving legacy chat.
4. Clean and repeat target-image migration: both extensions, isolated schemas,
   version/task markers, unchanged legacy public inventory.
5. Concurrent normal/integration Workers: queue isolation, one idempotent row,
   controlled retry to attempts=2, success, and named heartbeat.
6. API/Worker images run non-root and container healthchecks observe real state.

## 7. Wrong vs Correct

### Wrong

```python
@app.on_event("startup")
async def startup() -> None:
    await run_migrations()
    asyncio.create_task(parse_jobs())
```

This mutates schema per replica and loses work on restart.

### Correct

```python
# Deployment runs `ima migrate` once.
app = create_app(settings)

# A separate process consumes a named durable queue.
await task_app.run_worker_async(
    queues=[settings.diagnostic_queue],
    name=settings.worker_name,
)
```

