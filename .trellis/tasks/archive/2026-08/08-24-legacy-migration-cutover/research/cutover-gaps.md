# Research: Cutover Gaps — What Has No Python-Side Equivalent Yet

- **Query**: What legacy data/behavior has NO Python-side equivalent yet; can cutover be complete or does it need follow-ups?
- **Scope**: internal
- **Date**: 2026-08-28

## Verdict

A **functional** cutover (Python sole writer, legacy read-only/withdrawn) is achievable with the existing
slices, but the following gaps must be closed by this task or explicitly deferred to the deletion/follow-up
task. Items marked **BLOCKER** prevent a complete cutover per parent plan phase 9
(`.trellis/tasks/08-24-python-intranet-ima-migration/implement.md:523-584`).

## Gaps

### G1. Legacy file checksum encoding mismatch — BLOCKER for blob verification
Legacy `blob.sha256`/`sha256Proof` are **base64** (`src-server/s3.ts:41-50`, `src-server/kb/ops.ts:325`,
`digest('base64')`); the Python storage phase compares them to hex digests
(`backend/src/ima/infrastructure/storage.py:134-136,158-166`). As written, every legacy file fails
`copy_verified` with `SOURCE_OBJECT_CHANGED`. Fix required: normalize base64→hex (and validate proof
semantics) in the storage phase before/at final ETL.

### G2. No bulk re-ingestion of migrated files — BLOCKER for search/Ask completeness
Knowledge storage phase leaves documents at `file_state='pending'` (`cli.py:1238-1247`) and creates **no**
`ima.ingestion_jobs`. Nothing today enqueues parse/chunk/embed for migrated versions; chunks must be rebuilt
by the target pipeline (parent plan 12.2.9). Cutover needs a bounded, resumable enqueue step over all
`file_state='pending'` migrated documents plus worker capacity planning, and a gate that counts
ready/degraded/failed documents before routing switch.

### G3. Legacy conversations are not migrated — scope decision needed
No importer for `chat/message/messageEntity/toolCall` exists (CLI command set in `cli.py:42-116`). Parent
plan step 12.2.6 says import retained conversations "according to the approved retention rule"
(`implement.md:545-546`). Options: (a) implement a conversations importer into
`ima.conversations/conversation_messages` (tables exist, migration `20260826_0007`), or (b) approve a
retention rule of "none — legacy chat history archived/read-only during rollback window". Legacy ChatView is
still compiled and retained (`backend/tests/contract/test_search_coexistence.py:4-13`), so users currently
see legacy chat; after cutover, legacy chat routes (`/api/v1/chat/*`, `/api/kb/ask`) disappear with Bun.

### G4. Delta synchronization between ETL and freeze
Legacy `/api/kb`, `/api/s3`, `/api/mcp` (readwrite), `/api/connectors` remain live writers to `public.*`
until freeze (see `legacy-code-inventory.md` §1). Checkpoints detect changed fingerprints only on rerun
(`cli.py:854-860`), so the delta strategy is "rerun all applies under freeze", but:
- entities **created** in legacy after the last pre-freeze apply are picked up (insert-on-conflict), OK;
- rows deleted in legacy are not reflected in `ima.*` (importer never deletes target rows) — need a
  reconciliation rule/report (e.g., rows present in target but soft-deleted/trashed in legacy source);
- legacy-side **moves/renames** update by fingerprint diff only if the source row is re-read — OK for entity
  rows, but folder moves change closure expectations (authorization importer uses `ON CONFLICT DO NOTHING`
  for folders, `cli.py:1589-1599`, so a changed parent on an already-imported folder will NOT be fixed on
  rerun). Delta semantics for re-parented folders need explicit handling (delete-and-reimport or targeted
  update) — **design decision required**.
- Authorization importer upserts workspaces/members (`DO UPDATE`), but folder update-on-change is absent (same
  `DO NOTHING` issue).

### G5. No write-freeze mechanism exists
There is no maintenance/freeze flag anywhere (`ima.system_settings` keys are only
`allow_registration, smtp_enabled, session_idle_seconds, session_absolute_seconds, recent_auth_seconds`,
`backend/src/ima/api/v1/admin.py:456-483`). Freeze options to design:
1. Caddy route withdrawal of legacy write paths (`/api/kb`, `/api/s3 PUT`, `/api/connectors`, `/api/mcp`
   write tools) — precedent: Zero 403 block (`Caddyfile:45-50`), drill-derived JSON rollback configs.
2. Stop the Bun service entirely during the freeze window (simplest; legacy reads also stop — acceptable
   during announced maintenance since all user reads are already on Python routes).
