# Quality Guidelines

> Code quality standards for backend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

New backend code targets Python 3.13 and is checked with Ruff (format and lint),
mypy strict mode, and pytest. The application factory must be import-safe: no
network, database mutation, migration, or background task may happen at import
time.

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

Do not use FastAPI BackgroundTasks, detached asyncio tasks, in-memory durable
queues, automatic startup migrations, broad exception details, or duplicate
configuration/client implementations. Keep legacy Bun/Zero code untouched until
the migration task that owns its removal.

---

## Required Patterns

<!-- Patterns that must always be used -->

Use Pydantic settings and contracts, SQLAlchemy async engines for API data
access, explicit Alembic commands, and Procrastinate for durable PostgreSQL jobs.
Keep API and worker lifecycle cleanup explicit.

---

## Testing Requirements

<!-- What level of testing is expected -->

Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src/ima`,
and `uv run pytest` from `backend/`. Integration tests requiring PostgreSQL are
marked `postgres` and must run against the project database image in CI.

---

## Code Review Checklist

<!-- What reviewers should check -->

Review import side effects, secret leakage, transaction/schema isolation,
idempotency/retry behavior, generated OpenAPI drift, and clean container startup.
