# Legacy Migration and Cutover — Design

Evidence base: `research/` in this task directory (data inventory, code
inventory, gaps G1–G12, tooling state, sibling-task standards, coexistence
precedents). This document fixes the technical decisions.

## 1. ETL phases

Reuse the existing `migrate-legacy-*` importer family (checkpoint tables,
per-record fingerprints, topological import). No new ETL engine.

### Phase A — Pre-flight (read-only, repeatable)

- Existing `plan/report` commands for identity, authorization,
  model-governance, knowledge; `inventory-legacy-mcp report`.
- New `migrate-legacy report-all`: row counts per legacy table, blob
  count/total bytes, MIME histogram (flag unsupported types), delta probe
  (rows created/updated since last checkpoint pass), connector pending list.
- Snapshot evidence triple recorded into the rehearsal/cutover evidence file:
  DB snapshot id/checksum, object-store bucket inventory, image digests +
  Caddyfile sha256.

### Phase B — Background bulk import (legacy still writing)

- Fix G1 (checksum normalization) before any storage apply run.
- Apply chain in dependency order: identity → authorization → knowledge
  metadata → storage copy → model governance (operator mapping file). Rerun
  until `review/failed` sets are stable and operator-accepted.
- New bounded re-ingestion enqueue (G2) with worker capacity control; track
  ready/degraded/failed per MIME.

### Phase C — Write freeze + final delta

- Freeze at the edge (§3); quiesce legacy cron (parseKb/cleanBlobs) by
  stopping the Bun service before blob verification.
- Rerun the full apply chain as delta; checkpoints skip unchanged rows.
  Reconciliation rules (G4): legacy-deleted rows → mark/propagate to target
  per lifecycle contract; re-parented folders → delete-and-reimport subtree
  decision recorded in the report; trash moves reconciled to trash placement.
- Re-verify storage for blobs touched since the last pass; finish remaining
  re-ingestion or mark degraded explicitly.

### Phase D — Cutover, rollback window, handoff

Cutover procedure §4; rollback §5; then hand off to
`08-24-legacy-deletion-release` with retained rollback artifacts.

## 2. Verification gates

| Gate | Content | Enforcement |
|------|---------|-------------|
| V1 data equivalence | identity/authorization/knowledge verify; blob report; reconciliation report; connector pending == 0 | CLI commands, non-zero exit on failure |
| V2 content readiness | ingestion report (ready/degraded/failed by MIME); search/Ask spot-diff on a frozen fixture workspace with a role matrix | CLI report + contract test |
| V3 auth/ACL live checks | policy contract suite against migrated data (REST/search/Ask/download/MCP/OAuth/service principal); `/mcp` smoke | pytest suites |
| V4 operational readiness | backup+restore rehearsal on disposable copy, drill evidence for cutover+rollback Caddy JSON, runbook approval audit event | rehearsal test + drill script |

## 3. Write freeze

1. Primary mechanism: stop the legacy Bun service for the window (its only
   live consumers are legacy chat and legacy connector keys; Bun alone cannot
   authenticate anyway — bridge dependency). Stopping the service also
   quiesces parseKb/cleanBlobs cron.
2. Belt-and-suspenders: typed `ima.system_settings` flag
   `maintenance_write_freeze` (boolean + reason + entered_at); while set,
   Python refuses bridge-served mutations and any internal write not tagged
   `migration`. Enter/exit are `ima.audit_events` mirroring the
   `legacy.mcp.inventory` pattern.
3. Contract test: mutation attempts through bridge paths during freeze return
   a safe RFC 9457 maintenance error; migration-tagged writes succeed.

## 4. Cutover procedure (operator steps, encoded in the runbook)

1. Approve + record gate evidence V1–V4; record approval as audit event.
2. Enter freeze (§3); verify zero legacy write traffic.
3. DB snapshot + object-store inventory + image/config digests (rollback
   anchors).
