# Research: Standards and Evidence from Prior Sibling Tasks Constraining Migration

- **Query**: Which standards/evidence from archived sibling task research and specs constrain the final migration?
- **Scope**: internal
- **Date**: 2026-08-28

Sources: `.trellis/tasks/archive/2026-08/*/research/*.md`, `.trellis/spec/backend/*.md`,
`docs/*.md`, and contract tests that encode those decisions.

## 1. Identity / credential format constraints (local-identity-platform-admin)

Research: `archive/2026-08/08-24-local-identity-platform-admin/research/identity-bridge.md` (415 lines).

- Argon2id via `argon2-cffi`; only PHC strings parseable by the Python verifier may be imported
  (`backend/src/ima/application/legacy_identity.py:13-21` implements this: `$argon2id$` prefix,
  `extract_parameters` succeeds, `Type.ID`, `hash_len >= 16`). Incompatible hashes ⇒ forced reset, never
  re-encoded guesses. Spec: `.trellis/spec/backend/identity-platform-contracts.md:48-53` — checkpoints in
  `ima.legacy_identity_migration`, sessions revoked, tokens never copied; Python writes only the legacy
  `public.user`/`userData` projection, Bun keeps reading it.
- Pepper/digest handling: `ima.sessions`, `ima.auth_tokens`, invitations store **peppered opaque digests**
  (`oauth-mcp evidence:17,19,26` citing migration `20260824_0002:26,44`); peppers (`IMA_SESSION_PEPPER`,
  `IMA_TOKEN_PEPPER`) and `IMA_TOTP_ENCRYPTION_KEY` must be set to independent high-entropy values before
  production and only rotated during planned invalidation (`docs/identity-migration.md:13-15`). Migration
  must not log or report secret material — all reports carry `secretValues: false`.
- Bootstrap is CLI-only (`ima bootstrap-admin`), no network equivalent, refuses when a super admin exists
  (`docs/identity-migration.md:17-20`; `cli.py:1265-1329`).
- "Do not silently upgrade Argon2/TOTP behavior during a data migration" — pin versions during cutover
  (identity-bridge.md version caveat, line 75).

## 2. Authorization equivalence constraints (workspace-authorization-core)

Spec: `.trellis/spec/backend/workspace-authorization-contracts.md`.

- Bridge result semantics: `source=target|legacy|denied`; legacy read fallback only when no target record;
  malformed/partial/timeout ⇒ fail closed; **legacy ACL mutation is forbidden** (`:58-62`).
- Migration persists per-record failed/complete checkpoints, retries failures, verify fails safely, apply
  resumes (`:62,80-81,103-104`). Tests required: malformed/cyclic/cross-workspace fixtures.
- Legacy role map is fixed: owner/admin→workspace_admin, member→editor, guest→viewer
  (`backend/src/ima/domain/authorization.py` `legacy_role`; unit-pinned
  `backend/tests/unit/test_workspace_authorization.py:33-39`).
- Legacy ACL JSON grammar accepted by the strict parser (`cli.py:1845-1905`): `conf.acl = {inherit: false,
  aces: [{principalType: role|user, principalId, actions[]}]}`; action expansion and dependency rules are
  normative (`ask⇒view_content`, `download⇒view_metadata+view_content`).
