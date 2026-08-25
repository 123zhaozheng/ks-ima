# Retained Legacy Symbols And Deletion Gates

This manifest is the cutover boundary for the knowledge-tree migration. It
does not claim that Zero is gone: chat, administration, connectors, and
unmigrated compatibility paths still use parts of the legacy stack.

| Symbol or file | Current caller / evidence | Later owner | Deletion gate |
| --- | --- | --- | --- |
| `src-server/kb/ops.ts` | `src-server/kb.ts` and `src-server/mcp.ts` import its folder, note, file, tag, search, and upload operations. | Python knowledge API for folders, notes, tags, and lifecycle; storage and search children for their operations. | Split by ownership, then remove only after Bun browser routes, MCP tools, storage, ingestion, and search consumers have each cut over and rollback reads are no longer needed. |
| `src-server/kb.ts` | Bun `/api/kb/*` routes expose tree, note, file, upload, search, Ask, and lifecycle compatibility. | Python knowledge routes, durable storage/ingestion, and search/Ask services. | Route-by-route parity and explicit rollback switch; no Python failure may invoke these mutators. |
| `src-server/mcp.ts` | API-key MCP tools call every `kb/ops` operation, including notes, files, tags, move, delete, upload, search, and Ask. | Later Python MCP/service-principal child. | Migrate and contract-test every tool, including authorization and storage behavior, before removing this adapter. |
| `src-server/kb/ingest.ts` | `src-server/kb/ops.ts` enqueues parsing; ingest reads S3 and writes legacy parse/chunk state. | Durable object-storage and ingestion child. | Durable jobs, restart/retry/cancel, immutable source versions, and chunk ownership are live and verified. |
| `src-server/kb/retrieve.ts` | `src-server/kb/ops.ts` performs ACL-filtered FTS/vector retrieval and reranking. | Search/RAG child. | ACL-first retrieval, citations, reranking, and Ask parity are verified before deleting the compatibility reader. |
| `src-server/s3.ts` | Bun server upload/download helpers; browser upload uses `src/utils/knowledge-upload.ts`. | Object-storage child. | Ticketed upload, download, preview, checksum/blob verification, and cleanup own the operation; storage capability no longer reports pending. |
| `src-shared/mutators.ts` | Legacy Vue and Bun callers still create/update generic entities, pages, items, move, trash, restore, and delete; `EntityList.vue` remains mixed. | Python knowledge API for migrated knowledge; unrelated Zero domains retain only their own mutators. | Every knowledge browser caller uses generated Python APIs; mixed components are split; no migrated route has a Zero writer or dual-write fallback. |
| `src-shared/queries.ts` | Zero-backed tree, full item, page, recent, and trash readers remain in legacy stores/components. | Vue Query composables and generated Python client. | All knowledge callers are migrated and read-only rollback snapshots are retired; unrelated chat/admin queries still compile. |
| `entityPermission` / `kb_acl_*` | Legacy permission relations, materialization functions, and `src-shared/utils/acl.ts` still serve Bun compatibility/search consumers. | Python workspace authorization and later Bun/Python child cutovers. | No Zero knowledge reader, Bun KB/search reader, or bridge fallback evaluates these rows; ACL equivalence and denial tests pass before schema cleanup. |
| `pagePatch` | `src-server/schema/schema.ts` and `src-server/schema/relations.ts` expose the append-only legacy patch log; migration accepts only complete snapshots. | Python `document_versions`; unsupported histories stay checkpointed for review. | Every migrated page has verified content/version mapping or an explicit review record; no runtime note writer reads or appends patches. |
| `entity.conf.tags` | `src-server/kb/ops.ts`, `src-shared/queries.ts`, and legacy Vue entity-conf consumers read/write JSON tags. | Python workspace-scoped `tags` and `document_tags`. | Tag normalization, ACL-filtered counts, assignment parity, and malformed-value reports pass; no migrated UI writes `conf.tags`. |
| Storage consumers (`src-server/s3.ts`, `src/utils/knowledge-upload.ts`, blob rows) | Browser upload and Bun/MCP file operations still depend on S3/blob metadata. | Object-storage/durable-ingestion child. | Capability state changes from `STORAGE_MIGRATION_PENDING` only when the child owns bytes and dependencies; upload tests prove no duplicate/fake success. |
| Ingestion consumers (`src-server/kb/ingest.ts`, `parse-file.ts`, chunk/embedding rows) | Legacy parse queue and reindex paths consume item/blob state. | Durable ingestion child. | Durable parser lifecycle and migration of parse/chunk ownership complete; legacy `parseStatus` is no longer authoritative. |
| Search consumers (`src-server/kb/retrieve.ts`, `embed.ts`, `rerank.ts`, Ask path) | Bun KB search/Ask and model-governance bridge call legacy retrieval/model paths. | Search/RAG child plus model governance gateway. | ACL-first search, stable citations, and grounded Ask use target document/version IDs; compatibility fallback is removed route-by-route. |
| MCP consumers (`src-server/mcp.ts`, connector configuration) | API-key agents expose the legacy KB operation surface. | Python MCP/service-principal child. | Tool schemas, workspace authorization, audit, and explicit storage/search ownership are migrated and contract-tested. |
| Zero runtime (`src-server/zero/*`, `src/composables/zero/*`, `src/utils/zero-session.ts`) | Unrelated chat, account, connector, and admin flows still import Zero; `src/stores/workspace.ts` also retains non-knowledge state. | Per-domain owners after all product slices migrate. | Delete only after a repository-wide caller audit proves no unrelated domain depends on Zero; this knowledge child must not remove it wholesale. |

## Immediate knowledge cutover proof

- `src/api/knowledge-client.ts` is the sole Vue API adapter for migrated
  knowledge operations and uses `imaClient` for every request.
- `src/composables/use-knowledge.ts` owns Vue Query keys and calls that
  adapter; it does not import Zero or the legacy upload helper.
- `src/layouts/TrashLayout.vue` renders `KnowledgeTrashList.vue`. The old
  `TrashList.vue` has no live caller and is deleted by this child.
- `src/components/EntityList.vue` remains intentionally mixed until its
  remaining callers and upload workflow are split; it is not evidence that a
  migrated API silently falls back to a legacy writer.
