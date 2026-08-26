# Current Search and Grounded Ask Evidence

## Scope and Method

Repository inspected after the knowledge-tree and durable-ingestion migrations. This
is a code-backed planning record, not an implementation design or compatibility
promise. Source locations are repository-relative and line numbers refer to the
current checkout.

## 1. Python Knowledge, Chunks, and Ingestion

### Persisted source and version identity

- `backend/migrations/versions/20260825_0005_knowledge_tree.py:19` creates
  `ima.documents` with immutable UUID identity, workspace/folder ownership,
  lifecycle, mutable document `version`, and `current_version`.
- `backend/migrations/versions/20260825_0005_knowledge_tree.py:44` creates
  `ima.document_versions` keyed by `(document_id, version)`; its trigger rejects
  content/metadata/digest rewrites (`:53-65`). The current `KnowledgeService`
  writes note versions on create/update and reads them by exact document/version
  (`backend/src/ima/application/knowledge.py:255-280, 320-340, 410-449`).
- File versions are separately immutable. `ima.document_file_versions` is keyed
  by `(document_id, version)` and the verified-file trigger rejects object and
  source metadata rewrites (`backend/migrations/versions/20260825_0006_storage_ingestion.py:16-59`).

### Extraction, chunks, and vectors

- `Parser` accepts bounded TXT/Markdown/JSON/PDF/DOCX/XLSX, normalizes text,
  hashes it, and rejects empty/oversized/malformed/encrypted input
  (`backend/src/ima/application/ingestion.py:20-151`).
- `deterministic_chunks()` produces `(ordinal, text, sha256 digest)` with newline
  preference, overlap, an upper bound, and reproducible ordinals
  (`backend/src/ima/application/ingestion.py:154-173`).
- `ima.document_derived_text` is keyed by `(document_id, version, generation)`;
  `ima.document_chunks` is keyed by `(document_id, version, generation, ordinal)`.
  Each chunk retains `text_content`, `content_digest`, `embedding_status`,
  `model_id`, `model_version`, `embedding_dimension`, and `embedding vector`
  (`backend/migrations/versions/20260825_0006_storage_ingestion.py:27-41`).
- Parse writes derived text only after successful extraction; chunk inserts are
  idempotent; embed reads the exact chunk generation, rejects empty/non-finite or
  dimension-inconsistent vectors, and writes `embedding_status='ready'` only for
  each successful row (`backend/src/ima/infrastructure/tasks/ingestion.py:103-171,
  180-245, 250-322`). `documents.file_state` changes to `ready` after embedding.

### Gaps relevant to retrieval

- The target migration declares `embedding vector` but does **not** add a
  dimension-specific pgvector ANN index, a FTS `tsvector` generated column, or
  a GIN FTS index for `ima.document_chunks`. Retrieval must add these after an
  embedding dimension/index strategy is fixed; an untyped `vector` column cannot
  support a conventional dimension-specific HNSW/IVFFlat opclass across changing
  models without an explicit isolation/reindex plan.
- PostgreSQL capability is available at image level: `Dockerfile.postgres:3-9`
  installs pgvector. Legacy Drizzle also demonstrates PostgreSQL FTS using
  `to_tsvector('mixed', left(..., 250000))` in
  `drizzle/20260428130734_cloudy_ultimates/migration.sql:1-6`.
- Current Python knowledge routes expose file ingestion, documents, versions,
  tags, listings, and trash only; there is no target `/search`, `/ask`,
  citation, conversation, or chat route (`backend/src/ima/api/v1/knowledge.py:50-425`,
  `backend/src/ima/api/v1/knowledge_contracts.py:1-180`).

## 2. Target ACL and Retrieval Boundary

`WorkspaceService` is the Python mutation authority and authorizes actual folders,
not merely a workspace root. `_require_member()` verifies active account/workspace;
`_require_folder_action()` calls `folder_decision()` and maps a denial to a hidden
404 with an audit event (`backend/src/ima/application/authorization.py:93-180`).
`KnowledgeService` uses that path for content actions (`backend/src/ima/application/knowledge.py:80-103`).
Collection reads first compute authorized folder IDs through
`accessible_folder_ids()` and filter SQL with `folder_id=ANY(:ids)`
(`backend/src/ima/application/knowledge.py:132-184`).

The target ACL contract requires same-subject relational division: `ask` requires
`view_content`, and grants cannot be assembled from different subjects
(`.trellis/spec/backend/workspace-authorization-contracts.md:39-49, 111-132`).
Therefore retrieval must apply a target ACL predicate/filter before FTS ranking,
vector scoring, rerank requests, context construction, citation return, and any
model call. A final recheck before emitting citations is warranted because ACLs
may change during a streamed answer.

