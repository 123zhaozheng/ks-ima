# Search, Private Conversations, and Grounded Ask

## Goal

Make Python the sole authority for ACL-first target-document retrieval, private user conversations, grounded answer streaming, and immutable citations. Users can search authorized knowledge, ask questions against versioned chunks, receive progressive citation-backed answers, and revisit private conversations without leaking inaccessible content or falling back to a public/legacy corpus.

## Background

- Python now owns folders, documents, immutable note/file versions, parsed text, deterministic chunks, embeddings, model governance, and WorkspaceService authorization.
- `ima.document_chunks` contains exact `(document_id, version, generation, ordinal)` identities, digests, text, model metadata, dimension, and pgvector values, but has no target FTS or ANN retrieval indexes.
- Legacy Bun retrieval and Ask use legacy chunks, application-memory cosine scoring, Zero chats/messages, and entity-ID citations. They remain isolated compatibility behavior, not target authority.
- Model governance already exposes guarded chat streaming, embeddings, and rerank with exact profile/model versions and fail-closed target behavior.

## Requirements

### R1. ACL-first retrieval

- Add Python-owned target-document search APIs and service queries over `ima.document_chunks` only.
- Apply active account/workspace/membership, folder lifecycle, document lifecycle, and same-subject `view_content`/`ask` authorization in SQL before chunk text enters ranking, rerank, context construction, citation serialization, or a model call.
- Support bounded `keyword`, `vector`, and `hybrid` modes from the assigned grounded-Ask profile, with deterministic score normalization/fusion, stable tie-breaking, threshold, top-K, folder/tag filters, and cancellation.
- Recheck authorization before returning search results and before emitting citations because ACLs may change during retrieval or streaming. Unauthorized/missing resources behave as nonexistent.

### R2. PostgreSQL search and vector indexes

- Add normalized target FTS state and GIN indexes for versioned chunk text. Use the project Chinese/mixed text configuration and bounded source text.
- Add pgvector ANN indexes partitioned or otherwise isolated by exact embedding model version and dimension. Different dimensions/models never share an incompatible ANN index.
- A model/profile change creates a new ingestion generation and requires reindex before it becomes searchable. `REINDEX_REQUIRED` is explicit; no unbounded application-memory vector scan or fake index-ready state is allowed.
- Candidate pools, SQL timeouts, vector probes/search parameters, context characters, and total returned text are bounded and observable through safe counts only. `EXPLAIN` index usage is a release gate.

### R3. Optional rerank and degradation

- Invoke rerank only after ACL filtering and deterministic candidate fusion, using a bounded candidate list and Python model governance.
- Validate rerank indices and finite scores. Valid rerank changes ordering only; it cannot introduce unseen chunks.
- When rerank is optional and unavailable/malformed/timeout, preserve pre-rerank ordering with a safe degradation marker. Existing broken target assignments never invoke a public, browser, or legacy fallback.

### R4. Private conversations

- Add Python-owned workspace-scoped conversations, messages, answer state, and citations with explicit `owner_user_id`, lifecycle, optimistic version, UTC timestamps, and restrictive foreign keys.
- Every list/get/append/rename/archive/delete operation constrains `owner_user_id` to the current user. Workspace administrators and platform roles gain no implicit access to another user's conversation.
- Persist user questions before retrieval/model execution. Persist assistant status/text and immutable citation rows through `pending|streaming|completed|knowledge_gap|failed|cancelled` lifecycle.
- Legacy Zero chats remain separate during coexistence and are not migrated or mutated by the MVP.

### R5. Grounded Ask behavior

- Add a dedicated Ask operation that performs authorized retrieval before model execution.
- Empty accepted retrieval returns a successful fixed knowledge-gap result with `citations=[]` and does not call chat, rerank, or an unrelated fallback model.
- Nonempty retrieval builds a bounded prompt from exact authorized quotes and calls only governed target chat streaming.
- Chat failure after retrieval returns a stable failed/source-only state according to the API contract; it never invents an answer, broadens the corpus, or calls legacy/public infrastructure.

### R6. SSE stream contract

- Stream typed SSE events: `conversation`, `message`, `citations`, `delta`, optional `degraded`, terminal `completed`, `knowledge_gap`, `cancelled`, or bounded `error`.
- `citations` is emitted before any answer `delta`. Each event includes stable message/conversation IDs and sequence/order information suitable for reconnect or duplicate suppression.
- Cancellation closes the governed upstream stream and persists assistant state as cancelled. Once streaming begins, failures use bounded stable SSE error events rather than HTTP exception bodies.
- Never include prompts, hidden chunk text, gateway details, raw upstream errors, credentials, or authorization data in events/logs/audit.

### R7. Stable citations

