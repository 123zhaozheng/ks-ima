# Research: Deletion Inventory — Legacy DB Tables and Python-side Legacy Adapters

- **Query**: Which public.* tables exist, which does Python still read/write, what is the cleanup-migration shape?
- **Scope**: internal
- **Date**: 2026-08-29

## 1. Legacy `public` schema contents (to drop after rollback window closes)

Tables (37, from drizzle DDL scan, corroborated by archived `legacy-data-inventory.md` §1):

```
account, assistant, blob, channel, chat, connector, entity, entityAccess, entityPermission,
globalSettings, item, mcpPlugin, member, mergePatchesRule, message, messageEntity, model,
order, page, pagePatch, plan, planPrice, provider, search, searchRecord, session, shortcut,
toolCall, translation, translationRecord, two_factor, usage, user, userData, verification,
workspace, workspaceInvitation
```

Plus SQL functions/triggers to drop: `kb_acl_granted`, `kb_acl_can`, `kb_nearest_acl_break`,
`kb_rebuild_one_entity_permissions`, `kb_rebuild_workspace_permissions`,
`kb_entity_permission_trigger`, `kb_member_permission_trigger`
(`drizzle/20260824004617_entity_permissions/migration.sql`), blob refCount triggers
(`drizzle/20260317054607_create_trigger/migration.sql`), zhparser FTS config objects created by
`drizzle/20260415115542_init_fts` **that belong to legacy tables only** (the zhparser extension
itself must stay — `ima` FTS uses it), and generated tsvector columns/triggers attached to
legacy tables (they drop with the tables).

Also: database `zero` (Zero CVR/change DB) — drop with compose; and the legacy flat-layout S3
objects (keys = 16-char blob ids) — migrated objects were copied to
`documents/{id}/1/source`; legacy keys become orphans after deletion (retention policy decision:
delete now via lifecycle rule or keep as cold archive; parent plan says object-store inventory is
part of rollback evidence, so object deletion should be LAST).

Commercial tables among the above (removed concepts, archive-report only): `plan, planPrice,
order, usage, channel, translation, translationRecord, mcpPlugin, assistant, search,
searchRecord, shortcut, mergePatchesRule, entityAccess`.

## 2. Python runtime code still touching `public.*` (must retire in this task)

### 2a. Identity projection WRITES — retire
- `backend/src/ima/application/identity.py:387-418` — on user create (admin/invite): if
  `public.user` exists, inserts `ima.legacy_identity_projection` pending row, upserts
  `public."user"` and `public."userData"`, marks projection complete.