The legacy public schema has an `entityPermission` materialization migration with
`canView` and `canAsk` plus indexes, and SQL enforces `ask => view`
(`drizzle/20260824004617_entity_permissions/migration.sql:1-21, 52-65`). This is
for the legacy entity tree/Zero bridge, not a substitute for authorization over
`ima.folders`/`ima.documents`.

## 3. Governed Chat, Embeddings, Rerank, and Streams

- `GroundedAskConfig` already supplies typed, bounded settings: required chat
  model and optional embedding/rerank models; `hybrid|keyword|vector`, `topK`,
  vector weight, score threshold, context character limit, and generation timeout
  (`backend/src/ima/domain/model_governance.py:90-115`). Optional model IDs become
  required capabilities at profile validation (`:220-232`).
- `ModelGovernanceService.managed_embeddings()` and `.managed_rerank()` resolve
  exact assigned capabilities, fail `NO_ASSIGNMENT` or `UNAVAILABLE` safely, and
  execute only through the guarded gateway client
  (`backend/src/ima/application/model_governance.py:2090-2130`). Rerank return
  values are index/score pairs and existing tests cover finite-score rejection.
- Target chat streaming is available through `managed_chat_stream()`
  (`backend/src/ima/application/model_governance.py:2054-2088`). The private
  bridge returns FastAPI `StreamingResponse` as `text/event-stream`, disables
  proxy buffering, and is constant-time token gated
  (`backend/src/ima/api/v1/model_governance.py:519-594`).
- Model governance is deliberately fail-closed: a target assignment with broken
  profile/model/gateway state is authoritative `UNAVAILABLE`, never an apparent
  no-assignment that could invoke legacy execution
  (`backend/src/ima/application/model_governance.py:1815-1821`; contract
  `.trellis/spec/backend/model-governance-contracts.md:55-65`).

## 4. Legacy Bun Retrieval, Ask, Chat, and Citations

The legacy retrieval implementation is `src-server/kb/retrieve.ts`.

- It creates FTS candidates with `websearch_to_tsquery('mixed', q)` and
  `ts_rank(chunk.search, query)` (`:52-70`), then embeds the query and calculates
  cosine similarity in application memory over up to 8,000 rows (`:72-100`).
- It fuses keyword/vector scores, degrades vector-only mode to keyword if there
  are no vectors (`:27-48, 150-164`), scopes/filter ACL and folder/tag before
  reranking, caps rerank candidates to 20, then rechecks `view` before returning
  citations (`:165-198`). This establishes the intended ordering but is not a
  scalable target query shape because target chunks live in a separate schema.
- Legacy `kbAsk()` obtains `ask` citations first; it returns a fixed knowledge-gap
  answer without calling a model when none exist. With citations, it calls the
  governed chat bridge; when no answer is produced it returns concatenated source
  quotes, not an invented answer (`src-server/kb/ops.ts:54-79`).
- Bun MCP routes call `kbSearch`/`kbAsk` and restrict a supplied workspace ID to
  the connector's workspace (`src-server/mcp.ts:31-58`). Tool declarations are in
  `src-server/mcp-dispatch.ts:33-58`, using streamable HTTP transport (`:92-103`).
- The old Vue workspace plugin invokes `client.api.kb.search` as a chat tool and
  asks the model to cite result quotes (`src/utils/builtin-plugins/workspace.ts:7-55`).
  `KbCitations.vue` parses those stored tool results and identifies citations only
  by legacy `entityId` (`src/components/KbCitations.vue:1-69`).

## 5. Current Vue Ask/Chat and Transport

- Clicking Ask uses `useAskKnowledge()`, which requires a selected workspace and
  live Zero connection, creates a legacy `chat` entity, and navigates to
  `/chat/{id}` (`src/composables/ask-knowledge.ts:12-55`,
  `src/utils/create-entity.ts:12-26`).
- `createChat` writes a legacy entity with `personalAcl(currentUser)`, a `chat`
  row, and an initial user message (`src-shared/mutators.ts:296-330`);
  `personalAcl` grants all actions solely to that user
  (`src-shared/utils/acl.ts:48-58`). Thus private ownership is an ACL convention,
  not a Python conversation lifecycle.
- `ChatView` persists message pairs and branches via Zero, sends arbitrary chat
  history and optional browser-side tool definitions, streams completion results,
  supports abort/regenerate/edit/branch delete, and optionally generates a title
  (`src/views/ChatView.vue:200-312, 349-404`).
- `stream-message.ts` posts to Bun `/api/v1/chat/completions`, parses OpenAI-like
  SSE `data:` lines, progressively mutates legacy assistant messages, cancels the
  reader on abort, and allows up to five tool-loop turns
  (`src/services/stream-message.ts:110-199`). Bun forwards that response from
  the private Python model-governance bridge (`src-server/ai.ts:16-63`).

