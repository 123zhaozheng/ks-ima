# Research: Legacy Data Inventory and Migration Mapping

- **Query**: Where does legacy data live and what must be migrated into `ima.*` (source -> target, transformation, volume)?
- **Scope**: internal
- **Date**: 2026-08-28

## 1. Where legacy data lives

- **PostgreSQL database `app`, schema `public`** — all product and auth tables. Legacy DDL lives in
  `drizzle/*/migration.sql`; the live Drizzle schema projection is `src-server/schema/schema.ts` (473 lines)
  and `src-server/schema/legacy-user.ts` (17 lines, now a read-only projection maintained by Python identity).
- **Second database `zero`** — Rocicorp Zero CVR/change database (`docker-compose.example.yml:152-167`,
  init at `:179-187`). Disposable replication state, not migration input.
- **S3-compatible object storage** — legacy objects are stored **flat, key = 16-char `blob.id`** in the bucket
  configured by `S3_BUCKET` (`src-server/utils/s3.ts:1-17`, upload at `src-server/s3.ts:91-131`).
  The Python side uses `IMA_STORAGE_BUCKET` with layout `documents/{document_id}/{version}/source`
  (`backend/src/ima/infrastructure/storage.py:54-55`).
- **No other durable state**: legacy parse/ingestion state is JSON inside `entity.conf`; cron jobs are
  in-process (`src-server/jobs/index.ts:18-24`).

### Complete legacy table list (public schema)

From `drizzle/*/migration.sql` (CREATE TABLE scan) plus `drizzle/20260821000000_connector`:

```
account, assistant, blob, channel, chat, connector, entity, entityAccess, entityPermission,
globalSettings, item, mcpPlugin, member, mergePatchesRule, message, messageEntity, model,
order, page, pagePatch, plan, planPrice, provider, search, searchRecord, session, shortcut,
toolCall, translation, translationRecord, two_factor, usage, user, userData, verification,
workspace, workspaceInvitation
```

Plus SQL functions/triggers: `kb_acl_granted`, `kb_acl_can`, `kb_nearest_acl_break`,
`kb_rebuild_one_entity_permissions`, `kb_rebuild_workspace_permissions`,
`kb_entity_permission_trigger`, `kb_member_permission_trigger`
(`drizzle/20260824004617_entity_permissions/migration.sql`), blob `refCount` triggers
(`drizzle/20260317054607_create_trigger/migration.sql`), `zhparser`/mixed FTS config
(`drizzle/20260415115542_init_fts`), and generated `tsvector` columns on
`entity/item/chunk/message/page/translationRecord` (`src-server/schema/schema.ts:70-72,103-105,191-193,240-242,258-260,328-330`).

## 2. Source -> target mapping (current implemented state + plan)

Target schema: `ima` (product) + `ima_jobs` (queue), created by Alembic
`backend/migrations/versions/20260824_0001_foundation.py:11-14`; extensions `vector` + `zhparser`.

