# Research: Ordering Constraints — Rollback Window, Sunset Gate, What Deletes When

- **Query**: What must remain until sunset vs what can delete now; connector sunset status; /api/mcp retirement scope.
- **Scope**: internal
- **Date**: 2026-08-29

Sources: `docs/legacy-cutover-runbook.md`, `docs/oauth-mcp-coexistence-runbook.md`,
`.trellis/tasks/08-24-python-intranet-ima-migration/implement.md` (§12-13),
`.trellis/tasks/archive/2026-08/08-24-legacy-migration-cutover/research/coexistence-rollback-precedents.md`.

## 1. The boundary: rollback-window closure is the deletion gate

Parent Final Acceptance (§13): "Rollback window is closed only after user/operator acceptance and
verified backup." Task goal says deletion happens "after rollback acceptance". Concretely the
pre-deletion state required (from legacy-cutover-runbook):

- Gates V1-V4 approved and recorded as audit event; cutover declared.
- Snapshot triple recorded: DB snapshot id+checksum, object-store inventory, image digests +
  Caddyfile SHA-256; retained `cutover.json`/`rollback.json` drill artifacts.
- Monitoring through the window (auth failures, policy denials, queue age, ingestion failures,
  storage errors) shows nothing requiring rollback.
- User/operator acceptance of the migrated system.

Before that boundary, the **Pre-Deletion Rollback** path must stay executable
(runbook §Pre-Deletion Rollback): redeploy retained `rollback.json`; restart retained Bun image
ONLY with the Python identity bridge still up; restore freeze-time snapshot if Python wrote;
re-enter dual-run; exit freeze; rerun delta apply chain + Gate V1.

## 2. What can be deleted in-repo immediately vs what must wait

### Can delete in the deletion release (repo code/config) — provided the release is gated on rollback-window closure

Deletion of repo code does not by itself break pre-deletion rollback, because that path restores
**retained images and artifacts** (Bun image digest, rollback.json, snapshot), not repo builds —
with two exceptions below. So the practical rule: **merge + deploy the deletion release only after
window closure is recorded.**

### Must remain FUNCTIONAL in the deployed Python image until window closure (order-sensitive)

