# Legacy Migration and Cutover Contracts (Terminal State)

> Historical contracts for the retired `migrate-legacy-*` / `inventory-legacy-mcp` CLI family, plus the retained write freeze. The ETL code and legacy `public.*` tables were deleted in task `08-24-legacy-deletion-release` (cleanup migration `20260829_0011_legacy_schema_removal.py`). Checkpoint/history tables (`ima.legacy_*_migration`, `ima.workspace_authorization_migration`, `ima.legacy_identity_projection`) are retained as migration-history evidence.

Captured from tasks `08-24-legacy-migration-cutover` and `08-24-legacy-deletion-release`.

---

## Contract: Migration history tables are evidence, never live data

### Rule

The `ima.legacy_*_migration` checkpoint tables and `ima.legacy_identity_projection` are append-only historical evidence. No live code path reads them to serve requests, and no new writer exists. Future work must not reintroduce readers of `public.*` legacy tables — the tables themselves are gone after the cleanup migration; any `to_regclass`-guarded probe must treat absence as final, not transient.

---

## Contract: Legacy checksum normalization was read-side only

### Rule

Legacy blob checksums were base64 (`public.blob.sha256`); `ima.*` checksum columns are hex (CHECK-constrained). The ETL normalized base64→hex at the importer read path only and never rewrote legacy rows. Migrated `ima.*` rows carry hex digests; any future verification tool must keep the hex CHECK contract.

---

## Contract: Trash propagation keeps restoration anchors

### Rule

Any code path that moves a target row to trash must set the restoration anchors: `documents.original_folder_id = COALESCE(original_folder_id, folder_id)` and `folders.original_parent_id = COALESCE(original_parent_id, parent_id)`. A trashed row without anchors cannot be restored, violating the lifecycle contract. (Still live behavior in `ima/application/knowledge.py`.)

---

## Contract: Verification reports are exit-code gated and redacted

### Rule

Operational verify/report commands print one JSON payload and `raise SystemExit(4)` when findings exist. Reports carry `"secretValues": false` and never include connector key material. New verify tooling must follow the same gating pattern.

---

## Contract: Write freeze is super-admin only, audited, and fail-closed

### Rule (retained machinery)

- Enter/exit require an active super administrator; both write `ima.audit_events` (`maintenance.freeze.enter|exit`) with metadata `{"reason", "secretValues": false}`.
- While frozen, mutating workspace/knowledge/storage actions raise `MaintenanceFreezeError` → RFC 9457 `503` with code `maintenance_freeze`. Migration-tagged writers (direct `ima` CLI SQL) bypass it by design.
- The freeze flag lives in `ima.system_settings` (`maintenance_write_freeze` + reason/entered_at/entered_by). The freeze is a generic operations tool and survives legacy deletion.

---

## Gotcha: psycopg connections are transaction-scoped — CLI helpers open their own connection

### Symptom

A PostgreSQL test inserts fixture rows inside `with psycopg.connect(...) as conn:` and then calls a CLI helper; the helper reports the rows missing ("DID NOT RAISE SystemExit", empty findings).

### Cause

CLI helpers connect separately; they cannot see the test connection's uncommitted transaction. Exiting the `psycopg.connect` context commits, so fixtures are only visible after the block closes.

### Fix / Prevention

```python
with psycopg.connect(SYNC_URL) as connection:
    connection.execute(insert_fixture)
# committed here
cli_helper()  # sees the fixture
```

Keep cleanup in its own `with psycopg.connect(...)` block inside `finally`.

---

## Gotcha: shared integration database accumulates residue across suites

### Symptom

Rehearsal-style tests that assert a clean state fail on leftover rows from earlier suites.

### Fix / Prevention

Tests that assert clean state must sanitize at start: delete rows from `ima.legacy_*_migration` / `ima.workspace_authorization_migration` and leftover fixture rows (guarded by `to_regclass`). Never assume the shared test DB is pristine between runs.

---

## Related Specs

- [Database Guidelines](./database-guidelines.md) — schema isolation, migrations, forced-Postgres gate
- [Identity And Platform Contracts](./identity-platform-contracts.md) — legacy identity projection contract
- [OAuth and MCP Service Principal Contracts](./oauth-mcp-contracts.md)
