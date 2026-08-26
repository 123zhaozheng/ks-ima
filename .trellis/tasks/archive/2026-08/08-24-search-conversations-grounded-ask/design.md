# Search, Conversations, and Grounded Ask Design

## 1. Authority and module boundary

Python becomes the sole target authority for retrieval, conversation/message persistence, grounded answer orchestration, and citations. It consumes versioned chunks/embeddings from the ingestion slice, WorkspaceService authorization, and exact model-governance assignments.

```text
Vue search / Ask
  -> generated REST + SSE client
  -> /api/v1/workspaces/{id}/search|conversations|ask
  -> RetrievalService + ConversationService + GroundedAskService
  -> WorkspaceService ACL + ima.document_chunks + conversation/citation tables
  -> ModelGovernanceService embedding/rerank/chat stream
```

Legacy Bun retrieval, Zero chats/messages, browser tool loops, and entity-ID citations stay isolated for rollback. Target APIs never mix legacy and target chunks or fall back on target errors.

## 2. Schema

Add an additive migration with restrictive workspace/owner/source FKs:

- `chunk_search_indexes`: exact model ID/version/dimension, ingestion generation/index state, index name/partition, status, source counts/digests, activated/retired timestamps, and reindex dependency.
- Extend `document_chunks` with normalized FTS state (`tsvector` generated/maintained column) and indexes. Use partial indexes for ready/current generations.
- `conversations`: UUID, workspace ID, owner user ID, title, lifecycle, optimistic version, created/updated timestamps.
- `conversation_messages`: UUID, conversation/workspace/owner, role, status, bounded text, sequence, optimistic version, correlation ID, created/updated/completed timestamps.
- `message_citations`: assistant message ID + citation ordinal, document ID/version, file generation, chunk ordinal/digest, bounded quote, safe rank/score metadata, created timestamp. Restrictive FKs prevent source deletion while retained citations exist.

Conversation owner/workspace columns use composite FKs and indexes so every query can include `owner_user_id=:actor`. Published completed message/citation identity is immutable.

## 3. Retrieval query

`RetrievalService.search(actor, workspace, query, filters, profile)`:

1. Require active membership and resolve safe profile configuration.
2. Compute authorized folder IDs using the canonical ACL projection for `view_content` or `ask` with same-subject dependencies.
3. Build bounded keyword candidates with `websearch_to_tsquery`/`ts_rank` over authorized active documents/chunks.
4. If mode needs vectors, obtain query embedding through model governance, select only chunks matching exact model/version/dimension and active index generation, and run bounded pgvector distance SQL using the appropriate model/dimension index.
5. Normalize/fuse scores deterministically, dedupe by immutable chunk identity, apply filters/threshold/top-K, and stable tie-break by document/version/generation/ordinal.
6. Optional rerank receives only the ACL-filtered bounded quotes. Validate returned indices/scores; invalid/unavailable optional rerank preserves fused order and records safe degradation.
7. Recheck access before serialization and before Ask citation emission.

No application-memory scan over the corpus is allowed. Add SQL statement timeouts and release-gate `EXPLAIN (ANALYZE, BUFFERS)` fixtures.

## 4. ANN lifecycle

A pgvector ANN index is tied to exact embedding model version and dimension. Use dimension-specific expression/partial indexes or model-version partitions; never index mixed dimensions under one vector opclass. The ingestion/index service records source generation and digests, builds a new index concurrently where supported, verifies counts/plans, then atomically activates it. Profile/model switch returns `REINDEX_REQUIRED` until the matching index is ready. Old indexes remain readable only for citations/rollback and are retired through explicit cleanup.

## 5. Private conversation boundary

Every conversation/message operation requires active workspace membership and exact owner equality. Workspace and platform administration do not override owner privacy. IDs for another owner return 404. Creation stores the question before retrieval; assistant row starts pending and transitions through streaming to completed/knowledge_gap/failed/cancelled. Optimistic versions protect rename/archive/delete/retry. Conversation deletion refuses or coordinates citation/source retention according to the deletion contract.

## 6. Grounded Ask orchestration

`GroundedAskService.ask()` creates/persists user and assistant rows, performs `ask` retrieval, and:

- on zero accepted hits, persists `knowledge_gap`, returns fixed answer/citations empty, and makes no chat call;
- on hits, persists immutable citation rows and emits them before opening the chat stream;
- builds a bounded instruction/context containing exact numbered quotes and source handles;
- calls `managed_chat_stream()` only through target model governance;
- persists progressive/terminal assistant state and closes upstream on cancellation;
- on chat failure, emits bounded error/source-only state without invented answer or fallback.

## 7. SSE protocol

Endpoint returns `text/event-stream`, `Cache-Control: no-store`, and disables proxy buffering. Events carry `event`, message/conversation IDs, monotonically increasing sequence, and typed payload:

```text
conversation -> message -> citations -> delta* -> completed
conversation -> message -> knowledge_gap
... -> degraded
... -> cancelled|error
```

Citations are persisted and emitted before deltas. Pre-stream validation uses Problem Details; post-start errors use a stable SSE error code. AbortSignal/client disconnect closes the governed stream and persists cancellation. Reconnect support may use Last-Event-ID only if persisted event sequencing is implemented; otherwise clients retry from authoritative message state without replaying model execution.

## 8. Citation resolution

Citation identity is `(document_id, document_version, file_generation|null, chunk_ordinal, chunk_digest)`. Resolver verifies owner conversation access plus current source `view_content`, then loads the exact immutable chunk/version. It returns safe current display metadata separately and never substitutes current content. Revocation/deletion returns hidden 404. Search results may use transient citations, while grounded answers persist them before streaming.

## 9. Vue flow

Add target search page/dialog and dedicated Ask conversation route. One composable owns query keys, paginated search, conversation/message loading, SSE parsing, abort, progressive updates, retry, citations, conflicts, and workspace cancellation. Generic legacy Chat remains separate. Typed citation components navigate to exact target document/version where available. Desktop/mobile UI covers empty, loading, offline, no-hit, degraded rerank, model unavailable, cancelled, access revoked, archived, and citation-not-found states.

## 10. Migration/coexistence/rollback

Do not migrate legacy chats unless a later plan proves owner, branch, message, tool, and citation equivalence. Record them in a retained manifest. Cutover routes target workspace search/Ask only; generic legacy chat remains Bun-owned. Rollback switches SPA/API routes and preserves target conversations/read-only rows; it does not reverse-write into Zero. Remove Bun retrieval/Ask/Zero chat ownership only after search parity, citation stability, MCP migration, and final deletion gates.

## 11. Security and operations

Query/question/answer/chunk/quote content is excluded from logs and audit. Safe metrics include mode, candidate counts, hit counts, durations, degradation/error codes, stream state, and correlation IDs. Bound query length, candidate pools, rerank count, context characters, stream duration, message size, concurrent streams, and per-user/workspace rates. Internal model routes remain absent from browser OpenAPI/Caddy.

## 12. Validation

Use unit ranking/fusion/cursor/SSE/citation tests; fake guarded embedding/rerank/chat streams; PostgreSQL fresh/repeat migration, indexes/EXPLAIN, owner privacy, ACL revoke races, concurrent messages/cancel, citation deletion dependencies; generated OpenAPI/Caddy; Vue/Vitest and desktop/mobile Playwright search/Ask/citation journeys; coexistence and residue scans; and exact cleanup of databases, ports, streams, and Playwright output.
