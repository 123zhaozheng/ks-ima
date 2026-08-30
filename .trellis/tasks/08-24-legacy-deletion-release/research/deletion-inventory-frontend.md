# Research: Deletion Inventory — Legacy Frontend Residue (Zero-bound views, chat, removed features)

- **Query**: Which frontend pages/components/stores are legacy (unrouted or Zero-bound) vs live?
- **Scope**: internal
- **Date**: 2026-08-29

## 0. Key structural fact

The migrated slices (identity, workspaces, knowledge, storage, search/ask, OAuth, connectors,
model governance admin) live in `src/pages/*`, `src/admin/*`, `src/api/{ima,knowledge,grounded}-client.ts`,
`src/utils/identity-client.ts` and are Zero-free (verified by import scan). BUT the app shell and
several shared stores are still Zero-bound, and the legacy chat/item/entity experience is still
routed. Deleting Zero therefore requires **rewiring the shell**, not just deleting dead files.

## 1. Zero runtime core (delete after rewiring consumers)

- `src/utils/zero-session.ts` — creates `new Zero(...)` at module load; exports `z`, `mutate`,
  `user`, `connectionState`, `zRef`. Imported by ~20 modules (grep `zero-session` in src/).
- `src/composables/zero/query.ts`, `src/composables/zero/view.ts` — Zero query/useQuery bindings.
- `src/utils/config.ts` — `ZERO_CACHE_URL`.
- `src/stores/local-entities.ts` (uses `zql` from schema.gen).

## 2. Zero-bound shared stores used by MIGRATED pages (REWIRE, then delete Zero parts)

| Store/composable | Zero usage | Migrated consumers |
|---|---|---|
| `src/stores/workspace.ts` | `useQuery(queries.workspaces/fullWorkspace)`, `z.preload`, `mutate(mutators.updateMemberData/updateLastWorkspaceId)`, plus legacy `hc` fallback `client.api.connectors.workspaces` | AppFront.vue, WorkspaceLayout, TrashLayout, InvitationLayout, GroundedAskPage, WorkspaceConnectors/Models/Tags/Overview, FolderTree, CreateConnectorDialog, CreateInvitationDialog, SearchEntityDialog, composables/{acl,ask-knowledge,entity-conf}, stores/{perfs,active-entities,recent-entities,readonly-state,right-dir} |
| `src/stores/user-data.ts` | Zero queries/mutators (perfs/data) | workspace.ts, AppFront chain |
| `src/stores/perfs.ts` | `mutate(mutators...)` | AppFront.vue (theme etc.) |
| `src/stores/readonly-state.ts` | `connectionState` | (shell read-only banner) |
| `src/composables/require-login.ts` | `user` from zero-session | WorkspaceLayout, TrashLayout, InvitationLayout, SettingsLayout |
| `src/composables/ask-knowledge.ts` | `connectionState` | grounded ask flow |
| `src/pages/RedirectToFolder.vue` (route `/`) | `user`, `connectionState`, workspace store | root route |
| `src/components/MainDrawer.vue` | `user` | AppFront.vue |
| `src/admin/pages/EmptyPage.vue` | `user` | admin app root |

Rewire targets already exist: `src/utils/identity-client.ts` (session, workspaces list via
`/api/v1/...`), `src/api/ima-client.ts`, TanStack Vue Query boot (`src/boot/vue-query.ts`).
`switchWorkspace` currently pushes `/folder/:id` (legacy route) — must move to the migrated
knowledge route (`/` or `/knowledge/:documentId`).

## 3. Legacy-only views/routes (delete)

- Routes in `src/router/routes.ts` to remove: `/:type(chat|item|folder)` block incl.
  `DualViewPage`; `RedirectToFolder` rewired to Python workspace selection instead.
- `src/views/`: `ChatView.vue`, `ChatViewWrapper.vue`, `DirView.vue`, `EntityView.vue`,
  `ItemView.vue`, `ItemViewWrapper.vue` (all Zero/legacy-API bound; ChatView is the "retained
  legacy consumer" pinned by `backend/tests/contract/test_search_coexistence.py` — that pin must
  be removed in this task).
- `src/pages/DualViewPage.vue`.

## 4. Legacy-only components/services (delete; consumers all inside legacy subtree)

Chat & messages: `MessageItem.vue`, `MessageInput.vue`, `MessageEntity.vue`, `MessageImage.vue`,
`MessageInfoDialog.vue`, `ToolCallItem.vue`, `KbCitations.vue` (only consumer ToolCallItem),
`ViewWrapper.vue`, `RightDrawer.vue`, `RightEntityList.vue`, `NavigationDialog.vue`(?),
`services/stream-message.ts` (calls `/api/v1/chat/completions`), `services/generate-chat-title.ts`
(`/api/v1/chat/titles`), `services/import-aiaw.ts`, `composables/chat-res.ts`,
`composables/quote.ts`, `utils/chat-tools.ts` (only place the `ai` SDK types are used).

