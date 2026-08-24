# IMA Python Foundation

The foundation runs beside the retained Bun/Zero runtime. It owns only
`/health/*` and `/api/v1/system/*` in this phase.

## Development

```powershell
uv sync --frozen
uv run ima check-config
uv run uvicorn ima.main:app --reload --port 8000
uv run python scripts/export_openapi.py
uv run python scripts/check_contract.py
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
```

Set `IMA_DATABASE_URL` to a PostgreSQL URL. The API and worker do not migrate
on startup. Run `uv run ima migrate` once as a deployment step; it creates the
isolated `ima` and `ima_jobs` schemas and applies the Procrastinate schema.

The target PostgreSQL image must provide both `vector` and `zhparser`. The
repository `Dockerfile.postgres` builds that image explicitly. A migration
fails closed when either extension is unavailable.

## Worker

```powershell
uv run python -m ima.workers.main
```

The worker uses Procrastinate's PostgreSQL connector. Diagnostic jobs are
idempotent by application key, retry with the queue library, and persist their
state in `ima_jobs.diagnostic_job`.

The real PostgreSQL queue gate runs against the Compose target image:

```powershell
docker compose -f docker-compose.example.yml run --rm ima-integration
```

It applies the explicit migration, starts a separate Worker process, verifies
idempotent enqueue, controlled retry, persisted attempt/status state, heartbeat,
and queued work surviving the API/Worker process boundary. The integration test
also starts a normal `diagnostic` worker beside the
`diagnostic-integration` worker and asserts that queue isolation holds. The
Compose gate requires `IMA_TEST_DATABASE_URL` and exactly two Postgres tests;
missing database configuration cannot silently turn the gate into skips.

## Coexistence

`docker compose -f docker-compose.example.yml up --build` runs the explicit
`ima-migrate` job before API/worker readiness. Caddy sends only exact Python
foundation paths to `PYTHON_API_URL`; `/api/v1/chat/completions`, other Bun
routes, and `/zero-cache/*` retain their existing upstreams.
