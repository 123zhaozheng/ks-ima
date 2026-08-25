# Central Model Governance Evidence

## CodeGraph Snapshot

The repository CodeGraph was synchronized after workspace authorization. The
model surface is split across four active paths:

1. `src-server/kb/models.ts` resolves plaintext `provider.settings.apiKey` and
   `baseURL` for Bun chat, embedding, and rerank.
2. `src/utils/model.ts`, `src/services/stream-message.ts`, and
   `src/services/generate-chat-title.ts` construct AI SDK models in the browser.
3. `src/pages/WorkspaceModels.vue`, provider views/components, shared mutators,
   and Zero queries let workspace administrators configure gateways, secrets,
   model choices, chunking, retrieval, and reindex behavior.
4. `src/admin/pages/ModelsPage.vue` and `src-server/admin.ts` manage public
   models, including price fields and global model IDs, through Bun/Drizzle.

CodeGraph reports `gatewayForModel` reaches `embedTexts`, `kbAsk`, and `rerank`.
`toSdkModel` reaches title generation and browser streaming. `ModelSelect` is a
direct consumer of workspace/public Zero model rows.

## Locked Target Decisions

- Python owns model gateways, encrypted credentials, model catalog, capability
  profiles, health, and workspace assignment.
- Platform administrators mutate configuration. Security auditors may read safe
  metadata. Workspace administrators and ordinary users cannot read gateway,
  remote model, prompt, secret, or low-level retrieval configuration.
- Workspaces receive business workflow aliases and availability only. Users do
  not select a model per chat.
- Inference is server-side. Browser SDK/provider construction is deleted.
- MVP uses an OpenAI-compatible intranet gateway contract for chat, embedding,
  and a `/rerank` extension; Ollama is supported only through its compatible
  endpoint, not a second provider abstraction.
- Published profile versions are immutable. Assignments point to one published
  version and preserve the version used by jobs/answers.
- Embedding dimension/model changes require impact analysis and cannot silently
  reinterpret existing vectors. Actual durable reindex execution belongs to the
  object-storage/durable-ingestion child.
- Legacy provider/model tables remain read-only migration/rollback inputs only
  while live Bun consumers require them. New writes use Python exclusively.

## Legacy Removal Inventory

Remove after target cutover:

- workspace gateway/model/RAG tuning and provider entity routes/views;
- public model Bun admin routes/dialogs and input/output price fields;
- `ModelSelect`, assistant/per-chat model selectors, browser `toSdkModel`, and
  browser AI SDK inference;
- provider type/options metadata, arbitrary provider headers/tools, exposed API
  keys, public/free model and plan/quota/cost behavior;
- active Zero model/provider queries, mutators, preloads, and schema relations;
- localization and dependencies with no remaining server-side consumer.

Retained legacy database rows must have a named migration/rollback consumer and
are deleted by the final legacy cleanup child after the rollback window.
