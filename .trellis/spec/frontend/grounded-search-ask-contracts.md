# Grounded Search And Ask Frontend Contracts

## Scope / Trigger

Apply this contract to target workspace search, private conversation/history UI, grounded Ask SSE parsing, cancellation/retry, citation rendering/navigation, workspace switching, generated clients, Vue Query, and desktop/mobile browser verification.

## Signatures

```text
src/api/grounded-client.ts
src/composables/use-grounded-knowledge.ts
src/pages/GroundedAskPage.vue
/workspace/ask
```

## Contracts

- DTOs come from generated OpenAPI types. REST uses the shared IMA transport; SSE uses one bounded typed parser with credentials, Origin/CSRF mutation headers, AbortSignal, stable event names, and no component-local duplicate client.
- The target Ask page is mounted under `WorkspaceLayout` at `/workspace/ask`; generic legacy Chat remains a separate coexistence surface.
- Search supports target filters/modes and renders safe title/quote/rank projections only. `REINDEX_REQUIRED`, degraded rerank, no hits, access revoked, offline, archived, loading, and retry states are explicit.
- Ask events are handled in order: conversation/message, citations, delta, terminal completed/knowledge-gap/cancelled/error. Answer deltas never render before the citation event for grounded answers.
- Conversation queries and all mutations are workspace and owner scoped by the server. The UI supports list/open/rename/archive/delete/retry without assuming administrators can read other owners.
- Workspace changes cancel active streams, clear target query caches, and remove stale conversations/results/citations from the prior workspace even when the workspace ID changes outside the standard switch action.
- Cancellation aborts the fetch reader, leaves authoritative persisted terminal state to reload, and never reports completion. Retry uses expected versions and preserves prior completed history.
- Citation chips/rows use typed exact citation data and navigate to target document/version resolution. Legacy entity-ID citation parsing is not used for target grounded answers.
- Query, question, answer, quote, and citation content are not persisted to localStorage/Pinia beyond bounded current view state. Raw upstream errors, prompts, gateway details, and secrets are never rendered.
- Desktop/mobile controls remain keyboard/touch accessible and avoid overlap/horizontal overflow.

## Validation Matrix

| Condition | Required UI/result |
|---|---|
| Empty search/Ask retrieval | Explicit knowledge-gap; no fabricated streaming answer |
| `REINDEX_REQUIRED` | Index-required state/action for authorized admin; no fallback result |
| Rerank degradation | Original results remain, bounded degraded marker |
| Citations event then deltas | Citations visible before progressive answer text |
| Cancel during stream | Reader aborts, cancelled state, no completed state |
| Workspace changes mid-stream | Stream and old queries cleared immediately |
| Other-owner conversation ID | Unavailable/404; no stale cached content |
| Citation revoked/deleted | Hidden not-found state; no newer-source substitution |

## Tests Required

1. Vitest mounts the real `GroundedAskPage` with Vue Query and exercises search, SSE citations/deltas, cancellation, no-hit, retry/degraded/error, workspace change, and responsive classes.
2. Client tests assert generated paths, credentials/CSRF, SSE framing, AbortSignal, event ordering, and typed errors.
3. ESLint, `vue-tsc --noEmit`, Vitest, and sequential Quasar builds pass.
4. Desktop and Pixel-class mobile Playwright exercise target search, grounded answer, citations-before-delta, cancellation, no-hit/degraded states, conversation actions, citation navigation, and overflow/overlap checks. Route fixtures may isolate UI protocol, while PostgreSQL/model fake tests separately prove backend behavior.
5. Coexistence tests prove target Ask does not call Zero chat mutators, legacy search tools, or public/legacy model fallback.

## Wrong vs Correct

### Wrong

```typescript
createLegacyChat()
await legacyWorkspaceSearch(question)
streamGenericChatWithBrowserTools()
```

### Correct

```text
generated target search/conversation API
-> typed grounded SSE parser
-> citations rendered before deltas
-> workspace-scoped cancellation/cache clearing
```
