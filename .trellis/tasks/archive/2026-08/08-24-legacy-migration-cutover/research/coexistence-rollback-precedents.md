# Research: Coexistence and Rollback Precedents

- **Query**: Reusable patterns from docs/oauth-mcp-coexistence-runbook.md and the caddy-routing-drill for write freeze / cutover / rollback drills.
- **Scope**: internal
- **Date**: 2026-08-28

## 1. The OAuth/MCP coexistence runbook (`docs/oauth-mcp-coexistence-runbook.md`)

The repository already ran one full coexistence→sunset→rollback cycle for the MCP slice. Its structure is the
direct template for the final cutover runbook:

1. **Routing section** — canonical new resource published (`/mcp`), legacy route retained with legacy
   semantics (`/api/mcp`), compatibility alias explicitly reserved but disabled, internal routes stay 404
   (`runbook:3-9`).
2. **Inventory and classification** — deterministic read-only report → operator-reviewed decision file
   (connector id → `reissued`|`revoked`) → privileged `apply` (requires active super_admin, writes only safe
   count telemetry to audit in one transaction, never mutates legacy rows) → `verify` with exit codes:
   `4` pending rows, `2` invalid input, `3` unauthorized (`runbook:11-35`; implementation
   `backend/src/ima/cli.py:192-247`).
3. **Pre-sunset rollback** (ordered steps, `runbook:37-71`):
   - Record/verify evidence first: retained Bun image digest, Caddy/config checksum, DB snapshot id+checksum,
     PostgreSQL recovery point, secret-version ids — **without secret values**.
   - Confirm legacy route still reachable and only existing legacy-credential holders eligible.
   - Route eligible clients back to legacy route.
   - Withdraw the new canonical route.
   - Verify legacy semantics (initialize, tools/list, modes, expiry, root denial, revocation).
   - Leave additive `ima.*` schema/audit rows intact; **never reconstruct raw credentials**.
4. **Sunset gate** (`runbook:72-78`): no pending inventory items; every consumer re-issued or explicitly
   revoked; interoperability evidence accepted; **fresh DB snapshot + exact previous deployment
   image/config recorded; sunset approval explicitly authorizes compatibility-route removal** (removal itself
   belongs to the deletion task).
5. **Post-sunset recovery** (`runbook:80-82`): no mixed rollback after deletion — stop traffic, restore
   pre-cutover snapshot to recorded recovery point, deploy matching image/config checksums, validate privately,
   then reopen.
6. **Explicit non-claims** (`runbook:84-89`): the drill proves routing shape only, not client interop, not
   production rollback.

Contract test `backend/tests/contract/test_coexistence.py:36-54` pins this runbook's ordering (legacy-route
confirmation before canonical withdrawal, snapshot boundary phrases, drill command, pinned Caddy image).

## 2. The Caddy routing drill (`scripts/caddy-routing-drill.ts` + `caddy-routing-drill.test.ts`)

Reusable, evidence-producing routing rehearsal (`package.json`: `bun run test:caddy-routing`):

- Pins `CADDY_IMAGE = 'caddy:2.10.2-alpine'` (`drill.ts:6`) and the full route matrix:
  `PYTHON_PATHS` (health/system/identity/mcp/workspace/storage), `BUN_PATHS = ['/api/mcp', '/api/legacy-check']`,
  `ZERO_PATHS`, internal path (`drill.ts:8-22`).
- Runs the repo's real root `Caddyfile` in ephemeral, uniquely named containers with random host ports and
  local marker upstreams; validates current config on both public listeners (`drill.ts:200-220,286+`).
- **Derives a separate temporary rollback JSON** via `caddy adapt` (`buildRollbackConfig`, `adaptCaddyfile`
  `drill.ts:269+`) — e.g., pre-sunset rollback withdraws canonical `/mcp` with a local 404 — then restores and
  revalidates the unmodified root Caddyfile. Cleanup runs on success/failure/cancel and targets only
  containers it created.
