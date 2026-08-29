# Migration Design Input (Summary for design.md)

- **Query**: Synthesis of research into recommended ETL phases, verification gates, write-freeze mechanism, cutover and rollback procedure.
- **Scope**: internal synthesis (evidence in sibling files in this directory)
- **Date**: 2026-08-28

Companion files: `legacy-data-inventory.md`, `legacy-code-inventory.md`,
`coexistence-rollback-precedents.md`, `migration-tooling-state.md`, `cutover-gaps.md`,
`standards-from-sibling-tasks.md`.

## 0. Current position (evidence-based)

- All eight platform slices are live on Python behind Caddy; legacy Bun remains only for
  `/api/mcp` (legacy connector keys), `/api/kb`, `/api/s3`, `/api/search`, `/api/v1/chat/*`,
  `/api/connectors`, and retained ChatView. Zero mutate/query is already 403 at the edge.
- Bun no longer has its own identity: every legacy browser route authenticates and authorizes through the
  Python bridge (fail-closed). Legacy `public.session` was emptied by identity migration.
- Resumable importers already exist and have been exercised by tests for: identity, authorization
  (workspaces/members/folders/closure/ACL), model governance (disabled imports), knowledge metadata + blob
  copy, MCP connector inventory. Checkpoint tables and verify semantics are established.
- Not yet done: checksum-format fix, bulk re-ingestion, delta/freeze discipline, conversations decision,
  write-freeze mechanism, final equivalence reports, cutover/rollback runbook and drill.

## 1. Recommended ETL phases (build on existing commands; no new engine)

Phase A — Pre-flight (read-only, repeatable any time):
1. `migrate-legacy-{identity,authorization,model-governance,knowledge} report` + `inventory-legacy-mcp report`.
2. New inventory additions: row counts per legacy table, blob count/total bytes, MIME histogram (flag PPTX/
   unsupported), legacy rows created/updated since last checkpoint pass (delta probe), connector pending list.
3. Snapshot evidence triple: DB snapshot id/checksum + PITR point, object-store bucket inventory, deployment
   image digests + Caddyfile sha256 (drill evidence format).

Phase B — Background bulk import (dual-run, legacy still writing):
4. Fix G1 (base64→hex checksum normalization) before storage apply.
5. Run applies in dependency order: identity → authorization → knowledge metadata → storage copy → model
   governance (with operator mapping file). Rerun until `review/failed` sets are operator-accepted and stable.
6. New: bounded re-ingestion enqueue for migrated file versions (G2) with worker capacity control; track
   ready/degraded/failed per MIME.

Phase C — Write freeze + final delta (announced maintenance window):
7. Freeze legacy writes (§3). Stop legacy cron (parseKb, cleanBlobs) — quiesce before blob work.
8. Rerun the full apply chain as delta (checkpoints skip unchanged rows); handle G4 reconciliation rules:
   legacy-deleted rows, re-parented folders (delete-and-reimport decision), trash changes.
9. Re-verify storage for any blob touched since last pass; finish remaining re-ingestion or mark degraded
   explicitly.

Phase D — Cutover (§4) then rollback window, then handoff to deletion task.

## 2. Verification gates (map to parent plan 12.3)

Gate V1 — Data equivalence (CLI, exit-code gated):
- identity verify (0 failed, 0 legacy sessions, per-user invariants);
- authorization verify (membership, parent, closure-set, ACL-set equivalence);
- knowledge verify (fingerprints, digests per version, tags, lifecycle, trash placement);
- NEW blob report: every `document_file_versions` object HEAD-verified (checksum/size/MIME); counts vs
  legacy blob rows; orphans + missing listed;
- NEW reconciliation report: legacy rows absent in target and vice versa; connector inventory pending == 0.

Gate V2 — Content/search readiness:
- ingestion report: documents ready vs degraded (keyword-only) vs failed, by MIME; PPTX/unsupported listed;
- spot-diff legacy vs Python search/Ask results on a frozen fixture workspace (role matrix: admin, editor,
  viewer, restricted-folder user) — reuse bridge-era comparison approach.

Gate V3 — Auth/ACL live checks:
- policy contract suite against migrated data (REST/search/Ask/download/MCP/OAuth/service principal);
- connector/service-credential smoke on `/mcp`; legacy-key smoke on `/api/mcp` until its sunset gate.

Gate V4 — Operational readiness:
- fresh backup + restore rehearsal on a disposable copy (duration recorded); drill evidence for both
  cutover and rollback Caddy JSON; runbook approval recorded (audit event, like inventory apply).

## 3. Write-freeze mechanism (recommended)

