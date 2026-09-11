# Search, Private Conversation, And Grounded Ask Contracts

## Scope / Trigger

Apply this contract to target chunk FTS/pgvector retrieval, ANN index lifecycle (including automatic build after ingestion and reconciliation healing), rerank, private conversations/messages, grounded Ask SSE, citations, citation/source deletion dependencies, and any route or migration under the target search/Ask slice.

## Signatures

```text
GET  /api/v1/knowledge-bases/{kbId}/search
POST /api/v1/knowledge-bases/{kbId}/search-indexes/build
GET  /api/v1/conversations
GET/PATCH/DELETE /api/v1/knowledge-bases/{kbId}/conversations/{conversationId}
POST /api/v1/knowledge-bases/{kbId}/conversations/{conversationId}/retry
POST /api/v1/knowledge-bases/{kbId}/ask
GET  /api/v1/knowledge-bases/{kbId}/messages/{messageId}/citations/{ordinal}

ima.chunk_search_indexes
ima.conversations
ima.conversation_messages
ima.message_citations
```

## Contracts

- Retrieval corpus is target `ima.document_chunks` only. Legacy chunks/chats and public/external search are never fallback candidates.
- Every chunk carries `kb_id` and a restrictive composite knowledge-base/document FK. Candidate SQL filters active knowledge-base/document/folder lifecycle and the caller's membership role (`view_content` for search, `ask` for grounded Ask) before ranking, rerank, prompt construction, citation persistence, or serialization.
- FTS uses schema-qualified `ima.mixed`, created with the required `zhparser` parser and explicit Chinese/simple plus English stem mappings. A missing parser fails migration closed.
- Vector indexes are physical HNSW indexes isolated by knowledge base, exact embedding model ID/version, and dimension. Dynamic names/predicates are built only from validated database values; knowledge-base literals are escaped; advisory locks/building rows serialize competing builds.
- Index maintenance is automatic: the ingestion embed stage enqueues a build for its knowledge base, and the worker reconciliation pass heals any knowledge base that has ready exact-model chunks but no active index. Maintained indexes always match the current scene-default embedding model; a chunk/model mismatch stays `REINDEX_REQUIRED` and is never force-built. The build core is authorization-free and idempotent; only the HTTP route keeps owner authorization.
- Vector/hybrid search requires an exact active index row and matching ready chunk model/version/dimension. Missing index returns `REINDEX_REQUIRED`; application-memory corpus scans and dimension mixing are forbidden.
- Hybrid fusion is bounded, normalized, deterministic, and stably tied by immutable chunk identity. Optional rerank receives only membership-filtered bounded quotes, cannot introduce unseen chunks, validates unique in-range indices and finite scores, and degrades to fused order without public/legacy fallback.
- Conversations/messages are knowledge-base scoped and owner-private. Every get/update/archive/delete/retry query includes `owner_user_id=:actor`; platform administrators gain no implicit read. The conversation owner must be an active knowledge base member through a restrictive composite FK into `ima.kb_members`. The list endpoint (`GET /api/v1/conversations`) aggregates the calling user's own conversations across all knowledge bases and returns each row with its `kbId` and `kbName`; it never lists another user's conversations.
- Grounded Ask persists question/assistant state, performs retrieval first, emits persisted citations before any delta, streams only through governed target chat, closes upstream on cancellation, and persists `completed|knowledge_gap|failed|cancelled` terminal state.
- Empty retrieval returns the fixed knowledge-gap result and makes no chat call. Target model/rerank/index failure never broadens the corpus or invokes legacy/public infrastructure.
- Citation identity is exact `(document, version, generation, ordinal, digest)`. File versions are represented in immutable `document_versions`; citations restrict both version and exact chunk deletion. Completed message citations cannot be updated.
- Citation resolution checks conversation owner and current source authorization, loads the exact chunk, and never substitutes a newer version. Revoked/deleted sources return hidden 404.
- Logs/audit/errors contain safe IDs, modes, counts, durations, and stable reason codes only; never query, question, prompt, answer, quote, chunk text, hidden title/path, gateway URL, secret, or raw upstream body.

## Validation Matrix

| Condition | Required result |
|---|---|
| Nonmember asks/reads a knowledge base | Denied; no chunk/model/citation exposure |
| Membership revoke/move during retrieval/stream | Recheck hides source and cancels/terminates safely |
| Missing/mismatched ANN model/version/dimension | `REINDEX_REQUIRED`; no memory/legacy fallback |
| Ready exact-model chunks without an active index | Index built/refreshed automatically; no manual step |
| Two knowledge bases share embedding model | Distinct knowledge-base-predicate physical indexes and lifecycle rows |
| Invalid/timeout rerank | Deterministic pre-rerank order plus safe degradation |
| Empty accepted hits | `knowledge_gap`, empty citations, zero chat calls |
| User/admin accesses another owner's conversation | Hidden 404 |
| Citation source revised | Exact historical version/chunk resolves; current version not substituted |
| Citation/source deletion dependency | Delete refused until citation/conversation cleanup policy permits |
| Stream cancellation/upstream error | Upstream closed; persisted cancelled/failed state; bounded SSE event |

## Tests Required

1. Ruff format/check, strict mypy, full pytest, deterministic OpenAPI generation.
2. Fresh isolated PostgreSQL image with `vector` and `zhparser`; exact `IMA_REQUIRE_POSTGRES=1` test count passes with zero skips, migrations reach current head, catalog constraints/triggers/config/indexes are asserted.
3. Real `EXPLAIN (ANALYZE, BUFFERS)` fixtures prove GIN/HNSW candidate plans are bounded and knowledge-base/model/dimension predicates match the index.
4. Fake governed embedding/rerank/chat tests cover finite/dimension/index validation, no-hit no-chat, progressive SSE, cancellation, malformed events, and no fallback.
5. Owner/privacy, membership revoke races, conversation optimistic conflicts, citation stability/deletion, concurrent index build tests, and automatic index build/reconciliation healing of ready-but-unindexed knowledge bases run on PostgreSQL.
6. OpenAPI/Caddy tests prove exact Python routes and the terminal `/api/v1/internal/*` 404.

## Wrong vs Correct

### Wrong

```text
load 8,000 vectors into Python -> filter membership -> rerank -> browser tool-loop chat
```

### Correct

```text
knowledge base + membership-filtered SQL candidates
-> schema-qualified GIN and knowledge-base/model/dimension HNSW
-> bounded deterministic fusion -> optional governed rerank
-> persisted exact citations -> governed SSE chat
```