- Emits deterministic JSON evidence: resolved image digest (`imageDigest`), root Caddyfile SHA-256
  (`caddyfileSha256`), route status, marker destination (`drill.ts` phase evidence; asserted in
  `caddy-routing-drill.test.ts:13-54`).
- Test contract also asserts rollback derivation does not mutate unrelated routes
  (`caddy-routing-drill.test.ts:24-46`).

**Reuse pattern for final cutover**: generalize the drill to a cutover variant that derives the
post-cutover JSON (all `/api/*` to Python, legacy upstreams withdrawn/404-or-410) and the rollback JSON
(restore legacy catch-all for retained paths), each validated against marker upstreams, with the same
digest/checksum evidence record.

## 3. Bridge fail-closed coexistence (identity + authorization)

Precedent from the identity/workspace slices:

- Bun sessions are introspected through Python; bridge failure ⇒ unauthenticated
  (`src-server/auth/session.ts:28-40`).
- ACL decisions go through the Python authorization bridge; bridge unavailable/malformed/partial ⇒ deny
  (`src-server/utils/permissions.ts:124-155,192-216`; Python side fail-closed
  `backend/src/ima/api/internal/authorization_bridge.py`). Spec formalizes: "deny; never legacy-allow target
  data" and migration checkpoints fail safely (`.trellis/spec/backend/workspace-authorization-contracts.md:58-62,80-81`).
- Identity migration docs define the session-cutover rollback: restore previous Caddy/frontend artifact and DB
  snapshot, invalidate Python sessions; passwords never reverse-synced (`docs/identity-migration.md:22-24`).
  Note: `public.session` is emptied during identity migration (`backend/src/ima/cli.py:2029-2033`), so
  **legacy-only browser auth cannot be restored from data** — rollback always needs the Python bridge or a
  full pre-identity snapshot.

## 4. Migration command discipline (reused by every slice)

Every legacy migration CLI follows the same operational contract (pattern to keep for the final ETL):

- Actions `plan | apply | verify | report` (single positional arg, default `report`,
  `cli.py:102-104`).
- Read-only by default; `apply` never deletes/mutates legacy product rows (identity apply deleting
  `public.session` is the documented single exception tied to session revocation).
- Deterministic JSON summaries, `secretValues: false` flags, no content/key material in reports.
- Exit-code contract for gates: nonzero on verification failure (identity `cli.py:2122-2126`,
  authorization `cli.py:1838-1839`, knowledge `cli.py:1156-1164`, mcp inventory `cli.py:246-247` codes
  2/3/4).
- Per-record checkpointing with `source_fingerprint`, statuses `running|complete|failed|review`,
  attempts counter — resume = rerun apply (see `migration-tooling-state.md`).

## 5. Deployment/evidence patterns

- Compose already separates `ima-migrate` as a one-shot pre-deploy job with
  `condition: service_completed_successfully` for api/worker (`docker-compose.example.yml:73-75,97-99,101-115`)
  — the cutover delta run can reuse this pattern as an explicit job rather than an implicit side effect.
- Integration rehearsal harness exists: `ima-integration` compose service runs migrations + pytest against a
  real Postgres (`docker-compose.example.yml:117-133`); identity e2e seeding via
  `backend/scripts/seed_identity_e2e.py`.
- Caddy image pin + Caddyfile digest + DB snapshot id as the rollback evidence triple is already the accepted
  standard (runbook §Pre-Sunset Rollback, drill evidence fields).

## Caveats / Not Found

- No existing write-freeze mechanism (no maintenance flag in `ima.system_settings`; current keys are
  `allow_registration`, `smtp_enabled`, session lifetimes — `backend/src/ima/api/v1/admin.py:456-483`).
  Freeze so far was achieved by route withdrawal (Zero 403) and runbook ordering, not by an app-level switch.
- The routing drill currently covers MCP-route rollback only; it does not exercise legacy write shutdown or
  database snapshot restore. Those are net-new for this task.