- The legacy SQL materialization (`entityPermission` + `kb_*` functions,
  `drizzle/20260824004617_entity_permissions/migration.sql`) is the comparison oracle for ACL equivalence
  reports but must not drive target decisions (search-ask evidence:81-84: "for the legacy entity tree/Zero
  bridge, not a substitute for authorization over target data").

## 3. Blob / storage layout constraints (object-storage-durable-ingestion)

Research: `archive/2026-08/08-24-object-storage-durable-ingestion/research/current-storage-ingestion-evidence.md`.
Spec: `.trellis/spec/backend/object-storage-ingestion-contracts.md`.

- Legacy S3 keys = opaque `blob.id`; "New Python storage must not reuse a legacy key without an explicit
  coexistence/read policy" (evidence:18). Python target layout is
  `documents/{document_id}/{version}/source` (`infrastructure/storage.py:54-55`).
- Spec §legacy migration (`contracts:37`): "copies only completed metadata mappings with stable fingerprints;
  bounded-streams/verifies the source; performs provider-side copy to an opaque target key; verifies the
  target; checkpoints repeatably; **never deletes or reverse-writes legacy objects**."
- Cleanup must not delete bytes referenced by "rollback-retained legacy source" (`contracts:35`) — legacy
  blob keys are rollback-relevant until the deletion task.
- Changed/missing legacy blob ⇒ review/failed checkpoint, no guessed copy (`contracts:50`).
- Supported parse formats for target ingestion: text, Markdown, JSON, PDF text, DOCX, XLSX only
  (`contracts:31`; evidence:9 — PPTX legacy-only until separately verified).
- Legacy blob GC hazard: hourly `cleanBlobs` deletes `refCount=0` objects (evidence:17).
- Real MinIO/S3 copy verification "in isolated buckets with cleanup" is a required test class
  (`contracts:57`).
- Blob checksums: legacy base64 (see G1 in `cutover-gaps.md`); proof is prefix-bounded
  (`src-shared/utils/functions.ts:48-60`), not a full digest.

## 4. Knowledge tree constraints (knowledge-tree-vue-api)

Research: `archive/2026-08/08-24-knowledge-tree-vue-api/research/{backend-codegraph-evidence,frontend-validation-evidence,retained-legacy-symbols}.md`.

- No legacy tag table (tags = `entity.conf.tags`), no legacy version table (`pagePatch` only)
  (backend-codegraph-evidence:55-56) — migration creates versions/tags synthetically (uuid5 ids).
- Migration `20260825_0003` additive/idempotent; downgrade refuses to destroy populated target rows
  (frontend-validation-evidence:36).
- Retained-legacy-symbols table names deletion gates: `kb/ops.ts`, `kb.ts`, `kb/ingest.ts`, `mutators.ts`,
  `queries.ts`, `entityPermission`/`kb_acl_*` stay until every consumer cut over **and rollback reads no
  longer needed**; ACL equivalence and denial tests must pass before schema cleanup
  (`retained-legacy-symbols.md:9-17`).

## 5. MCP/OAuth constraints (oauth-service-principals-mcp)

Research: `archive/2026-08/08-24-oauth-service-principals-mcp/research/current-oauth-mcp-evidence.md`.

- "Do not make the legacy `connector` table the OAuth authority" — bounded coexistence input only (evidence:11).
- Python OAuth implementation must never mutate `public.connector` — enforced by regex contract test
  (`backend/tests/contract/test_coexistence.py:57-69`).
- Legacy connector schema (`drizzle/20260821000000_connector/migration.sql`): SHA-256 `keyHash` +
  `keyPrefix`, mode read/readwrite, optional folder root/expiry/revocation — raw keys are irrecoverable;
  cutover must never attempt key reconstruction (runbook: "Never derive or reconstruct a legacy key",
  `docs/oauth-mcp-coexistence-runbook.md` Pre-Sunset step 2; evidence:30-32).
- Workspace archival/deletion explicitly refuses while legacy `public.member`/`public.entity` dependencies
  exist (evidence:28) — legacy tables are live dependencies until deletion task.

## 6. Search/Ask constraints (search-conversations-grounded-ask)

Research: `archive/2026-08/08-24-search-conversations-grounded-ask/research/current-search-ask-evidence.md`.

- Target retrieval is Python-owned; legacy retrieval retained only for compatibility tests
  (`backend/tests/contract/test_search_coexistence.py:4-13` pins `src-server/kb/retrieve.ts` +
  `src/views/ChatView.vue` existence and that Python search source contains no "legacy" fallback).
- Chunk determinism: `deterministic_chunks()` `(ordinal, text, sha256)` — re-ingestion will produce stable
  chunk identities (`evidence:31-36`).
- FTS: PostgreSQL `zhparser`/mixed config must exist in the target image (foundation migration creates it;
  evidence:54).

## 7. Model governance constraints (central-model-governance)

Research: `archive/2026-08/08-24-central-model-governance/research/model-governance-evidence.md:40-57`.

- Legacy provider/model rows are "read-only migration/rollback inputs only"; retained legacy rows must have
  a named migration/rollback consumer and are deleted by the final cleanup child after the rollback window.
- Secrets: envelope encryption with versioned key ring (`IMA_MODEL_KEY_RING`,
  `backend/src/ima/infrastructure/model_gateway/secrets.py`), rotation command `rotate-model-secrets`
  (`cli.py:301`); legacy plaintext `provider.settings.apiKey` must be re-encrypted at import and never
  appear in reports/audit (implemented in `cli.py:519-560`).

## 8. Foundation constraints (python-foundation-contracts)

- Problem Details errors, correlation ids, camelCase DTOs, cursor pagination, deterministic OpenAPI export —
  any new cutover API surface (e.g., freeze status, migration status endpoint) must follow
  `.trellis/spec/backend/python-foundation-contracts.md`.
- Alembic forward-only; explicit data-migration commands separate from schema migrations (parent design §5.1).

## 9. Cross-cutting operational standards

- Evidence hygiene: deterministic JSON artifacts, image digests + config checksums + snapshot ids, no secret
  values (runbook + drill precedent; see `coexistence-rollback-precedents.md`).
- Contract tests pin coexistence invariants — cutover changes to Caddyfile/compose/docs must update these
  tests deliberately: `test_coexistence.py`, `test_knowledge_coexistence.py`, `test_search_coexistence.py`,
  `test_mcp_transport.py`.
- Deletion is a later task: `08-24-legacy-deletion-release` owns removal of src-server/Zero/commercial
  residue; this cutover task must keep rollback artifacts alive.

## Caveats

- Specs under `.trellis/spec/frontend/` were not reviewed in depth; frontend cutover evidence requirements
  (no Zero traffic) should reuse Playwright/contract patterns from the archived frontend research.