| Legacy source | Target `ima.*` table(s) | Implemented in | Transformation notes |
|---|---|---|---|
| `user` (+ `account` credential rows, `two_factor`) | `ima.users`, `ima.password_credentials`, `ima.totp_credentials`, `ima.legacy_identity_projection` | `cli.py:1908-2143` (`migrate-legacy-identity`) | IDs preserved. Argon2id PHC imported only if `compatible_argon2id_phc` parses it (`application/legacy_identity.py:13-21`), else `password_reset_required=true` and credential deleted. TOTP imported only if base32/RFC6238-valid, re-encrypted with `IMA_TOTP_ENCRYPTION_KEY` (`cli.py:1998-2009`). Recovery codes reissued (deleted, `cli.py:1995-1997`). `public.session` is **deleted** (sessions never copied, `cli.py:2029-2033`). Inserts empty `public.userData` projection row (`cli.py:2010-2013`). |
| `workspace` | `ima.workspaces` | identity apply (`cli.py:2031-2033`) + authorization apply (`cli.py:1384-1441`) | IDs preserved; plan/payment/quota/storage fields dropped. Owner becomes `workspace_admin` member (`cli.py:1419-1423`). Root folder = workspace id, seeded ACL from `DEFAULT_ROLE_GRANTS` (`cli.py:1395-1418`). |
| `member` | `ima.workspace_members` | `cli.py:1442-1494` | Role map owner/admin→workspace_admin, member→editor, guest→viewer (`domain/authorization.legacy_role`, tests `tests/unit/test_workspace_authorization.py:33-39`). Unknown roles fail checkpointed. |
| `entity` type `dir`/`folder` | `ima.folders`, `ima.folder_closure`, `ima.folder_acls`, `ima.folder_acl_entries` | `cli.py:1495-1676` (`migrate-legacy-authorization`) | Folder IDs preserved. Topological import; cycles/cross-workspace parents/dangling parents fail checkpointed (`cycle_or_missing_parent`, `cross_workspace_parent`). Closure table built incrementally (`cli.py:1600-1611`). Legacy `conf.acl` with `inherit=false` becomes an independent ACL via strict parser `_parse_legacy_acl` (`cli.py:1845-1905`): action expansion map (`view`→view_metadata+view_content, `download`→download+views, `ask`→ask+view_content, `manage`→manage_acl), rejects `ask` without `view_content`, unknown roles/subjects/actions → `malformed_acl*` failures. |
| `entity` type `item`/file + `item` + `blob` | `ima.documents`, `ima.document_versions`, `ima.document_file_versions`, `ima.legacy_knowledge_migration` | `cli.py:648-1165` + storage phase `cli.py:1168-1262` (`migrate-legacy-knowledge`) | Documents get **derived UUIDv5** target id `uuid5(NAMESPACE_URL, "legacy-knowledge:{root}:{source}")` (`cli.py:896-898`) — legacy item IDs are NOT preserved; mapping recorded in checkpoint table. Version 1 metadata snapshot only, no bytes read in metadata phase (`cli.py:947-991`). `file_state='pending'`. Trash detection via workspace `trashId` ancestry + `conf.originalParentId` (`cli.py:784-804,863-869`). |
| `entity` note + `page.text` + `pagePatch` | `ima.documents` (kind=note), `ima.document_versions` | same | Note bodies = snapshot list from patches + final `page.text` (`cli.py:940-946,992-1003`). Only `{"text": "..."}` snapshots importable; JSON-patch histories → `unsupported_patch_history` review (`application/legacy_knowledge.py:82-108`). Digests = sha256 of body (`cli.py:1001`). |
| `entity.conf.tags` | `ima.tags`, `ima.document_tags` | `cli.py:1004-1017` | NFKC + casefold dedupe (`application/legacy_knowledge.py:33-47`); tag ids uuid5 `legacy-tag:{root}:{normalized}`. |
| blob bytes (S3) | same bucket, key `documents/{target_id}/1/source`; `ima.document_file_versions` row `object_state='verified'` | storage phase `cli.py:1168-1262` | `ObjectStorageClient.copy_verified` (`infrastructure/storage.py:125-149`): get source, bounded sha256 re-digest compared to `blob.sha256`, provider-side copy, then HEAD verify of target. Checkpoint kind `storage`, id `{source_id}:storage`. **Checksum format caveat — see section 5.** |
| `provider` | `ima.model_gateways`, `ima.model_gateway_secrets`, `ima.legacy_model_governance_migration` | `cli.py:389-645` (`migrate-legacy-model-governance`) | Only structurally explicit providers (baseURL+apiKey) import, always `enabled=false`; secret re-encrypted into key ring (`cli.py:519-560`). Ambiguous → `review`. |
| `model` | `ima.governed_models` | `cli.py:571-639` | Requires explicit operator mapping file (capability chat/embedding/rerank, embedding dimension) via `--mapping-file` or `IMA_MODEL_GOVERNANCE_MAPPING`; imported models `enabled=false, validated=false` (`cli.py:617-633`). |
| `connector` | **not converted** — inventory/classification only | `cli.py:192-247` (`inventory-legacy-mcp`) + `application/legacy_mcp_inventory.py` | Read-only report of id/mode/folder-root/expiry/revocation; operator decision file maps each id to `reissued`/`revoked`; apply writes only audit telemetry (`cli.py:230-244`), never mutates `public.connector` (pinned by contract test `backend/tests/contract/test_coexistence.py:57-69`). |

## 3. Data with NO Python-side migration (gaps; detail in `cutover-gaps.md`)

- `chat` / `message` / `messageEntity` / `toolCall` — no importer exists. Parent plan step 12.2.6 requires
  importing retained conversations "according to the approved retention rule" (`.trellis/tasks/08-24-python-intranet-ima-migration/implement.md:545-546`) — not yet implemented.
- `chunk` (legacy RAG slices, JSON embeddings) — never copied; target rebuilds via re-parse/re-chunk/re-embed
  (parent plan 12.2.9). Migrated files sit at `file_state='pending'` with no ingestion job enqueued.
- `workspaceInvitation`, `entityAccess`, `search`/`searchRecord`, `shortcut`, `userData.perfs/data`,
  `globalSettings` defaults (profiles), `usage`, commercial tables — dropped by design or review-only.
- Capability profiles (`ima.capability_profiles`) are not auto-created from legacy settings; admin must publish them.

## 4. Checkpoint tables (resumability substrate)

All migration state lives in dedicated `ima` tables (Alembic):

