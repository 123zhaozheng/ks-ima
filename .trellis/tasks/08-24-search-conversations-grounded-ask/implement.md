# Search, Conversations, and Grounded Ask Implementation Plan

## 1. Preflight and fixtures

- [ ] Refresh caller inventory for target chunks/index state, WorkspaceService, model governance, Bun retrieval/Ask, Zero chat/message, Vue Ask/search, citations, MCP, and deletion owners.
- [ ] Add fixtures for keyword/vector/hybrid ranking, mixed dimensions/models, stale generations, Chinese/English queries, ACL same-subject rules, revoke races, empty hits, rerank degradation, SSE cancellation/error, owner privacy, citation revision/deletion, and legacy coexistence.
- [ ] Pin exact operation IDs, error/event schemas, query/context/rate limits, role/action matrices, PostgreSQL test counts, and Playwright desktop/mobile gates.

## 2. Retrieval schema and indexes

- [ ] Add conversation/message/citation and search-index lifecycle schema with restrictive composite FKs, optimistic versions, immutable completed answers/citations, owner indexes, and populated-data downgrade refusal.
- [ ] Add bounded FTS state/GIN indexes and exact model-version/dimension pgvector ANN index lifecycle. Add reindex state/digest/count verification and safe retirement.
- [ ] Test fresh/repeat migration, constraints, mixed dimensions, source deletion dependencies, owner privacy, and `EXPLAIN (ANALYZE, BUFFERS)` index use.

## 3. Retrieval and rerank service

- [ ] Implement ACL-first keyword/vector/hybrid SQL, stable score normalization/fusion, filters, threshold/top-K, deterministic ties, cancellation, and safe result DTOs.
- [ ] Resolve query embeddings through Python model governance only when the selected mode requires them; require exact ready index generation.
- [ ] Implement optional post-ACL rerank with bounded candidates, finite/index validation, degradation marker, and no public/legacy fallback.
- [ ] Add authorization recheck before result/citation serialization and race tests for revoke/move/trash/reindex during retrieval.

## 4. Private conversations and citations

- [ ] Implement owner-private conversation/message CRUD, pagination, optimistic rename/archive/delete/retry, and hidden 404 for other owners including admins.
- [ ] Persist user question, assistant lifecycle, immutable citations, exact chunk identity, safe terminal states, and dependency-aware source/conversation deletion.
- [ ] Implement citation resolver against exact version/generation/ordinal/digest with current authorization and no newer-version substitution.

## 5. Grounded Ask and SSE

- [ ] Implement retrieval-first Ask orchestration and fixed knowledge-gap result with no chat invocation.
- [ ] Implement typed SSE events with citations before deltas, bounded prompt/context, governed chat stream, cancellation cleanup, progressive persistence, stable post-start error events, and no content logging.
- [ ] Add fake-stream tests for progressive chunks, disconnect, timeout, malformed upstream, cancellation, source-only failure, and no fallback.

## 6. Generated API and Vue migration

- [ ] Add stable OpenAPI operations/DTOs for search, conversations/messages, Ask stream initiation, cancellation/retry, and citation resolution; keep internal model execution private.
- [ ] Regenerate TypeScript and extend one shared client/composable for search pagination, SSE parsing, abort, optimistic rollback, workspace cancellation, message persistence, and citations.
- [ ] Migrate workspace search and Ask to target APIs while leaving generic legacy Chat isolated. Add desktop/mobile search/Ask/conversation/citation UX and all loading/error/degraded/gap/revoked states.

## 7. Coexistence and deletion evidence

- [ ] Add exact Caddy and coexistence tests, prove target routes never query legacy chunks/chats or invoke legacy/public fallback, and retain MCP compatibility symbols for its child.
- [ ] Produce retained/deletion manifest for Bun retrieval, Ask, Zero conversations/messages, browser tools, citation parser, and MCP search/Ask.
- [ ] Coordinate source/chunk/object/conversation/citation permanent deletion and rollback retention.

## 8. Required validation

```text
cd backend
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest -m postgres
uv run python scripts/export_openapi.py --check

cd ..
bun run generate:api
bun run lint
bunx vue-tsc --noEmit
bun test
bun run test:unit
bun run build:front
bun run build:admin
bun run build:server
bun run test:e2e
```

Additional gates: exact PostgreSQL FTS/ANN `EXPLAIN`, fake embedding/rerank/chat servers, ACL revoke-during-stream, zero-hit no-model assertion, owner-private matrix, citation stability/deletion dependencies, stream cancellation and resource cleanup, coexistence/residue scan, and sequential Quasar builds.

## 9. Rollback

- Preserve legacy search/chat artifact and target conversation/index snapshots before route cutover.
- During coexistence target Ask has one Python writer and target-only corpus; rollback switches routes/artifacts without reverse-writing target messages/citations into Zero.
- Do not delete legacy retrieval/chat or old target indexes until search parity, citation resolution, MCP migration, retention expiry, and final cutover verification pass.
