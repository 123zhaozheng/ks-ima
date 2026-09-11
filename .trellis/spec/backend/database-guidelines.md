# Database Guidelines

> Database patterns and conventions for this project.

---

## Overview

<!--
Document your project's database conventions here.

Questions to answer:
- What ORM/query library do you use?
- How are migrations managed?
- What are the naming conventions for tables/columns?
- How do you handle transactions?
-->

The foundation uses SQLAlchemy 2 async for runtime probes and future domain
queries, psycopg for Alembic/operational commands, and PostgreSQL schemas `ima`
and `ima_jobs`. The legacy `public.*` tables were dropped by cleanup migration
`20260829_0011_legacy_schema_removal.py`; `ima.*` is the only live schema
surface.

---

## Forced-Postgres Integration Gate

`backend/tests/conftest.py` enforces an EXACT count of `postgres`-marked tests
when `IMA_REQUIRE_POSTGRES=1` (currently 38); any test add/remove must update
that number or collection exits 2.

The test database must provide the zhparser parser AND pgvector — a plain
`postgres:17-alpine` image fails on `CREATE EXTENSION vector`. Use the local
`nyaai-postgres-it` image (or build `Dockerfile.postgres`), e.g.:

```
docker run -d --name ima-test-pg -p 55432:5432 \
  -e POSTGRES_PASSWORD=identity-gate-password -e POSTGRES_DB=app \
  nyaai-postgres-it:20260825
```

Tests connect via asyncpg (`IMA_TEST_DATABASE_URL=postgresql+asyncpg://...`);
Alembic itself needs the sync psycopg driver (`postgresql+psycopg://` in
`IMA_DATABASE_URL`) because `migrations/env.py` uses a sync engine.

---

## Query Patterns

<!-- How should queries be written? Batch operations? -->

Use bound parameters with SQLAlchemy `text()` for foundation queries. Keep task
library connections on the validated `ima_jobs` search path and do not interpolate
untrusted identifiers.

---

## Migrations

<!-- How to create and run migrations -->

Migrations run only through `ima migrate` or an explicit Alembic invocation.
`ima` is bootstrapped and committed before Alembic creates `ima.alembic_version`.
The Procrastinate schema is installed only when its marker table is absent.
Runtime startup never upgrades the database.

---

## Naming Conventions

<!-- Table names, column names, index names -->

Schema/table names are snake_case; foundation schemas are `ima` and `ima_jobs`.
Alembic's version table is in `ima`; task tables and enums are on the `ima_jobs`
search path. Foundation timestamps are UTC `timestamptz` values.

---

## Common Mistakes

<!-- Database-related mistakes your team has made -->

Do not point foundation migrations at the wrong schema, bypass explicit
migration steps, or assume that a successful Alembic log means bootstrap SQL
committed. Verify schema, version, extension, and task marker state on a clean
PostgreSQL instance.

### Common Mistake: Stale dev API process serving a migrated database

**Symptom**: After pulling backend changes, API endpoints (e.g. `POST
/knowledge-bases/{id}/ask`) return 500 `INTERNAL_ERROR` while the database
itself is healthy.

**Cause**: The long-running local API process still executes the old code,
but the database has already been migrated forward. When a migration drops or
renames a table the old code reads (real case 2026-09-11: `20260910_0013`
dropped `ima.kb_profile_assignments` while the running server predated commit
`f3fba45`), every code path touching it raises an unhandled
`UndefinedTableError`.

**Fix**: Restart the local API (`python backend/run_server.py`). Verify with
`Get-Process <pid> | Select StartTime` vs `git log -1 --format=%ci --
backend/src`: process older than the latest backend commit means stale code.

**Prevention**: After applying or pulling migrations that drop/rename schema
objects, restart all local backend processes (API + worker) before testing.
When triaging a 500, compare the server process start time against the latest
backend commit before digging into application code.