This is a usable general-chat transport, but it is not a grounded-Ask transport:
it has no server-issued citation event, no server-owned conversation identity,
and lets browser-selected tools obtain retrieval material outside the proposed
target Ask service.

## 6. Coexistence, Ownership, and Deletion Blockers

1. Python knowledge data is `ima.documents`/`ima.document_versions`/storage
   relations, while legacy search and conversations use public `entity`, `chunk`,
   `chat`, `message`, and Zero mutators. No target conversation tables exist.
   Search/Ask cannot transparently query both stores without defining dual-read,
   source provenance, ACL equivalence, and deletion semantics.
2. The target schema includes `ima.legacy_knowledge_migration` checkpoints
   (`backend/migrations/versions/20260825_0005_knowledge_tree.py:84-92`), but
   the migration runner is not a retrieval bridge. The target authorization
   contract permits legacy read fallback only for genuinely unmigrated objects;
   partial/timeout/malformed target data must deny
   (`.trellis/spec/backend/workspace-authorization-contracts.md:55-64`).
3. Python document/file/version/chunk relations use `ON DELETE RESTRICT`
   (`20260825_0005_knowledge_tree.py:44-52`,
   `20260825_0006_storage_ingestion.py:16-48`). Target document deletion must
   explicitly coordinate active/queued ingestion jobs, chunks, derived text,
   file versions, object cleanup, and later citations/conversation retention.
   It cannot be a casual cascade.
4. Legacy chat deletion currently follows legacy entity cascade relations:
   deleting an entity cascades its chat/message/tool-call rows
   (`src-server/schema/schema.ts:60-149`). It is unrelated to target document
   lifecycle. Existing private chats remain legacy-owned until a migration plan
   gives them immutable target records or explicitly retires them.
5. Bun currently has rollback-only legacy model fallback when resolver reports
   exact `NO_ASSIGNMENT` (`src-server/kb/model-governance.ts:39-80`). The MVP
   grounded Ask endpoint must not use that public/legacy fallback: no retrieval
   means no model call; unavailable target chat/rerank/embedding yields a stable
   target error or source-only result as specified below, never a broader corpus,
   browser gateway, or public endpoint.

## 7. Stable Citation Contract

A citation must identify the retrieved immutable source, not only a display path,
legacy entity, score, or current document version. Recommended immutable identity:

```text
citationId: opaque stable UUID (optional response handle)
documentId: UUID
documentVersion: integer
fileGeneration: integer | null
chunkOrdinal: integer
chunkDigest: sha256
```

Return display metadata separately: current-safe title/path, a bounded quote,
and optional rank/score. Persist the complete identity on the assistant answer
before/at stream completion. Citation resolution must authorize `view_content`
every time and return 404 after source deletion/revocation; it must not silently
redirect to a newer version or another chunk. For note content,
`documentVersion` maps directly to `document_versions`; for files,
`documentVersion + fileGeneration + ordinal` maps to the derived/chunk tuple.
`chunkDigest` detects accidental ordinal/content mismatch. This maps exactly onto
the target schema keys described in section 1.

## 8. Recommended MVP

1. Add a Python-owned retrieval service and public typed routes for target
   documents only. Authenticate the current user, require active membership,
   derive allowed folder/document scope via `WorkspaceService`, and put the ACL
   join/filter inside candidate SQL. Never send unauthorized chunk text to an
   embedding or rerank model.
2. Start with ACL-first hybrid retrieval: PostgreSQL FTS over chunk text plus
   pgvector cosine ranking only for ready chunks matching the configured model
   dimension/version. Bound each candidate pool, normalize/fuse scores, dedupe
   by stable chunk identity, apply threshold/top-K, then recheck access. Add
   partial FTS and pgvector indexes only after determining the active embedding
   dimension/index lifecycle; `EXPLAIN` is a release gate.
3. Query embedding only when the grounded-Ask profile has a valid embedding
   assignment and the selected mode needs it. Keyword remains usable where the
   profile explicitly permits it. Optional rerank runs only after ACL filtering,
   on a bounded candidate list; an unavailable/invalid reranker should preserve
   the pre-rerank order with a safe degradation marker, rather than retrying
   against public/legacy infrastructure.
4. Introduce Python-owned private conversations and messages. Every row must
   include `workspace_id`, `owner_user_id`, creation/update timestamps,
   lifecycle/version, and foreign-keyed answer/citation records. All list/get/
   append/delete operations constrain `owner_user_id=current user`; workspace
   membership alone never exposes another user's conversation. Do not migrate or
   mutate legacy chats in the MVP.
5. Offer a dedicated grounded Ask SSE endpoint. It performs retrieval first and
   emits a structured `citations` event before token `delta` events, followed by
   terminal `completed` or stable `error`. Persist user question plus citation
   set before calling chat; persist assistant text/status on completion or
   cancellation. Use existing guarded Python `managed_chat_stream()` only after
   nonempty, authorized target retrieval.
