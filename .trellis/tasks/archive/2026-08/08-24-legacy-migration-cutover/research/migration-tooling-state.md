# Research: Existing Migration Tooling in the Python Backend

- **Query**: CLI patterns, Alembic state, ETL-ish scripts, and resumability patterns already used.
- **Scope**: internal
- **Date**: 2026-08-28

## 1. CLI (`backend/src/ima/cli.py`, ~2,300 lines, argparse)

Commands (`cli.py:42-116`), all with optional positional action `plan|apply|verify|report` (default `report`):

| Command | Function | Notes |
|---|---|---|
| `worker` | `_run_worker` (`cli.py:159`) | task-queue worker loop |
| `check-config` | `cli.py:117-120` | settings validation |
| `check-worker` | `_check_worker` (`cli.py:283`) | worker heartbeat check |
| `migrate` | `_run_migrations` (`cli.py:250`) | Alembic upgrade to head (runs as compose job `ima-migrate`) |
| `bootstrap-admin` | `_bootstrap_admin` (`cli.py:1265-1329`) | first super-admin from `IMA_BOOTSTRAP_EMAIL/PASSWORD` sealed env or interactive prompt; refuses when a super_admin exists; Argon2id `m65536-t3-p2`, param version `argon2id-v1-m65536-t3-p2` |
| `migrate-legacy-identity` | `_legacy_identity_report` (`cli.py:1908-2143`) | resumable per-user import; deletes `public.session` on apply; verify checks 7 per-user invariants + checkpoint counts |
| `migrate-legacy-authorization` | `_legacy_authorization_report` (`cli.py:1332-1842`) | workspaces→members→folders topological import with closure + ACL; verify does full equivalence (membership, parent, closure set, ACL set) |
| `rotate-model-secrets` | `_rotate_model_secrets` (`cli.py:301`) | key-ring rotation for gateway secrets |
| `migrate-legacy-model-governance` | `_legacy_model_governance_report` (`cli.py:389-645`) | provider→gateway (disabled), model→governed_models with operator `--mapping-file` / `IMA_MODEL_GOVERNANCE_MAPPING` |
| `migrate-legacy-knowledge` | `_legacy_knowledge_report` (`cli.py:648-1165`) | metadata ETL + storage phase (`_legacy_knowledge_storage_phase` `cli.py:1168-1262`); verify compares fingerprint, folder/document fields, version digests, tag sets |
| `inventory-legacy-mcp` | `_legacy_mcp_inventory` (`cli.py:192-247`) | report/apply/verify with operator decision file; exit 2 invalid, 3 unauthorized, 4 pending |
| `register-mcp-client` | `_register_mcp_client_sync` (`cli.py:2146+`) | pre-registered OAuth client |

DB access pattern: sync `psycopg.connect` with conninfo derived from `settings.database_url`
(asyncpg URL rewritten to postgresql, `cli.py:200-205`), per-record `connection.transaction()` blocks,
explicit commit after failure-checkpoint writes. No ORM in migration paths; raw SQL for operator review
(deliberate, `cli.py:3-4`).

## 2. Resumability patterns already implemented

- **Checkpoint tables** (see `legacy-data-inventory.md` §4): `(source_kind, source_id)` PK, status machine
  `running → complete|failed|review`, `attempts`, `last_error`, `source_fingerprint`, `mapping jsonb`.
- **Skip-if-complete**: apply skips rows whose checkpoint is `complete` with unchanged fingerprint
  (`cli.py:848-853`, `487-492`, `576-581`); changed fingerprint → `review/source_changed`, never silent overwrite.
- **Failure isolation**: every record's failure is checkpointed (`failed` + exception class name) and the
  loop continues; rerun picks up failed rows (authorization `cli.py:1428-1441,1481-1494`; knowledge
  `cli.py:1041-1048`; identity `cli.py:2022-2028`).
- **Idempotent inserts**: `ON CONFLICT DO NOTHING` / `DO UPDATE` everywhere; derived target ids are
  deterministic UUIDv5 (`cli.py:896-898,1005-1007`) so reruns cannot duplicate documents/tags.
- **Topological processing with bounded loop**: folder import iterates pending rows until no progress, then
  marks remainder `cycle_or_missing_parent` (`cli.py:1495-1676`).
- **Storage phase resumability**: per-object checkpoint kind `storage`/id `{source_id}:storage`; complete
  rows skipped on rerun (`cli.py:1194-1210`); missing blob → `review/missing_legacy_blob`; copy errors map
  `OBJECT_MISSING|SOURCE_OBJECT_CHANGED → review`, others → `failed` (`cli.py:1253-1261`).