- Persist and return exact immutable identity: document ID, document version, file generation when applicable, chunk ordinal, and chunk digest. Display title/path/quote/score are safe projections, not identity.
- Citation resolution reauthorizes every request and loads the exact historical source/chunk. It never redirects to the current document version or another ordinal.
- Source deletion, permanent cleanup, or access revocation produces hidden not-found. Citation dependencies prevent unsafe permanent deletion while retained conversations require the source.

### R8. Vue migration

- Add generated clients and one Vue Query/composable boundary for search, conversations, message history, citation resolution, Ask SSE, cancellation, retry, pagination, and workspace-scoped cache clearing.
- Migrate workspace Ask and search surfaces to target APIs. Keep generic legacy chat isolated during coexistence; target Ask does not call Zero chat mutators or legacy search tools.
- Render progressive answers, citation list/navigation, knowledge-gap, retry/cancel, degraded rerank, unavailable model, access-revoked, archived, offline, empty, and conflict states on desktop and mobile.
- Persist no query/prompt/answer/citation content in browser storage beyond existing bounded draft requirements.

### R9. Migration, coexistence, and deletion

- Add resumable plan/apply/verify/report for legacy conversations only if a safe exact mapping is provable; otherwise explicitly retain them as legacy read-only history and report them outside target MVP.
- Target search never dual-reads target and legacy chunks in one result set. A target-owned document or conversation has one Python writer.
- Produce a retained-symbol/deletion manifest for Bun retrieval, Ask, Zero chat/message mutators, citation parser, MCP search/Ask, and legacy chunk/vector code, with named later owners for MCP and final deletion.
- Document/chunk/object permanent deletion coordinates citation and conversation dependencies; no endpoint reports success while retained citations still reference the source.

### R10. Security, audit, and operations

- Audit safe IDs, actions, result codes, candidate/citation counts, mode, and durations only. Never store search query, question, prompt, answer, quote, source text, path/title for hidden resources, model body, or raw exception.
- Enforce query/context/body/rate/concurrency/time limits and exact Caddy routing. Public OpenAPI excludes private model bridges and internal retrieval operations.
- Add database/index health, model availability, stream cancellation, and operational metrics using low-cardinality safe dimensions.

## Acceptance Criteria

- [ ] AC1: Keyword/vector/hybrid retrieval returns only authorized target chunks with deterministic bounded ranking, exact filters, stable tie-breaking, and indexed SQL plans.
- [ ] AC2: Same-subject `ask + view_content`, lifecycle, workspace, folder/tag, revoke-during-request, and platform-admin-without-membership cases reveal no restricted IDs, text, counts, paths, tags, scores, or citations.
- [ ] AC3: Optional rerank operates only on ACL-filtered bounded candidates, validates finite scores/indices, degrades safely, and never invokes public/legacy fallback.
- [ ] AC4: Conversations and messages are owner-private under all list/get/mutate/delete paths, including workspace-admin and platform-admin attempts.
- [ ] AC5: Empty retrieval returns a fixed knowledge-gap response with no chat invocation; grounded SSE emits citations before deltas, persists terminal state, and closes the upstream stream on cancellation/error.
- [ ] AC6: Citations retain exact document/version/generation/ordinal/digest identity, reauthorize on resolution, never substitute newer content, and block unsafe source deletion while retained.
- [ ] AC7: Generated OpenAPI/client, Vue Query, workspace search, Ask conversation, citation navigation, progressive/cancel/retry/degraded states pass desktop/mobile browser journeys without Zero target authority.
- [ ] AC8: Fresh/repeat migrations, FTS/ANN indexes, `EXPLAIN`, PostgreSQL concurrency/revoke tests, fake model streams/rerank, OpenAPI/Caddy, builds, residue scans, and required PostgreSQL/browser suites pass with zero skips in CI.

## Out of Scope

- Public web search, internet browsing, external corpus fallback, cross-workspace search, shared/team conversations, conversation sharing/export, voice input, multimodal question answering, OCR, public links, and final MCP implementation.
- General-purpose agent tool loops or arbitrary browser-selected tools inside grounded Ask.
- Migration of legacy chats when exact owner/message/branch/citation equivalence cannot be proven; legacy history may remain isolated until final cutover.

## Technical Decisions

- Retrieval corpus is target `ima.document_chunks` only.
- Keyword remains available where the governed profile permits it; vector search requires an exact ready model/dimension generation.
- ANN indexes are model-version/dimension isolated, and activation requires completed reindex evidence.
- Empty retrieval never calls chat. Target assignment failure is terminal and never interpreted as permission to use legacy/public infrastructure.
- Citation identity is immutable source identity, not current title/path or legacy entity ID.
