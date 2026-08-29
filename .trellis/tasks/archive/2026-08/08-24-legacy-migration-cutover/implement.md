# Legacy Migration and Cutover — Implementation Plan

## Preconditions

- Re-read PRD, `design.md`, and all `research/` evidence before coding.
- Follow existing importer conventions: checkpoint tables, per-record
  fingerprints, `plan/apply/verify/report` CLI shape, transport-neutral
  application services, safe audit metadata.
- Never mutate `public.*` rows; migration reads legacy, writes `ima.*`.

## Ordered Work

### 1. Checksum normalization (G1)

1. Locate legacy blob checksum read path in the storage importer; normalize
   base64→hex at read time (never rewrite legacy data).
2. Unit test with a base64 checksum fixture; PostgreSQL test proving
   `copy_verified`/blob verification passes for migrated legacy blobs.

Gate: storage verify green on seeded legacy blob fixtures with base64
checksums.

### 2. Reconciliation and delta rules (G4)

1. Add shared row-set comparison helper (legacy key set vs target provenance
   set) reused by identity/authorization/knowledge importers.
2. Implement rules: legacy-deleted rows, folder re-parenting
   (delete-and-reimport subtree with report entry), trash moves.
3. Add `migrate-legacy reconcile-report` CLI with exit-code gating and a
   machine-readable report (legacy-absent-in-target, target-absent-in-legacy,
   rule decisions).

Gate: PostgreSQL tests cover delete/re-parent/trash deltas and rerun
idempotence; report exit codes asserted.

### 3. Blob verification report

1. Add `migrate-legacy blob-verify`: HEAD-check every migrated object version
   (checksum/size/MIME), compare counts against legacy blob rows, list
   orphans and missing.
2. Exit-code gated CLI + report model consistent with other verify commands.

Gate: PostgreSQL test with seeded objects incl. one corrupted/orphan/missing
case each.

### 4. Re-ingestion enqueue and readiness (G2)

1. Add `migrate-legacy reingest enqueue` — resumable, bounded enqueue into the
   existing `ingestion_jobs` pipeline with worker capacity control; skips
   versions already ready.
2. Add `migrate-legacy reingest report` — ready/degraded/failed by MIME.

Gate: PostgreSQL test proves resumability (partial run → rerun completes) and
boundedness; readiness classification per MIME asserted.

### 5. Conversation archive report

1. Add `migrate-legacy conversations-archive` — counts-only report of legacy
   chat/conversation/message rows (decision: not migrated). No importer.

Gate: unit/PostgreSQL test on seeded fixtures; report shape asserted.

### 6. Write freeze mechanism (G5)

1. Alembic migration (additive, `ima` schema only): `ima.system_settings`
   typed key-value with `maintenance_write_freeze` boolean + reason +
   entered_at.
2. `application/maintenance.py` service: enter/exit/status; audit events
   mirroring `legacy.mcp.inventory` pattern.
3. Guard hook: while frozen, refuse bridge-served mutations and internal
   writes not tagged `migration` with a safe RFC 9457 maintenance error.
4. CLI `maintenance freeze enter|exit|status`.

Gate: contract test proves bridge mutation refused during freeze and allowed
after exit; audit rows recorded; migration-tagged writes succeed.

### 7. Routing drill cutover phase

1. Extend `scripts/caddy-routing-drill.ts` with a `cutover` phase deriving
   cutover JSON (all `/api/*` → Python, legacy upstreams withdrawn, `/api/mcp`
   404/410) and rollback JSON, with evidence artifacts matching existing
   phase format.
2. Add/extend drill tests to validate both configs (matchers, precedence,
   internal-404 preserved).

Gate: `bun run test:caddy-routing` passes with cutover + rollback phases
`"ok": true`.

### 8. Runbook and rehearsal

1. Write `docs/legacy-cutover-runbook.md` mirroring the OAuth/MCP runbook:
   pre-flight, freeze, cutover steps, pre-deletion rollback, post-deletion
   recovery, evidence checklist.
2. Contract test pinning runbook presence and required sections.
3. Rehearsal: PostgreSQL integration test exercising
   apply→verify→freeze→delta→cutover-config→rollback-config on a disposable
   sanitized dataset, recording gate results.

Gate: rehearsal test passes with zero skips; runbook pin test green.

## Required Verification

```powershell
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
$env:IMA_REQUIRE_POSTGRES = "1"; $env:IMA_TEST_DATABASE_URL = "postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app"; uv run pytest -m postgres
```

```powershell
bun run test:caddy-routing
bun run lint
bun run test:unit
```

Confirm exact script names in `package.json` before running. New Postgres
tests must never skip under the forced-Postgres gate (conftest enforces the
count — update the expected count accordingly).

## Review Gates

Before commit, diff-review for: accidental `public.*` writes, raw-secret
handling of connector keys, legacy fallback reintroduction, non-additive
migrations, application-layer FastAPI imports, and unredacted audit payloads.
Each security-relevant negative condition needs a failing-test proof.

## Rollback

All changes are additive; disabling is via Caddy config + freeze flag exit.
No legacy artifact is removed by this task.
