# Legacy Migration and Cutover Contracts

> Executable contracts for the resumable legacy ETL (`migrate-legacy-*` CLI family), write freeze, and cutover tooling. Source modules: `ima/cli.py` (`_legacy_*` helpers), `ima/application/migration_*.py`, `ima/application/maintenance.py`.

Captured from task `08-24-legacy-migration-cutover` implementation and check sessions.

---

## Contract: Migration reads legacy, never writes it; checksum normalization happens at read time

### Rule

All `migrate-legacy-*` commands are SELECT-only against `public.*`. Never UPDATE/DELETE legacy rows from migration code. Legacy blob checksums are base64 (`public.blob.sha256`); Python storage verification and `ima.*` checksum columns are hex (CHECK-constrained). Normalize base64→hex at the importer read path only.

### Wrong

```python
# rewriting legacy data, or storing the legacy checksum verbatim
connection.execute("UPDATE public.blob SET sha256=%s ...", (hex_digest,))
target_checksum = row.sha256  # base64 -> violates hex CHECK / fails copy_verified
```

### Correct

```python
target_checksum = normalize_legacy_checksum(row.sha256)  # base64 -> hex, read-side only
```

### Tests Required

- Unit test with a base64 checksum fixture; PostgreSQL test proving `copy_verified`/blob-verify pass on migrated legacy blobs.

---

## Contract: Trash propagation must keep restoration anchors

### Rule

Any code path that moves a migrated target row to trash (initial importer, trash-move reconciliation, legacy-deletion propagation) must set the restoration anchors: `documents.original_folder_id = COALESCE(original_folder_id, folder_id)` and `folders.original_parent_id = COALESCE(original_parent_id, parent_id)`. A trashed row without anchors cannot be restored, violating the lifecycle contract.

### Tests Required

- PostgreSQL test: legacy-deleted source propagates to a trashed target row whose anchors point at the pre-trash placement; restore returns it there.

---

## Contract: Rerun convergence — completed checkpoints with stale error state must re-reconcile

### Rule

The knowledge apply loop must not silently skip a `complete` checkpoint whose fingerprint matches but whose `last_error` records an unresolved delta (e.g. `legacy_deleted`). If the legacy row reappears (deleted then recreated), the apply must route the checkpoint through `_reconcile_knowledge_delta` again so the target converges; otherwise the row stays trashed forever and reruns never converge.

### Tests Required

- Rerun scenario: row deleted → apply propagates trash → row recreated → rerun restores placement (or records an explicit review decision), never a silent skip.

---

## Contract: Reconciliation reports are exit-code gated and redacted

### Rule

`migrate-legacy reconcile-report` (and all verify/report siblings) print one JSON payload and `raise SystemExit(4)` when findings exist — matching `inventory-legacy-mcp`. Recorded review decisions (`status='review'`, `last_error IN ('reparented_folder','legacy_deleted','source_changed')`) must be reported even when the legacy tables are absent. Reports carry `"secretValues": false` and never include connector key material.

---

## Contract: Write freeze is super-admin only, audited, and fail-closed for bridge mutations

### Rule

- Enter/exit require an active super administrator; both write `ima.audit_events` (`maintenance.freeze.enter|exit`) with metadata `{"reason", "secretValues": false}`.
- While frozen, bridge-served mutating actions and workspace/knowledge/storage mutations raise `MaintenanceFreezeError` → RFC 9457 `503` with code `maintenance_freeze`. Migration-tagged writers (direct importer SQL paths) keep working.
- The freeze flag lives in `ima.system_settings` (`maintenance_write_freeze` + reason/entered_at/entered_by); the bridge contract uses `Literal` source typing so refusal stays fail-closed.

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
cli._legacy_reconcile_report("knowledge")  # sees the fixture
```

Keep cleanup in its own `with psycopg.connect(...)` block inside `finally`.

### Gotcha: shared integration database accumulates residue across suites

Importer suites (identity, knowledge, model governance) leave checkpoints whose legacy rows were deleted and legacy fixtures (`public."user"`, `public."workspace"`). Rehearsal-style tests that assert a clean reconcile must sanitize at start: delete rows from `ima.legacy_*_migration` / `ima.workspace_authorization_migration` and leftover `public.*` fixture rows (guarded by `to_regclass`). Never assume the shared test DB is pristine between runs.

---

## Related Specs

- [Database Guidelines](./database-guidelines.md) — schema isolation, migrations, forced-Postgres gate
- [Identity And Platform Contracts](./identity-platform-contracts.md) — legacy identity projection contract
- [OAuth and MCP Service Principal Contracts](./oauth-mcp-contracts.md)
