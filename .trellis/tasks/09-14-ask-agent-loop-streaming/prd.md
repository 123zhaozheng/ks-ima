# Ask: agent loop with streaming retrieval tools (ChatGPT-style)

## Problem

The product owner's intent: the Ask window should itself be an **agent loop** that calls
built-in retrieval tools, with a capability and design language comparable to ChatGPT.
They also perceive the current Ask as "not streaming".

### What actually exists (do not rebuild)

- **The transport is already SSE end to end.** `POST .../ask` and `.../retry` return
  `StreamingResponse(media_type="text/event-stream")`
  (`backend/src/ima/api/v1/search.py:141-182`); the frontend really does consume it
  incrementally (`src/api/grounded-client.ts:34-56`) and renders deltas as they arrive
  (`src/pages/ConversationView.vue:147-167`, `328-329`).
- Events already defined: `conversation`, `message`, `citations`, `delta`, `completed`,
  `knowledge_gap`, `cancelled`, `error` (`search.py:65-67`).
- Retrieval is a decent hybrid retriever: `websearch_to_tsquery` over the `ima.mixed`
  zhparser config + `ts_rank` (`search.py:405-439`), pgvector cosine
  (`search.py:441-482`), fusion via `fuse_scores()` with `vector_weight`, optional
  managed rerank (`search.py:550-625`).
- Cancellation works (AbortController → `cancelled` persisted, `search.py:1169-1171`).
- Markdown + DOMPurify + clickable `[1]` citation superscripts already render
  (`src/utils/markdown.ts:26-78`, `src/components/CitationSources.vue`).
- The model gateway **already accepts a `tools` parameter** and supports streaming
  (`backend/src/ima/infrastructure/model_gateway/egress.py`), and MCP already implements
  knowledge tools (`backend/src/ima/application/mcp.py`).

### Why it still feels wrong

1. **It is a fixed single-shot RAG, not an agent loop.** `SearchService.ask()`
   (`search.py:1003-1179`) does: retrieve once → re-retrieve for authorization → one LLM
   generation. No query rewrite, no multi-hop retrieval, no tool calling, no
   self-correction.
2. **Time-to-first-byte is bad**, which is why it "feels" non-streaming: the first
   retrieval happens **before** the `StreamingResponse` generator is returned
   (`search.py:1090-1103`), then a second retrieval and citation persistence happen inside
   the generator (`1129-1146`) — so nothing reaches the browser until all retrieval is done.
3. **Conversation history never reaches the model.** Messages are persisted and returned
   by `get_conversation()` (`search.py:663-684`), but the LLM call passes only the current
   question (`search.py:1153-1161`). Multi-turn is an illusion.
4. **Possible token loss across chunk boundaries**: `_deltas(raw)`
   (`search.py:1182-1193`) decodes and splits each HTTP byte chunk independently, with no
   cross-chunk buffer, while the gateway forwards arbitrary byte chunks
   (`egress.py:493-497`). A `data:` line split across two chunks can be dropped.
5. Grounded profile settings `score_threshold` and `max_context_chars`
   (`backend/src/ima/domain/model_governance.py:102-115`) are **not** applied in
   `ask()`; the bounded path hardcodes `50000` (`search.py:927-929`).

## Goal

Ask becomes a real, cancellable, streaming agent loop: the model decides when to search,
the user watches retrieval happen, answers stay grounded with exact citations, and
multi-turn context works — without regressing the existing single-shot path.

## Requirements

### 1. Fix perceived latency and streaming correctness (do this first)

- Return the SSE generator **immediately**; move the first retrieval inside it.
- Emit `conversation` / `message` right away, plus a new `retrieving` (or
  `tool_call`) event so the UI can show progress before the first token.
- Give `_deltas()` a cross-chunk buffer so partial `data:` lines are never lost.
- Actually apply `score_threshold` and `max_context_chars` from the grounded profile.

### 2. Internal tool executor (shared with MCP, not via MCP HTTP)

Extract a reusable in-process tool layer (e.g. `backend/src/ima/application/ask_tools.py`)
sharing implementation with `mcp.py` but **not** going through the external OAuth/HTTP
transport. Minimum tool set:

- `search_knowledge(query, folderId?, documentId?)`
- `list_dir(folderId?)`
- `get_document_outline(documentId)`

Hard constraints: tools run as the **current Ask user**, reuse existing membership/role
checks (`backend/src/ima/application/authorization.py`), treat the request scope as a
non-bypassable filter, cap result counts and quote lengths, and return exact citation
identity so answers can only cite what tools actually returned.

### 3. The loop

- `messages = [system, bounded conversation history, user]` — include prior turns.
- Up to N rounds (e.g. 6). Each round: stream from the model with `tools=…`;
  if `tool_calls` arrive, accumulate the JSON arguments across deltas, execute, append a
  `role=tool` message, emit a `tool_call` SSE event, continue; otherwise stream the final
  answer and finish.
- Enforce max rounds, total token/context budget, upstream cancellation propagation,
  safe degradation on tool error, and a final authorization re-check before persisting
  citations.

### 4. API/protocol

- Extend the Ask request with an opt-in flag (e.g. `"agent": true`). **Default must
  preserve today's exact event sequence and behaviour.**
- Add the `tool_call` event (name, argument summary, hit count, round).
- Regenerate/adjust OpenAPI artefacts. Note the current schema wrongly declares the Ask
  200 response as `application/json` (`src/api/generated/schema.ts:6907-6918`,
  `frontend/generated/openapi.json:9413-9444`) — fix that while you are here.

### 5. Frontend (ChatGPT-like, but keep it simple)

- Handle `tool_call` in `src/api/grounded-client.ts` / `src/composables/use-grounded-knowledge.ts`.
- Show a **collapsed-by-default** "检索过程" trace above the answer
  (new `src/components/AskToolTrace.vue`), plus a "正在检索…" state before first token.
- Add regenerate for successful answers (retry currently only appears for failed/cancelled
  messages, `src/pages/ConversationView.vue:104-117`).
- Keep the existing design tokens and the Chrome 109 CSS policy; do not redesign the page.

## Non-goals

- Adding `pydantic-ai` or another agent framework — the gateway already takes `tools`;
  implement a minimal loop with no new dependency.
- Internet search or any outbound non-intranet tool.
- Changing the retrieval fusion algorithm or the rerank provider.
- Full ChatGPT feature parity (attachments in-chat, branching, voice).

## Acceptance criteria

- Backend tests: multi-round tool calling; arguments split across stream chunks; max-round
  cap; tool permission denial; scope escape attempt is blocked; cancellation mid-loop;
  final authorization re-check; citations only from tool results; `_deltas` chunk-boundary
  buffering.
- Frontend tests: `tool_call` rendering; citations arriving before deltas; stop does not
  emit a false `completed`; regenerate.
- `agent=false` (default) path is byte-for-byte compatible with today's event sequence.
- `uv run pytest` and `bun vitest run` pass.

## Key files

- `backend/src/ima/application/search.py` (`ask`, `ask_bounded`, `_deltas`, `sse`)
- `backend/src/ima/api/v1/search.py`, `search_contracts.py`
- `backend/src/ima/application/mcp.py` (extract shared tools)
- `backend/src/ima/infrastructure/model_gateway/egress.py` (tools + streaming)
- `src/api/grounded-client.ts`, `src/composables/use-grounded-knowledge.ts`
- `src/pages/ConversationView.vue`, new `src/components/AskToolTrace.vue`
