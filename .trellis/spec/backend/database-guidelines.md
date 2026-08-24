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
and `ima_jobs`. Legacy public tables are outside this child's ownership.

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

Do not point foundation migrations at `public`, drop legacy schemas, or assume
that a successful Alembic log means bootstrap SQL committed. Verify schema,
version, extension, and task marker state on a clean PostgreSQL instance.