1. **Session bridge** `POST /api/v1/internal/session/introspect` — a restarted Bun cannot
   authenticate without it (`public.session` is empty; runbook: "never restore legacy sessions
   without Python").
2. **Authorization bridge** endpoints — Bun ACL decisions fail-closed without it (readable
   but unusable legacy).
3. **Identity projection writes** (`public."user"`/`"userData"` upserts) — users created during
   the window must remain visible to a restarted Bun.
4. **`migrate-legacy-*` CLI in the deployed image** — the pre-deletion rollback path reruns the
   delta apply chain and Gate V1 against the CURRENT deployment. If the deletion release strips
   these commands from `ima`, pre-deletion rollback additionally requires redeploying the prior
   `ima-api` image. DESIGN DECISION for the PRD: (a) keep migration CLI until window closure and
   delete in a follow-up, or (b) document that pre-deletion rollback restores the prior Python
   image too.
5. **Freeze enter/exit + bridge-refusal wiring** — rollback path exits freeze and relies on the
   freeze semantics; delete together with bridges, not before.

### Must wait until AFTER window closure (destructive, point of no return)

- Alembic cleanup migration dropping the 37 `public` tables + ACL functions/triggers.
- Retirement of bridge endpoints, projection writes, legacy model adapters, legacy CLI readers.
- Caddy terminal routing change in the real deployment (the cutover JSON already does this at the
  edge — the committed Caddyfile update merely catches up).
- Legacy flat-key S3 object purge (LAST; only after the snapshot it protects is itself retired).
- `zero` database and `zero-cache-data` volume removal at deployment level.

### Sunset approval content (oauth-mcp runbook §Sunset Gate — template for the whole deletion)

- No pending inventory items (connectors pending == 0).
- Every active consumer re-issued a Python service credential or explicitly revoked.
- Interoperability evidence accepted.
- Fresh DB snapshot + exact previous deployment image/config recorded.
- Approval explicitly authorizes compatibility-route removal ("This child task does not perform
  that removal" — the removal belongs to THIS deletion task).

## 3. Connector sunset gate status tooling

- `uv run ima inventory-legacy-mcp report|apply|verify --mapping-file ...`
  (`backend/src/ima/cli.py:192-247`, `application/legacy_mcp_inventory.py`):
  exit 4 = pending rows remain, 2 = invalid input, 3 = unauthorized. `apply` requires active
  super_admin, writes only audit telemetry, never mutates `public.connector`.
- `uv run ima migrate-legacy report-all` includes the connector pending list and exits 4 while
  any connector is pending (runbook Pre-Flight §1).
- Decision file maps connector id → `reissued|revoked`; `reissued` means a Python service
  principal was separately issued (no key conversion ever).
- After deletion, these commands lose their source table — keep or remove per python-db
  inventory §2e decision; the gate evidence must be captured BEFORE deletion.

## 4. Is legacy `/api/mcp` retirement part of this task? YES

- Cutover already answers `/api/mcp` with terminal `410` in the derived `cutover.json`
  (drill `buildCutoverConfig`; runbook Cutover step 4).
- This task removes the handler itself (`src-server/mcp.ts`), the connector key APIs/UI,
  `ima_` bearer utilities (`src-server/utils/permissions.ts generateApiKey`, key hash checks),
  legacy MCP scripts, and repoints user-facing config to `/mcp`:
  `src/utils/mcp-config.ts` (+test), `ConnectorCreatedDialog.vue` hint text, README block,
  `test_coexistence.py` README assertions.
- The disabled-by-default Python `/api/mcp` compatibility alias stays disabled/nonexistent
  (oauth runbook: reserved for an explicitly approved post-legacy routing change; config
  `mcp_resource_path` is hard-locked to `/mcp`).
- Evidence to capture first: inventory verify exit 0 (pending == 0) with approved decisions file.

## 5. Recommended ordered phases (input to deletion plan)

Phase A — Gate evidence & acceptance (no deletion):
1. Confirm rollback acceptance recorded; freeze status decided (see §6 open question).
2. Run sunset evidence: `inventory-legacy-mcp verify` exit 0; `migrate-legacy report-all`;
   record fresh snapshot triple + image digests (sunset approval).

Phase B — Repo deletion (single release branch, gates green before merge):
3. Frontend: rewire shell stores (workspace/user-data/perfs/require-login/RedirectToFolder/
   InvitationLayout/MainDrawer/admin EmptyPage) onto identity-client/TanStack Query; delete
   legacy views/components/services, Zero runtime, hc client, legacy connector UI; repoint
   mcp-config to `/mcp`.
4. Delete `src-server/`, `src-shared/` (after relocating pure utils), legacy scripts, drizzle
   configs/dir, Dockerfile.server, dev-db/dev-pg; update package.json scripts/deps + bun.lock.
5. Python: remove bridges, projection writes, legacy model adapters, legacy workspace guards,
   legacy CLI readers (per §2 decision); update coexistence contract tests (replace with
   post-deletion invariants); update conftest postgres count; add Alembic cleanup migration
   (last migration in the chain).
6. Deployment artifacts: Caddyfile terminal form, docker-compose.example.yml, .env.example,
   README, CI workflows (drop nyaai-server, add backend images), drill rewrite.
7. Run FULL gate matrix (release-gates.md) incl. e2e + drill + forced-Postgres + residue search.

Phase C — Deploy + destructive close (post-merge, change-controlled):
8. Deploy web/api/worker images; `ima-migrate` applies the cleanup migration (tables drop).
9. Verify terminal routing (410/404 evidence), health, smoke matrix on real deployment.
10. Later, separately: purge orphan legacy S3 keys and retire the pre-cutover snapshot only per
    data-retention approval; update runbooks/docs to "sunset complete".

## 6. Open operational question (runbook gap)

The cutover runbook enters the write freeze before routing changes but its success path never
lists `maintenance freeze exit` (only the rollback path does). While frozen, Python refuses
mutating knowledge/workspace actions — normal product use requires exiting freeze after
acceptance. The deletion PRD should pin: freeze exit happens at (or before) rollback-window
closure with an audit event, and the deletion release verifies `freeze status` is `frozen: false`
as a pre-condition (deleting the freeze machinery while it is still engaged would strand the
deployment read-only).

## Caveats / Not Found

- No telemetry/metrics wiring exists to prove "zero legacy write traffic" beyond Caddy access
  logs — evidence is operator-collected.
- `conversations-archive` counts-only report is already produced by the cutover task; no chat
  retention obligation blocks ChatView deletion.
