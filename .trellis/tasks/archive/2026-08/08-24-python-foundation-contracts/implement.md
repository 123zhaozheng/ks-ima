# Python Foundation Implementation Checklist

## 1. Preflight

- Verify installed Python, uv, Bun, Docker/Compose, and PostgreSQL development
  prerequisites; record supported versions.
- Confirm current Bun tests and build baseline; report the known long-running
  lint behavior rather than suppressing it.
- Inspect existing Caddy/Compose/Dockerfiles and choose exact coexistence paths.
- Search for existing Python/backend scaffolds before creating names/utilities.

## 2. Python Project And Quality Tooling

- Create `backend/pyproject.toml`, source/test layout, and exact `uv.lock`.
- Add application factory, settings, CLI, error, middleware, logging, DB, task,
  API, worker, and test modules described in `design.md`.
- Configure Ruff, mypy, pytest/asyncio, coverage, and import boundaries.
- Add developer commands/scripts through package entry points; do not add shell
  scripts that duplicate Python CLI behavior.
- Validate import has no database/network/filesystem mutation side effects.

## 3. Database And Alembic

- Implement engine/session lifecycle and readiness probes.
- Configure target schemas, naming convention, version table, extension checks,
  and explicit upgrade/check commands.
- Add initial migration and clean-upgrade integration test.
- Add legacy public-schema non-mutation assertion.
- Add migration-head readiness failure and safe Problem Details/log coverage.

## 4. Durable Worker

- Run the library compatibility spike and record the chosen pinned dependency in
  code/docs/tests.
- Configure task schema, worker process, heartbeat, graceful shutdown, and lag.
- Implement idempotent diagnostic task with controlled fail-once test path.
- Test enqueue, single completion, retry, restart recovery, and duplicate key.
- Delete spike-only code and dependencies.

## 5. HTTP And Contracts

- Implement liveness, readiness, build/system info, and guarded diagnostic job
  endpoints.
- Implement correlation, trusted proxy, body limit, CORS, Problem Details, and
  redaction middleware.
- Define centralized cursor/ETag/idempotency/SSE contract types and unit tests.
- Export normalized OpenAPI and add drift check.
- Generate current Vue TypeScript client and add Vue Query system-info proof.
- Test legacy chat route is not captured by Python coexistence routing.

## 6. Containers And Coexistence

- Add non-root multi-stage API/worker image(s) with health checks.
- Add Compose services/config without deleting or renaming active legacy
  services.
- Add exact Caddy Python routes before generic Bun routes.
- Add clean Compose build/start/migrate/readiness/diagnostic/legacy-route smoke.
- Document routing rollback.

## 7. Validation

Backend:

```text
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy backend/src
uv run pytest
uv run alembic check
```

Frontend/legacy:

```text
bun test
bun run lint
bun run build:front
bun run build:admin
bun run build:server
```

Deployment/contract:

```text
OpenAPI export/check command defined by the implementation
docker compose config
docker compose build for API, worker, current web, and current server
clean database migration and coexistence smoke
```

Review:

- Read/write path and errors traced across Vue -> Caddy -> FastAPI -> DB/task.
- Secrets/config absent from logs/responses/OpenAPI.
- New dependencies all used, pinned, licensed, and documented.
- No empty feature modules, TODO behavior, debug endpoints enabled in production,
  broad proxy capture, auto migration, in-memory durable work, or legacy deletion.
- `trellis-check` passes and relevant backend/frontend specs are updated with the
  real conventions established by this child.

## 8. Rollback Point

- Tag/record the pre-routing revision and database inventory.
- Rollback removes exact Python proxy routes and stops new containers.
- Do not drop the isolated schema during emergency rollback; clean it only with
  an explicit reviewed operation after diagnosis.
