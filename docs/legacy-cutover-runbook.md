# Legacy Migration Cutover, Rollback, and Recovery

This runbook covers the final cutover from the legacy Bun service to the
Python `ima` backend. It mirrors `docs/oauth-mcp-coexistence-runbook.md`:
pre-flight gates, write freeze, cutover steps, pre-deletion rollback, and
post-deletion recovery. Connector credentials are handled exclusively through
the OAuth/MCP runbook's inventory, reissue, and revoke flow; this runbook
never reconstructs or converts a legacy key.

## Current State

- Until cutover, the legacy Bun service remains the source of truth for
  `/api/*` catch-all traffic; Python already serves identity, OAuth/MCP,
  workspace/knowledge, and storage APIs on its explicit paths.
- `/api/v1/internal/*` remains public `404` in every phase.
- Conversation/chat history is not migrated (the system was never live).
  Only a counts-only archive report is produced:
  `migrate-legacy conversations-archive` with decision `counts_only_archive`.

## Pre-Flight Gates

Run all commands from `backend/`. Every gate must be recorded as release
evidence before freeze entry is approved.

1. Read-only inventory:

   ```powershell
   cd backend
   uv run ima migrate-legacy report-all
   ```

   Reports legacy row counts per table, blob bytes, the MIME histogram with
   unsupported types flagged, the delta probe against the last checkpoint
   pass, and the connector pending list. Exit code `4` while any connector
   remains pending.

2. Apply chain in dependency order (rerun until review/failed sets are
   stable and operator-accepted):

   ```powershell
   uv run ima migrate-legacy-identity apply
   uv run ima migrate-legacy-authorization apply
   uv run ima migrate-legacy-knowledge apply
   uv run ima migrate-legacy-model-governance apply --mapping-file .\operator-mapping.json
   ```

3. Gate V1, data equivalence (each command exits non-zero on failure):

   ```powershell
   uv run ima migrate-legacy-identity verify
   uv run ima migrate-legacy-authorization verify
   uv run ima migrate-legacy-knowledge verify
   uv run ima migrate-legacy blob-verify
   uv run ima migrate-legacy reconcile-report all
   uv run ima inventory-legacy-mcp verify --mapping-file .\approved-mcp-decisions.json
   ```

   `blob-verify` HEAD-checks every migrated object version (checksum, size,
   MIME) against legacy blob rows and lists missing, corrupt, and orphan
   objects. `reconcile-report` lists legacy-absent-in-target and
   target-absent-in-legacy rows with rule decisions for delete, re-parent,
   and trash deltas.

4. Gate V2, content readiness:

   ```powershell
   uv run ima migrate-legacy reingest enqueue --reingest-limit 50 --reingest-max-active 8
   uv run ima migrate-legacy reingest report
   ```

   Enqueue is resumable and bounded by worker capacity; reruns skip versions
   that already have pipeline jobs. The report classifies every migrated
   file version as ready/degraded/failed/pending by MIME type.

5. Gate V3, auth/ACL live checks: run the backend contract and policy
   suites against the migrated data (`uv run pytest`), including the
   bridge freeze contract.

6. Gate V4, operational readiness: a fresh database snapshot identifier and
   checksum, the object-store bucket inventory, and the deployment image
   digests plus Caddyfile SHA-256. Record the snapshot triple without
   recording secret values. Rehearse the sequence on a disposable sanitized
   dataset via the PostgreSQL rehearsal test before touching production
   data.

## Write Freeze

Freeze at the edge first, then raise the typed flag:

1. Stop the legacy Bun service. This also quiesces its parseKb/cleanBlobs
   cron. From this moment legacy cannot write.
2. Enter the typed freeze:

   ```powershell
   uv run ima maintenance freeze enter --operator-id <super-admin-user-id> --reason "legacy cutover"
   ```

   While `ima.system_settings.maintenance_write_freeze` is true, Python
   refuses bridge-served mutations and service-level writes with a safe
   RFC 9457 maintenance problem; migration-tagged writers (the `ima` CLI
   delta passes) keep working. Enter and exit are recorded as
   `ima.audit_events` (`maintenance.freeze.enter` / `maintenance.freeze.exit`)
   with redacted metadata only.