- **Verify = independent recomputation**: verify paths recompute expected state from legacy source (not from
  checkpoints) and diff against target rows — identity (`cli.py:2044-2126`), authorization closure/ACL
  equivalence (`cli.py:1677-1839`), knowledge digest/tag/lifecycle equivalence (`cli.py:1058-1164`).

## 3. Alembic state (`backend/migrations/versions/`)

9 migrations, raw-SQL style, head `20260828_0009`:

```
20260824_0001_foundation            ima + ima_jobs schemas; vector + zhparser; diagnostic_job, worker_heartbeat
20260824_0002_identity_platform     users, password_credentials, totp_credentials, recovery_codes, sessions,
                                    auth_tokens, auth_rate_limits, platform_role_assignments, system_settings,
                                    workspaces, audit_events, legacy_identity_migration, legacy_identity_projection
20260825_0003_workspace_authorization
                                    workspace_members, workspace_groups, workspace_group_members,
                                    workspace_invitations, folders, folder_closure, folder_acls,
                                    folder_acl_entries, workspace_authorization_migration
20260825_0004_model_governance      model_gateways, model_gateway_secrets, model_gateway_health, governed_models,
                                    capability_profiles, capability_profile_versions, model_dependency_index,
                                    workspace_profile_assignments, legacy_model_governance_migration
20260825_0005_knowledge_tree        documents, document_versions, tags, document_tags, legacy_knowledge_migration
                                    (+ folders lifecycle columns alter)
20260825_0006_storage_ingestion     document_file_versions, document_derived_text, document_chunks,
                                    ingestion_jobs, storage_cleanup_jobs
20260826_0007_search_conversations  chunk_search_indexes, conversations, conversation_messages, message_citations
                                    (document_chunks alter)
20260826_0008_oauth_mcp             mcp_clients, mcp_client_redirects, mcp_authorization_codes, mcp_grants,
                                    mcp_access_tokens, mcp_refresh_tokens, mcp_refresh_families, mcp_credentials,
                                    mcp_service_principals, mcp_rate_buckets, mcp_concurrency_leases
20260828_0009_mcp_concurrency_hardening
```

Conventions: additive `IF NOT EXISTS`; downgrades refuse to destroy populated target rows (knowledge-tree
research cites `20260825_0003:102-118`); migration credentials separable from runtime; `alembic check` is a
release gate (parent implement.md §13.3).

## 4. Job/queue infrastructure (for ETL steps beyond CLI)

- Durable PostgreSQL-backed queue in schema `ima_jobs` (env `IMA_TASK_SCHEMA`), worker via `ima worker`;
  queues in use: `diagnostic`, `ingestion` (`docker-compose.example.yml:57-59`); design reserved a
  `migration` queue name for resumable legacy import steps (parent design.md §5.2) — **not yet created**.
- Ingestion pipeline: `ima.ingestion_jobs` with stages parse/chunk/embed, statuses
  `queued|running|retryable|blocked|failed|dead_letter|cancelled|cancel_requested`, generation-aware retry
  (`backend/src/ima/application/storage.py:259,327-387`); jobs created via
  `JobService.create_ingestion_jobs(conn, document_id, version, count, actor)`.
- Task app factory: `backend/src/ima/infrastructure/tasks/app.py`; worker tasks under
  `infrastructure/tasks/{ingestion.py,diagnostic.py,model_health.py}`.

## 5. Other backend scripts (`backend/scripts/`)

- `seed_identity_e2e.py` — deterministic identity fixture seeding for Playwright (accounts ordinary/super/
  platform/auditor/disabled; uses `new_legacy_id`, `hash_password`, `encrypt_secret`, peppers from env).
- `check_contract.py`, `export_openapi.py` — deterministic OpenAPI export/contract gate
  (`ima contract export --check` in release gates, parent implement.md:628).

## 6. Relevant settings (`backend/src/ima/config.py`)

- `storage_endpoint/region/bucket/access keys`, `storage_max_object_bytes=25MiB`,
  `storage_presign_seconds=300`, `storage_retention_seconds=604800` (`config.py:72-81`);
  all-or-nothing storage config validation (`config.py:291-299`).
- `bridge_token` (shared secret for Bun↔Python internal calls), `session_pepper`, `token_pepper`,
  `totp_encryption_key`, model key ring (`.env.example`).
- `mcp_resource_path` hard-locked to `/mcp` (`config.py:90,200-201`) — no compat alias exists today.

## Caveats / Not Found

- No `resume` subcommand distinct from `apply` — resumability is implicit in rerunning apply (parent plan
  12.1 lists `resume` as planned UX; current UX is `apply` rerun).
- No bulk COPY-based importer and no parallel workers for ETL; single-process psycopg loops.
- No migration-progress telemetry beyond CLI stdout JSON and checkpoint tables (no job-queue visibility for
  migration steps yet).