- `ima.legacy_identity_migration`, `ima.legacy_identity_projection` (`migrations/versions/20260824_0002_identity_platform.py`)
- `ima.workspace_authorization_migration` (`20260825_0003_workspace_authorization.py`)
- `ima.legacy_model_governance_migration` (`20260825_0004_model_governance.py`)
- `ima.legacy_knowledge_migration` (`20260825_0005_knowledge_tree.py`)

Common columns: `source_kind`, `source_id`, `source_fingerprint`, `status`
(`running|complete|failed|review`), `attempts`, `last_error`, `mapping jsonb`, `processed_at`, `updated_at`.
Fingerprint = sha256 of canonical source payload (`application/legacy_knowledge.py:27-30`); a changed source
flips the row to `review/source_changed` instead of silently overwriting (`cli.py:854-860`).

## 5. Critical format facts (verification constraints)

- **Legacy blob checksums are base64** (`src-server/s3.ts:41-50` header `z.base64()`,
  `src-server/kb/ops.ts:325` `digest('base64')`), while the Python storage pipeline treats checksums as
  **lowercase hex** (`infrastructure/storage.py:158-170` `bounded_digest` returns hexdigest;
  `_checksum_header` converts hex→base64 only for S3 headers). The current storage phase passes
  `blob.sha256` unchanged into `copy_verified` (`cli.py:1178-1192,1212-1218`), where it is compared to a hex
  digest (`storage.py:134-136`) — legacy base64 values cannot match. **This must be normalized before/at
  cutover or every legacy file will checkpoint as `review/SOURCE_OBJECT_CHANGED`.**
- Legacy `sha256Proof` is a partial-stream proof (prefix + first N bytes,
  `src-shared/utils/functions.ts:48-60`), not reproducible as full-object digest; Python verification must rely
  on full-object re-digest, not the proof.
- Legacy object metadata carries `x-amz-checksum-sha256` as **user metadata**, not a real S3 checksum
  attribute (`src-server/s3.ts:96-100`); HEAD `ChecksumMode=ENABLED` on legacy keys returns no checksum. The
  Python copy step recomputes checksums on the target (`copy_object` with `ChecksumAlgorithm='SHA256'`,
  `storage.py:137-144`), which is what makes target verification possible.
- Legacy blobs are deduplicated by `(sha256[, proof])` with `refCount` (`src-server/s3.ts:70-84`,
  `src-server/kb/ops.ts:326-345`); several items can reference one blob key. The storage phase copies per
  completed item (`cli.py:1177-1182`), so a shared blob is copied once per referencing document — target keys
  are per-document, no dedupe dependency.
- Legacy ids are 16-char varchar (`src-server/schema/schema.ts:11`); Python user/workspace/folder ids are
  preserved verbatim (varchar/text), document target ids are UUIDv5. ID length/type must stay compatible with
  `ima.folders.id`/`ima.workspaces.id` accepting legacy 16-char strings (they do — identity/authorization
  migrations insert legacy ids directly).

## 6. Volume considerations (qualitative — no production DB available in this repo)

- `entity` is the largest structural table (one row per folder/item/chat/model/provider/assistant/page/search/
  shortcut depending on `type`); the knowledge importer filters to `type IN ('folder','item')`
  (`cli.py:668-672`) and authorization to `type='dir'` (`cli.py:1362-1364`).
- Row-by-row psycopg transactions: identity/authorization/knowledge apply loops issue O(1) round trips per
  record with per-record commits (`cli.py:1383-1676` etc.). Fine for intranet scale (thousands–low millions of
  entities); for large estates, batch SQL and cursor pagination would be the scale lever. There is no
  COPY-based bulk path today.
- Blob phase streams every object through the API process for re-digesting
  (`storage.py:125-149` reads body then provider-side copies) — bandwidth/time scales with total blob bytes;
  resumable per-object, safe to rerun.
- `chunk` table can be large (up to 8k chunks scanned in-app historically, parent research) but is not
  migrated — replaced by worker re-ingestion, whose cost is governed by parser/embedding throughput.
- The final delta import under write freeze re-runs the same resumable commands; only rows with changed
  fingerprints are reprocessed, so delta cost is proportional to writes made since the last apply.

## Caveats / Not Found

- No access to a real legacy production database dump; row counts/volumes above are structural, not measured.
- `public.account`/`verification` Better Auth tables are read only for the newest credential row
  (`cli.py:1924-1929`); email verification records and secondary accounts are not migrated (local single
  credential per user is the target model).
- Legacy `two_factor` table name is referenced in CLI SQL (`cli.py:1927`) though the drizzle scan shows a
  truncated `CREATE TABLE "two...` entry; Better Auth two-factor tables (`twoFactor*`) may vary by version —
  verify against the actual database during cutover rehearsal.