1. Announce maintenance; freeze is enforced at the edge, not by app flags (consistent with precedent):
   - Derive a freeze Caddy config (drill-style `buildRollbackConfig` generalization): legacy write paths
     (`/api/kb` mutations cannot be split from reads at route level, so simplest safe form = route the whole
     retained legacy surface to a static 503/410 maintenance responder, or stop the Bun service), keep
     Python routes.
   - Preferred: **stop the legacy Bun service** for the window (its only live consumers are legacy chat and
     connector keys; both tolerate the maintenance window; bridge dependency means Bun alone cannot serve
     anyway if Python degrades).
2. Quiesce legacy cron by service stop (parseKb/cleanBlobs) — mandatory before blob verification.
3. Optional belt-and-suspenders: a typed `ima.system_settings` maintenance flag that makes Python refuse any
   bridge-served mutation and any internal write not tagged `migration` — small, audited, reversible.
4. Freeze entry/exit are audit events (`ima.audit_events`), mirroring `legacy.mcp.inventory` pattern
   (`cli.py:230-244`).

## 4. Cutover procedure (recommended, mirrors design.md 16.3 and runbook ordering)

1. Approve + record gate evidence (V1–V4); record approval as audit event.
2. Enter freeze (§3); verify zero legacy write traffic (access logs / counters).
3. DB snapshot + object-store inventory + image/config digests (rollback anchors).
4. Run final delta applies + storage verify + reconciliation (Gate V1 rerun, must be clean).
5. Complete/accept re-ingestion state (Gate V2); rebuild/verify FTS+vector indexes if any manual step used.
6. Switch Caddy to cutover JSON: all `/api/*` to Python incl. `/api/mcp` decision (either route `/api/mcp`
   to Python compatibility only if explicitly approved per runbook §Routing, else 404/410 with consumers
   already moved to `/mcp`); withdraw legacy upstreams; keep internal bridge up for nothing — Bun stopped.
7. Deploy final frontend build; verify no Zero/legacy traffic (network evidence).
8. Smoke matrix on migrated data: platform admin, workspace admin, editor, viewer, restricted user, OAuth
   Agent (kb:read/ask/write), service principal; plus MCP SDK handshake on `/mcp`.
9. Monitor: auth failures, policy denials, queue age, ingestion failures, S3 errors, gateway errors.
10. Declare cutover; start rollback window (legacy services stopped but images/config/snapshots retained;
    legacy tables untouched).

## 5. Rollback procedure (two regimes, per precedent)

Pre-deletion (during rollback window):
1. Stop cutover traffic; redeploy pre-cutover Caddy JSON (drill-derived, evidence-recorded).
2. Restart retained Bun image (digest-recorded) ONLY if Python identity/authorization bridge also restored —
   because legacy browser sessions live in `ima.sessions` now and legacy `public.session` is empty, a
   Bun-only restoration cannot authenticate users. Rollback therefore means: Python API stays up (identity +
   bridge), legacy routes serve legacy data again.
3. If Python-side writes occurred after freeze, restore the freeze-time DB snapshot + object inventory before
   re-enabling legacy routes (legacy tables were read-only during window, so legacy data is consistent at the
   snapshot point); invalidate Python sessions per `docs/identity-migration.md:22-24`.
4. Document failed verification; re-enter dual-run; rerun delta.

Post-deletion (after `08-24-legacy-deletion-release`): no mixed rollback — full restore of pre-cutover
snapshot + matching images/config, per runbook §Post-Sunset Recovery.

## 6. Deliverable checklist for this task (candidate PRD requirements)

- [ ] G1 checksum normalization fix + regression test (base64 legacy fixtures).
- [ ] G4 delta/reconciliation rules for deletes and folder re-parenting.
- [ ] Resumable re-ingestion enqueue + readiness report (G2).
- [ ] Blob verification report over all migrated objects (V1 addition).
- [ ] Conversations retention decision + importer or archive report (G3).
- [ ] Write-freeze mechanism (edge withdrawal and/or system flag) + audit events (G5).
- [ ] Generalized routing drill: cutover JSON + rollback JSON + evidence artifact.
- [ ] Final cutover runbook doc (docs/), mirroring oauth-mcp runbook structure, pinned by contract test.
- [ ] Connector sunset gate evidence (pending==0) (G6).
- [ ] Model governance admin validation + profile publication step evidence (G8).
- [ ] Removed-domain archive/count report (plan 12.2.10).
- [ ] Rehearsal on production-size sanitized copy with recorded durations (plan 12.4).

## 7. Explicit non-goals for this task

- No deletion of src-server, Zero, drizzle, legacy tables, or legacy Caddy routes (next task owns it).
- No conversion of legacy connector secrets; no reconstruction of raw keys.
- No dual-write architecture; legacy remains source until freeze, Python sole writer after cutover.
- No legacy-session restoration; rollback always involves the Python identity service.