4. Final delta applies + storage verify + reconciliation (Gate V1 rerun, must
   be clean).
5. Complete/accept re-ingestion state (Gate V2).
6. Switch Caddy to cutover JSON (drill-derived): all `/api/*` to Python;
   `/api/mcp` becomes 404/410 unless an explicit compatibility approval
   exists — consumers move to canonical `/mcp` per the OAuth runbook; legacy
   upstreams withdrawn; Bun stopped.
7. Smoke matrix on migrated data: platform admin, workspace admin, editor,
   viewer, restricted-folder user, OAuth agent (kb:read/ask/write), service
   principal; plus MCP SDK handshake on `/mcp`.
8. Monitor auth failures, policy denials, queue age, ingestion failures,
   storage errors.
9. Declare cutover; open rollback window (legacy stopped but images/config/
   snapshots retained; legacy tables untouched).

## 5. Rollback

Pre-deletion (rollback window): redeploy pre-cutover Caddy JSON; restart the
retained Bun image ONLY with the Python identity bridge still up (legacy
`public.session` is empty — Bun-only restoration cannot authenticate); if
Python-side writes happened after freeze, restore the freeze-time snapshot +
object inventory first and invalidate Python sessions; re-enter dual-run and
rerun delta.

Post-deletion: no mixed rollback — full restore of pre-cutover snapshot +
matching images/config, per the runbook's post-sunset recovery section.

## 6. Module layout

Backend (all under `backend/src/ima`, following existing importer patterns):

- `application/migration_checksum.py` (or extension of the storage importer
  module): G1 base64→hex normalization at read time from legacy blob rows;
  never rewrites legacy data.
- `application/migration_reconcile.py`: delta detection + reconciliation
  rules + report model; used by all importer families via shared row-set
  comparison helper.
- `application/migration_blob_verify.py`: object HEAD verification + orphan/
  missing report.
- `application/migration_reingest.py`: bounded enqueue into existing
  `ingestion_jobs` pipeline + readiness report by MIME.
- `application/maintenance.py` + migration for `ima.system_settings`
  `maintenance_write_freeze` flag; guard hook in the bridge/internal mutation
  entry points.
- `application/conversation_archive.py`: legacy chat counts-only archive
  report (decision: data not migrated).
- CLI (`cli.py`): new subcommands following plan/apply/verify/report
  conventions:
  - `migrate-legacy report-all`
  - `migrate-legacy reconcile {identity,authorization,knowledge}` /
    `migrate-legacy reconcile-report` (exit-code gated)
  - `migrate-legacy blob-verify`
  - `migrate-legacy reingest enqueue|report`
  - `migrate-legacy conversations-archive`
  - `maintenance freeze enter|exit|status`

Frontend/tooling:

- `scripts/caddy-routing-drill.ts`: add `cutover` phase producing/validating
  cutover JSON + rollback JSON evidence alongside existing
  `pre_sunset_rollback` / `restored` phases.
- `docs/legacy-cutover-runbook.md`: structure mirrored from
  `docs/oauth-mcp-coexistence-runbook.md`.

## 7. Tests

- Unit: checksum normalization (base64 fixture), reconciliation rules
  (delete/re-parent/trash), readiness classification, freeze guard.
- PostgreSQL: full apply→delta→reconcile→blob-verify→reingest chain on
  seeded legacy fixtures; freeze enter/exit audit rows.
- Contract: runbook presence/sections pin; drill phases (cutover + rollback)
  evidence validation; freeze refusal on bridge mutations.
- Rehearsal: end-to-end sequence on disposable sanitized dataset (mark as
  postgres integration test, zero skips).

## 8. Non-goals

- No deletion of src-server/Zero/drizzle/legacy tables/legacy routes (next
  task).
- No connector secret conversion or reconstruction.
- No dual-write architecture.
- No legacy-session restoration path; rollback always involves Python
  identity.