- `backend/src/ima/application/identity.py:1190-1196` — same projection on profile update path.
- Spec pin to update: `.trellis/spec/backend/identity-platform-contracts.md` ("Python writes only
  the legacy public.user/userData projection, Bun keeps reading it") — contract exists solely for
  Bun readers; retire both writes and the spec clause. Decision on the
  `ima.legacy_identity_projection` table itself: keep as audit history (additive, harmless) or
  drop in cleanup migration — recommend keep (migration-history policy).

### 2b. Authorization workspace-delete legacy guards — retire
- `backend/src/ima/application/authorization.py:2484-2503` — `WORKSPACE_LEGACY_DEPENDENCY`
  checks against `public.member` / `public.entity` (guarded by `to_regclass`, so they no-op after
  drop, but they are dead code).

### 2c. Model governance legacy fallback — retire
- `backend/src/ima/application/model_governance.py:1917-1964+` `_legacy_model()` reads
  `public.model/provider/entity/workspace/globalSettings` (deliberately tolerant of absent
  tables) plus `managed_legacy_chat` / `managed_legacy_embeddings` services.
- Transport: `backend/src/ima/api/v1/model_governance.py` `internal_router`
  (`/api/v1/internal/model-governance/*`, mounted `api/app.py:271`), incl.
  `execute/legacy/chat` (`:580`), `execute/legacy/embedding` (`:618`) and rerank siblings — all
  consumed only by `src-server/kb/model-governance.ts`.

### 2d. Internal bridges (exist only for Bun) — retire
- `backend/src/ima/api/internal/session_bridge.py` — `POST /api/v1/internal/session/introspect`.
- `backend/src/ima/api/internal/authorization_bridge.py` —
  `POST /api/v1/internal/authorization/{decide,batch,member}`.
- Mounted at `backend/src/ima/api/app.py:267-271`; Caddy already 404s `/api/v1/internal/*`
  publicly. Remove routers, modules, `bridge_token` auth helpers, and the `IMA_BRIDGE_TOKEN` /
  `IMA_BRIDGE_TIMEOUT_MS` / `PYTHON_API_INTERNAL_URL` settings they consume
  (`backend/src/ima/config.py` bridge fields; compose/env keys).
- Freeze guard coupling: `application/maintenance.py` refusal is wired into the authorization
  bridge and knowledge/workspace/storage mutations. The freeze feature itself is generic
  maintenance machinery — decide keep (harmless, audited) vs simplify; it no longer guards any
  bridge once bridges are gone but still guards Python mutations during future maintenance.

### 2e. Migration CLI family (`cli.py` ~2,900 lines) — decision item
All `migrate-legacy-*` / `inventory-legacy-mcp` commands are SELECT-only on `public.*` and most
degrade via `to_regclass` when tables are absent (report zero counts / empty findings; contract
spec says review rows must still be reported when legacy tables are absent). Options:
1. Keep as historical tooling (post-drop runs report empty) — zero risk.
2. Delete commands + checkpoint queries after cutover acceptance — cleaner repo, but removes the
   ability to re-run verification against a restored pre-cutover snapshot during post-deletion
   recovery (the runbook's recovery path restores snapshot + old deployment image, which brings
   its own CLI version — so deletion is safe for recovery purposes).
Recommend option 2 for the legacy readers, KEEP the checkpoint-table history; flag as PRD decision.
Note: `test_postgres_cutover.py` rehearsal (890 lines) seeds `public.*` fixtures — must go with
the CLI commands it exercises (affects the pinned Postgres-test count, see release-gates §6).

## 3. Alembic cleanup migration (net-new, this task)

Parent plan 13.1: "add one destructive cleanup migration and keep history." No existing Alembic
migration references `public.` (grep verified). New migration `2026xxxx_NNNN_legacy_cleanup`
should (design input, not final):
- `DROP TABLE IF EXISTS public."<each of 37 tables>" CASCADE` (CASCADE absorbs triggers,
  tsvector columns, FKs; the ACL SQL functions drop explicitly or via CASCADE).
- Drop the `zero`-related DB only at compose/deployment level (separate database; not reachable
  from the `app` DB migration).
- Keep `zhparser` + `vector` extensions (used by `ima`).
- Downgrade policy: per repo convention downgrades refuse to destroy data; for a destructive
  cleanup the documented rollback is snapshot restore (`docs/legacy-cutover-runbook.md`
  Post-Deletion Recovery), not an Alembic downgrade — state this explicitly in the migration
  docstring (matches design.md 16.3: "After cleanup, rollback is database/object restore plus
  previous deployment, not an ad hoc schema downgrade").

## 4. Object storage residue

Legacy objects: flat keys = `blob.id` in `S3_BUCKET`/`IMA_STORAGE_BUCKET` (same bucket in the
example compose). Migration copied verified objects to `documents/{target}/1/source`
(`infrastructure/storage.py`). After deletion: legacy flat keys are orphans. `cleanBlobs` cron
(the only legacy GC) dies with Bun. Recommend an explicit operator step/report (list by prefix /
known id set from `ima.legacy_knowledge_migration` mapping) rather than an automatic purge —
and only after rollback-window close + snapshot no longer needed.

## 5. Contract tests pinning legacy (must be deleted/rewritten with the code)

- `backend/tests/contract/test_coexistence.py` — pins Caddy legacy catch-all `@api path /api/*`,
  `/api/mcp` NOT in Python matcher, runbook phrases, drill internals, README `/api/mcp` text,
  "no writes to public.connector" rule (the no-write rule can stay; the routing/README pins flip).
- `backend/tests/contract/test_knowledge_coexistence.py` — asserts `src-server/kb/ops.ts`,
  `kb.ts`, `kb/ingest.ts`, `kb/retrieve.ts`, `s3.ts`, `mcp.ts` exist and non-empty.
- `backend/tests/contract/test_search_coexistence.py` — asserts `src-server/kb/retrieve.ts` and
  `src/views/ChatView.vue` exist.
- `backend/tests/integration/test_postgres_cutover.py` — rehearsal over legacy fixtures.
- `backend/tests/conftest.py:24` pins exactly **48** Postgres-marked tests — update the count
  when deleting/keeping Postgres tests (hard gate: suite exits 2 on mismatch).

## Caveats / Not Found

- No SQLAlchemy ORM models for `public.*` exist in the backend (all access is raw SQL text) — no
  model layer to delete beyond the listed functions.
- `public.two_factor` / `verification` / `account` (Better Auth) tables still exist in legacy
  DDL; identity importer only read newest credential rows; safe to drop with the rest.