3. Optional app-level freeze flag in Python for extra safety against bridge-served legacy writes.
Legacy in-process cron also needs quiescing: `parseKb` every 15s writes parse state; `cleanBlobs` hourly
**deletes S3 objects** for `refCount=0` (`src-server/jobs/index.ts:18-24`,
`src-server/jobs/clean-blobs.ts`) — blob GC must be stopped before/during blob migration or verified-safe
(refcounts of migrated blobs remain ≥1 while legacy rows exist).

### G6. Connectors are inventory-only; legacy `/api/mcp` consumers need a final gate
`inventory-legacy-mcp` classifies but never converts connectors (by contract,
`backend/tests/contract/test_coexistence.py:57-69`). Cutover needs the sunset gate from the runbook: zero
pending connectors, every active consumer re-issued a Python service credential or explicitly revoked
(`docs/oauth-mcp-coexistence-runbook.md:72-78`). Removing the `/api/mcp` route itself is deletion-task scope,
but the **gate evidence** must be produced here.

### G7. Legacy search/Ask/chat parity gap during rollback window
Legacy `/api/search`, `/api/kb/search|ask`, `/api/v1/chat/completions` serve the retained ChatView and any
not-yet-migrated UI (`src-server/search.ts`, `src-server/kb.ts:40-91`, `src-server/ai.ts`). After routing
cutover they are gone. Any rollback before deletion restores them only if Bun still runs AND the Python
bridge still serves identity/authorization — rollback therefore implies keeping ima-api up (see
`coexistence-rollback-precedents.md` §3).

### G8. Model governance: imported gateways/models are disabled/unvalidated; no profiles
`migrate-legacy-model-governance` imports gateways `enabled=false` and models `enabled=false,
validated=false`; capability profiles and workspace assignments are not derived from legacy
`globalSettings`/workspace tuning (`cli.py:544-560,617-633`; report counts `workspaceTuningRows` and
`indexedChunks` as review inputs, `cli.py:428-444`). Cutover needs an admin validation step (connectivity
check, enable, publish profile versions, assign workspaces) before grounded Ask parity is real. Secrets are
re-encrypted into the Python key ring — legacy plaintext keys in `provider.settings` remain in legacy tables
until deletion (secret-safety note for the rollback window).

### G9. Zero cache still routed; frontend legacy residue
`zero-cache` route remains in Caddy (`Caddyfile:57-59,115-117`) and compose (`docker-compose.example.yml:152-173`),
though `/api/zero/*` is 403. Cutover acceptance per parent plan: "Vue no longer connects to Zero/Bun"
(`implement.md:579`) — requires verifying the shipped frontend build has no live Zero/mutation traffic; the
repo still contains `src-shared/schema.gen.ts|mutators.ts|queries.ts` and legacy views. Their deletion is the
next task, but the cutover gate needs evidence (network-level or contract test) that no browser writes go to
legacy.

### G10. `userData.perfs/data`, invitations, entityAccess, search records
Not migrated: `userData` perfs/preferences (identity apply inserts an **empty** row only,
`cli.py:2010-2013`), open `workspaceInvitation` rows (Python has its own invitations; legacy pending invites
lapse — document this), `entityAccess` (recent-views UX state), `search/searchRecord/shortcut` (removed
concepts). Decide: accept loss vs. report counts in the removed-domain archive report (parent plan 12.2.10).

### G11. Trash semantics and legacy PPTX/other formats
- Trash restoration depends on `conf.originalParentId`; rows without it stay review
  (`cli.py:795-804`) — acceptable but needs operator review counts at gate.
- Legacy parsers covered PPTX; Python MVP deliberately excludes PPTX/OCR/media
  (`.trellis/spec/backend/object-storage-ingestion-contracts.md:31`,
  archived storage research). Migrated PPTX files will parse-fail/degrade — report them explicitly in the
  ETL report (mime inventory) rather than silently.

### G12. Verification gaps vs parent plan 12.3
Existing verify steps cover identity, authorization closure/ACL, knowledge digests/tags, MCP inventory.
Still missing per parent plan: blob existence/checksum report over ALL target objects, ready chunk counts,
password verification fixture run, OAuth/service-principal state report, audit sequence continuity,
cross-role journey comparison (legacy vs Python results for list/search/ask/download). Several are net-new
commands/reports for this task.

## What is already complete (no gap)

- Identity (users/passwords/TOTP/roles), workspaces/members, folders/closure/ACL, documents/notes/versions
  metadata, tags, blob copy mechanics, gateway/model skeleton import, MCP inventory + OAuth/service-principal
  platform, all target schemas through conversations/OAuth (Alembic head `20260828_0009`).