Entity/knowledge-legacy UI: `EntityItem.vue`, `EntityLink.vue`, `EntityList.vue`,
`EntityListOptionsBtn.vue`, `EntityListOptionsDialog.vue`, `EntityTypeSelect.vue`,
`CommonItem.vue`(?), `DenseItem.vue`(?), `SearchEntityDialog.vue` (legacy `client.api.search`),
`SelectDirDialog.vue`, `SelectDirItem.vue`, `SelectEntityPanel.vue`, `NewEntityBtns.vue`,
`ParseFilesDialog.vue`, `FileInputArea.vue`(?), `CreateShortcutDialog.vue`,
`UpdateShortcutDialog.vue`, `ShortcutInputItems.vue`, `ShortcutKeyInput.vue`,
`composables/run-shortcut.ts`, `utils/create-entity.ts`, `utils/knowledge-upload.ts` (legacy
`/api/s3` path via `utils/functions.ts:66`), `utils/blob-cache.ts`, `utils/hash.ts` (legacy
client-side sha256/proof for `/api/s3`), `composables/blob-url.ts`, `composables/entity-conf.ts`,
`composables/state-proxy.ts`(?), `stores/{active-entities,recent-entities,local-entities,
entity,global-settings,right-dir,plugins}.ts`.

Plugins / removed features: `components/PluginContextBtn.vue`, `PluginToggleItems.vue`,
`PromptArgsDialog.vue`(?), `stores/plugins.ts`, `utils/builtin-plugins/{index,mermaid,workspace}.ts`
(chat plugins incl. workspace switcher plugin), `utils/template-engine.ts` (liquidjs; only
ToolCallItem). Shortcut concept is explicitly removed (parent design §19).

Hono client bridge: `src/utils/hc.ts` (typed `hc<AppType>` from src-server; delete once all
consumers are rewired/deleted — consumers: WorkspaceConnectors, CreateConnectorDialog,
stores/workspace, SearchEntityDialog, EntityList, ItemView).

Legacy connector UI in migrated page: `WorkspaceConnectors.vue` lines 352/514/531 still call
legacy `/api/connectors` via hc alongside Python service principals; `CreateConnectorDialog.vue`
creates legacy keys and shows `/api/mcp` hints; `ConnectorCreatedDialog.vue` shows legacy
`/api/mcp` URL text. Per OAuth deletion gate these legacy-key paths must go (service principals
only), and `src/utils/mcp-config.ts` must point at `/mcp` (currently builds `/api/mcp` URLs,
lines 15/98; its test `mcp-config.test.ts` asserts `/api/mcp`).

## 5. Legacy bun tests & vitest files

Bun tests (`bun test`): `src/utils/identity-client.test.ts` (KEEP — identity is live),
`src/utils/mcp-config.test.ts` (UPDATE to `/mcp`), `src/utils/open-created-entity.test.ts`
(verify target; legacy open-entity helper), `src-shared/utils/acl.test.ts` (delete with legacy
ACL util), plus the three `src-server/**.test.ts`.

Vitest (`tests/components/*.vitest.ts`) — all target migrated components (AccountSecurity,
AuditPage, GroundedAskPage, KnowledgeTree, ModelsPage, OAuthConsentPage, UpdateSettingsDialog,
UsersPage, WorkspaceConnectors, WorkspaceModels, WorkspaceOverview, WorkspacesPage) — KEEP;
`WorkspaceConnectors.vitest.ts` must be updated when legacy connector UI is removed.
`tests/components/KnowledgeFileClient.test.ts`, `KnowledgeFileReplacement.test.ts` run under
`bun test` (`.test.ts`) — KEEP.

## 6. Router/layout leftovers

- `src/layouts/InvitationLayout.vue` still imports Zero queries/mutators + `zero-session`
  (accept-invite flow) — must rewire to identity-client invitation acceptance.
- `src/layouts/SettingsLayout.vue` → `SettingsList.vue` includes `ShortcutKeyInput` (legacy
  keyboard-shortcut settings) — remove that item; rest (theme/locale) keep.
- `quasar.config.ts` devServer proxies: `/api` → `SERVER_URL` (Bun) and `/zero-cache` →
  `ZERO_CACHE_URL`; repoint `/api` to `PYTHON_API_URL` and drop `/zero-cache`.
- `index.html` / `src-pwa` — no legacy references found.

## 7. Commercial / removed-feature residue in frontend

Grep for payment/stripe/plan/order/quota/translation/channel/mcpPlugin/pubRoot/searxng/jina/gread
across `src/`: matches only in legacy chat subtree (assistant role, message types) and generated
OpenAPI schema (unrelated). No payment UI remains in `src/` (removed before baseline 6afe5aa).
Remaining commercial surface is the **legacy DB tables** and `drizzle-zero.config.ts` table list
(see python-db inventory), plus i18n keys (unused strings in `i18n/*.json` — low priority,
optional sweep).

`public/` assets and `assets/` — parent plan requires a reference+license audit before removing
anything; no deletion recommended without that audit.

## Caveats / Not Found

- Exact per-component keep/delete decisions marked `(?)` need a compile-time import-graph pass at
  implementation (delete subtree, then `bun run typecheck` reveals shared survivors).
- Chat history is intentionally not migrated (cutover scope decision, counts-only archive), so
  removing ChatView removes the only legacy chat UX — accepted by the runbook's "system never
  live" statement (`docs/legacy-cutover-runbook.md:16-18`).