3. Verify zero legacy write traffic and confirm `uv run ima maintenance
   freeze status` reports `frozen: true`.
4. Run the final delta: rerun the apply chain, then `blob-verify` and
   `reconcile-report all` again. Gate V1 must be clean before routing
   changes. Complete or explicitly accept remaining re-ingestion state
   (Gate V2 rerun).

## Cutover Steps

1. Approve gates V1–V4 and record the approval as an audit event.
2. Take the rollback anchors: database snapshot identifier and checksum,
   object-store inventory, image digests, and Caddyfile SHA-256.
3. Derive and validate the routing evidence with the pinned
   `caddy:2.10.2-alpine` image:

   ```powershell
   bun run test:caddy-routing
   ```

   The drill validates the current config, derives the temporary `cutover.json`
   (every legacy `/api/*` upstream withdrawn to Python and `/api/mcp`
   answered with a terminal `410`) and the temporary `rollback.json`
   (canonical `/mcp` withdrawn with a local `404`), validates both, and
   restores the unmodified root Caddyfile. Retain the deterministic JSON
   output with the release evidence; it is safe configuration metadata and
   contains no credentials, database identifiers, or protected content.
   The drill does not deploy a rollback or modify the production Caddyfile.

4. Load the cutover JSON on the deployment edge. After this step all
   `/api/*` traffic reaches Python, legacy upstreams are withdrawn, and
   `/api/mcp` returns `410`. Legacy MCP consumers move to canonical `/mcp`
   per the OAuth/MCP runbook; the Bun service stays stopped.
5. Run the smoke matrix on migrated data: platform admin, workspace admin,
   editor, viewer, restricted-folder user, OAuth agent (kb:read/ask/write),
   service principal, and an MCP SDK handshake on `/mcp`.
6. Monitor auth failures, policy denials, queue age, ingestion failures,
   and storage errors through the rollback window.
7. Declare cutover. The legacy tables, images, and configuration remain
   untouched for the rollback window; nothing is deleted by this task.

## Pre-Deletion Rollback

During the rollback window (legacy stopped but retained):

1. Redeploy the retained `rollback.json` produced by the drill.
2. Restart the retained Bun image ONLY with the Python identity bridge
   still up. Legacy `public.session` is empty, so a Bun-only restoration
   cannot authenticate; never restore legacy sessions without Python.
3. If any Python-side write happened after freeze entry, restore the
   freeze-time database snapshot and matching object-store inventory first,
   then invalidate Python sessions.
4. Re-enter dual-run routing (the unmodified root Caddyfile), exit the
   freeze (`uv run ima maintenance freeze exit --operator-id <id>`), and
   rerun the delta apply chain plus Gate V1.

## Post-Deletion Recovery

After legacy deletion (handled by the separate legacy-deletion release),
do not attempt a mixed rollback. Stop public traffic, restore the
identified pre-cutover database snapshot to its recorded recovery point
together with the matching object-store inventory, deploy the recorded
image and configuration checksums, validate privately, and only then
reopen traffic. A deployment against a post-deletion database with legacy
code is not supported.

## Evidence Checklist

- `migrate-legacy report-all` output with empty connector pending list.
- Gate V1 outputs: verify commands, `blob-verify`, `reconcile-report`,
  inventory verify.
- Gate V2 output: `reingest report` readiness by MIME.
- Freeze enter/exit audit rows and `freeze status` captures.
- `bun run test:caddy-routing` deterministic output including the
  `cutover` and `pre_sunset_rollback` phases, image digest, and Caddyfile
  SHA-256; retained `cutover.json` and `rollback.json` artifacts.
- Database snapshot identifier and checksum, object-store inventory, image
  digests, and Caddyfile SHA-256 (snapshot triple).
- `conversations-archive` counts-only report.
- Cutover approval audit event and smoke matrix results.

## Evidence Not Claimed Here

This runbook and the local drill do not claim external-client acceptance,
deployed public-origin smoke results, database snapshot/PITR restoration
evidence, or operator approval of the gates above. It does not deploy a
rollback, delete any legacy artifact, or authorize the legacy-deletion
release. Record those results only after executing them against the real
deployment.
