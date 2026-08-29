# Legacy migration and final cutover

## Goal

Implement resumable legacy ETL, schema/content/auth/ACL/blob verification, write freeze, routing cutover, and rollback runbook.

This is the last functional task before legacy deletion
(`08-24-legacy-deletion-release`): after it, all live data lives in the Python
`ima` backend and Python is the sole writer.

## Scope decisions (user-confirmed 2026-08-28)

- Conversations/chat history are NOT migrated (system not yet live). Produce a
  counts-only archive report; no importer, no Python-side chat storage model.
- Legacy connector credentials are NOT converted or reconstructed. Operators
  reissue compliant service-principal credentials or revoke/report each legacy
  key, per `docs/oauth-mcp-coexistence-runbook.md`, until the sunset gate
  (pending == 0) is met.

## Requirements

1. Checksum normalization (G1): legacy blobs store `sha256` base64; Python
   storage verification compares hex. Normalize during migration so every
   legacy blob passes `copy_verified`. Regression test with a base64 legacy
   fixture required.
2. Delta/reconciliation (G4): resumable reruns must handle legacy rows deleted
   since the last checkpoint, folder re-parenting, and trash moves. Provide an
   exit-code-gated reconciliation report listing legacy-absent-in-target and
   target-absent-in-legacy rows.
3. Re-ingestion (G2): resumable bounded bulk enqueue of migrated file versions
   through the existing worker pipeline, with capacity control and a
   ready/degraded/failed readiness report by MIME.
4. Blob verification: report over every migrated object version — HEAD-check
   checksum/size/MIME, compare counts against legacy blob rows, list orphans
   and missing objects. Exit-code gated.
5. Write freeze: enforced at the edge (stop legacy Bun service + quiesce its
   cron) with an optional typed `ima.system_settings` maintenance flag that
   makes Python refuse bridge-served mutations. Freeze entry/exit recorded as
   `ima.audit_events`.
6. Routing drill: generalize `scripts/caddy-routing-drill.ts` to derive and
   validate cutover JSON and rollback JSON with evidence artifacts (same
   format as existing drill phases).
7. Cutover runbook: `docs/legacy-cutover-runbook.md` mirroring the OAuth/MCP
   runbook structure (pre-flight, freeze, cutover steps, pre-deletion
   rollback, post-deletion recovery), pinned by a contract test.
8. Rehearsal: an automated test path exercising the full
   apply→verify→freeze→delta→cutover→rollback sequence on a disposable
   sanitized dataset with recorded results.

## Constraints

- No deletion of legacy code, tables, or Caddy routes — that belongs to
  `08-24-legacy-deletion-release`. This task must preserve rollback artifacts.
- No dual-write architecture: legacy remains the source until freeze; Python
  is the sole writer after cutover.
- No mutation of `public.connector` rows; no reconstruction of raw legacy
  secrets; connector handling is inventory + reissue/revoke only.
- Digest/pepper compatibility rules from the identity migration must not be
  re-derived or altered (see `research/standards-from-sibling-tasks.md`).
- All new commands follow existing `ima` CLI plan/apply/verify/report
  conventions; application services stay transport-neutral.

## Acceptance Criteria

- [ ] G1 fix landed with a base64-checksum regression test; storage verify
      passes on migrated legacy blobs.
- [ ] Reconciliation and blob verification reports exist as CLI commands with
      exit-code gates and tests covering delete/re-parent/trash deltas.
- [ ] Re-ingestion enqueue is resumable and bounded; readiness report covers
      ready/degraded/failed by MIME.
- [ ] Freeze mechanism implemented with audit events; contract test proves
      bridge-served mutations are refused during freeze.
- [ ] Routing drill produces cutover + rollback evidence and both validate.
- [ ] Cutover runbook document exists and is pinned by a contract test.
- [ ] End-to-end rehearsal test on sanitized data passes.
- [ ] Full backend quality matrix green (ruff, mypy, pytest, forced Postgres).

## Notes

- See `design.md` for the phase plan and module layout, `implement.md` for
  ordered execution, and `research/` for evidence (data/code inventories,
  gaps G1–G12, sibling-task standards).
- Environment reality: not yet in production, so freeze/cutover can stop the
  Bun service outright; keep the mechanisms production-shaped anyway.
