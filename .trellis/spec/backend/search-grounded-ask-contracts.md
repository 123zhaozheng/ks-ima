# Search, Private Conversation, And Grounded Ask Contracts

## Scope / Trigger

Apply this contract to target chunk FTS/pgvector retrieval, ANN index lifecycle, rerank, private conversations/messages, grounded Ask SSE, citations, citation/source deletion dependencies, and any route or migration under the target search/Ask slice.

## Signatures

```text
GET  /api/v1/workspaces/{workspaceId}/search
POST /api/v1/workspaces/{workspaceId}/search-indexes/build
GET  /api/v1/workspaces/{workspaceId}/conversations
GET/PATCH/DELETE /api/v1/workspaces/{workspaceId}/conversations/{conversationId}
POST /api/v1/workspaces/{workspaceId}/ask
POST /api/v1/workspaces/{workspaceId}/conversations/{conversationId}/retry
GET  /api/v1/workspaces/{workspaceId}/messages/{messageId}/citations/{ordinal}

ima.chunk_search_indexes
ima.conversations
ima.conversation_messages
ima.message_citations
```

## Contracts

- Retrieval corpus is target `ima.document_chunks` only. Legacy chunks/chats and public/external search are never fallback candidates.
- Every chunk carries `workspace_id` and a restrictive composite workspace/document FK. Candidate SQL filters active workspace/document/folder lifecycle and canonical same-subject `view_content` or `ask` authorization before ranking, rerank, prompt construction, citation persistence, or serialization.
- FTS uses schema-qualified `ima.mixed`, created with the required `zhparser` parser and explicit Chinese/simple plus English stem mappings. A missing parser fails migration closed.
- Vector indexes are physical HNSW indexes isolated by workspace, exact embedding model ID/version, and dimension. Dynamic names/predicates are built only from validated database values; workspace literals are escaped; advisory locks/building rows serialize competing builds.
- Vector/hybrid search requires an exact active index row and matching ready chunk model/version/dimension. Missing index returns `REINDEX_REQUIRED`; application-memory corpus scans and dimension mixing are forbidden.
- Hybrid fusion is bounded, normalized, deterministic, and stably tied by immutable chunk identity. Optional rerank receives only ACL-filtered bounded quotes, cannot introduce unseen chunks, validates unique in-range indices and finite scores, and degrades to fused order without public/legacy fallback.
- Conversations/messages are workspace-scoped and owner-private. Every list/get/update/archive/delete/retry query includes `owner_user_id=:actor`; workspace/platform administrators gain no implicit read. Conversation owner must be an active workspace member through a restrictive composite FK.
- Grounded Ask persists question/assistant state, performs retrieval first, emits persisted citations before any delta, streams only through governed target chat, closes upstream on cancellation, and persists `completed|knowledge_gap|failed|cancelled` terminal state.
- Empty retrieval returns the fixed knowledge-gap result and makes no chat call. Target model/rerank/index failure never broadens the corpus or invokes legacy/public infrastructure.
- Citation identity is exact `(document, version, generation, ordinal, digest)`. File versions are represented in immutable `document_versions`; citations restrict both version and exact chunk deletion. Completed message citations cannot be updated.
- Citation resolution checks conversation owner and current source authorization, loads the exact chunk, and never substitutes a newer version. Revoked/deleted sources return hidden 404.
- Logs/audit/errors contain safe IDs, modes, counts, durations, and stable reason codes only; never query, question, prompt, answer, quote, chunk text, hidden title/path, gateway URL, secret, or raw upstream body.

## Validation Matrix

| Condition | Required result |
|---|---|
| Ask/view grants split across subjects | Denied; no chunk/model/citation exposure |
| Revoke/move/trash during retrieval/stream | Recheck hides source and cancels/terminates safely |
| Missing/mismatched ANN model/version/dimension | `REINDEX_REQUIRED`; no memory/legacy fallback |
| Two workspaces share embedding model | Distinct workspace-predicate physical indexes and lifecycle rows |
| Invalid/timeout rerank | Deterministic pre-rerank order plus safe degradation |
| Empty accepted hits | `knowledge_gap`, empty citations, zero chat calls |
| User/admin accesses another owner's conversation | Hidden 404 |
| Citation source revised | Exact historical version/chunk resolves; current version not substituted |
| Citation/source deletion dependency | Delete refused until citation/conversation cleanup policy permits |
| Stream cancellation/upstream error | Upstream closed; persisted cancelled/failed state; bounded SSE event |

## Tests Required

1. Ruff format/check, strict mypy, full pytest, deterministic OpenAPI generation.
2. Fresh isolated PostgreSQL image with `vector` and `zhparser`; exact `IMA_REQUIRE_POSTGRES=1` test count passes with zero skips, migrations reach current head, catalog constraints/triggers/config/indexes are asserted.
3. Real `EXPLAIN (ANALYZE, BUFFERS)` fixtures prove GIN/HNSW candidate plans are bounded and workspace/model/dimension predicates match the index.
4. Fake governed embedding/rerank/chat tests cover finite/dimension/index validation, no-hit no-chat, progressive SSE, cancellation, malformed events, and no fallback.
5. Owner/privacy, ACL revoke races, conversation optimistic conflicts, citation stability/deletion, and concurrent index build tests run on PostgreSQL.
6. OpenAPI/Caddy/coexistence tests prove exact Python routes, private model bridges remain hidden, and legacy generic Chat/MCP consumers remain isolated until their owner tasks.

## Wrong vs Correct

### Wrong

```text
load 8,000 vectors into Python -> filter ACL -> rerank -> browser tool-loop chat
```

### Correct

```text
workspace + ACL-filtered SQL candidates
-> schema-qualified GIN and workspace/model/dimension HNSW
-> bounded deterministic fusion -> optional governed rerank
-> persisted exact citations -> governed SSE chat
```