6. Empty retrieval is a successful, non-streaming knowledge-gap response with
   an empty citation list and no chat call. Target chat failure after retrieval
   may return citations plus bounded source excerpts/status, or a safe 503; it
   must not generate unsupported facts. There is no public, legacy-corpus, or
   unauthenticated fallback.
7. Migrate Vue Ask to the target conversation/search APIs and SSE event schema.
   Keep existing generic legacy Chat separate during coexistence. Replace the
   `KbCitations` entity-ID parser for grounded answers with typed target citation
   records and a target document/version viewer route.

## 9. Safe Audit, Logging, and Errors

- Follow the backend JSON logging contract: record operation/status/duration/
  correlation ID and low-cardinality reason codes, but never prompts, answers,
  query text, chunk text, document content, authorization headers, credentials,
  gateway URL, or raw upstream response (`.trellis/spec/backend/logging-guidelines.md:19-59`).
  `RedactingFormatter` recursively masks secret-named fields but is not a license
  to put document content in log metadata (`backend/src/ima/infrastructure/observability/logging.py:12-39`).
- Audit access decisions and mutations with actor/workspace/conversation or
  document opaque IDs, action, result, reason code, correlation ID, and bounded
  counts. Existing `WorkspaceService._audit()` is the established write shape
  (`backend/src/ima/application/authorization.py:52-77`).
- Reuse RFC 9457 problem responses and correlation headers for pre-stream errors
  (`backend/src/ima/api/errors.py:17-85`). Once an SSE response begins, send only
  a bounded stable error event, close the upstream stream on cancellation, and
  leave the persisted answer in an explicit failed/cancelled state. Do not leak
  model/provider/network details.

## 10. Executable Validation Matrix

| Scenario | Verification | Required result |
| --- | --- | --- |
| Migration/schema | `alembic upgrade head`; PostgreSQL inspection plus `EXPLAIN (ANALYZE, BUFFERS)` for FTS/vector candidates | Chunk indexes exist and scoped query uses them; no unbounded vector scan in production path. |
| Ingestion identity | Upload/revise/reingest a file; inspect derived/chunk keys and digests | Distinct immutable `(document,version,generation,ordinal)` citations; no stale generation selected. |
| ACL denial | Two users; revoke view/ask before search, rerank, and during an Ask stream | Hidden 404/pre-stream denial or terminal safe stream result; denied text never reaches reranker/chat/citations. |
| Same-subject dependency | Grant `ask` and `view_content` to different subjects, then grant both to one subject | First is denied; second is permitted. |
| Hybrid modes | Fixture keyword-only, vector-only, and mixed matches; test keyword/vector/hybrid profile settings | Deterministic bounded fusion, threshold and top-K; vector absence only falls back to keyword when profile mode permits it. |
| Rerank | Fake valid, timeout, malformed, NaN/Inf rerank response | ACL-filtered bounded documents only; valid reorder; degraded pre-rerank ordering or stable safe error, never public fallback. |
| Empty retrieval | Ask an authorized corpus with zero accepted hits; assert gateway fake has no chat calls | Knowledge-gap response, `citations=[]`, no SSE chat/model invocation. |
| Grounded SSE | Fake managed chat emits multiple SSE chunks then cancellation/error | `citations` precedes `delta`; progressive rendering; `completed` persists final answer; cancellation closes upstream and persists lifecycle. |
| Citation stability | Cite version N, revise/restore/delete/revoke source, then resolve citation | Exact N/chunk identity only; newer content is never substituted; deletion/revocation returns hidden not-found. |
| Private conversations | User A/B same workspace enumerate/read/update/delete each other's IDs | Owner-only rows and operations; B receives hidden 404; workspace admin gains no implicit conversation read. |
| Error/audit hygiene | Capture logs/audit for denied, empty, upstream failure, and malformed event | Correlation/reason/counts present; no query, source text, prompt/answer, secret, URL, or raw upstream body. |
| Coexistence | Run legacy Chat and target Ask side by side; disable target model assignment | Legacy generic chat behavior remains isolated; target Ask never queries legacy chunks/chats or invokes legacy/public fallback. |

## Planning Conclusion

The target foundation supports durable source/version/chunk identity, target folder
authorization, guarded model execution, and Python SSE forwarding. It does not yet
supply target retrieval indexes/queries, conversations, citations, or Vue APIs.
The MVP should therefore be a narrow Python-owned, ACL-first target-document
workflow: hybrid FTS/pgvector retrieval, optional post-ACL rerank, owner-private
conversations, SSE grounded answers with immutable version/chunk citations, and a
fixed knowledge-gap result without any public or legacy fallback.
