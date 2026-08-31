# Design: Frontend UX Overhaul (ima-style)

Technical design for `08-30-frontend-ux-overhaul`. Requirements in `prd.md`; evidence in `research/` (ima-design-philosophy.md, current-ux-inventory.md, semi-design-feasibility.md).

Stack decision (user-approved): keep **Vue 3 + Quasar + TS + TanStack Query + identity-client**; adopt Semi's *visual language* as a custom theme, not Semi UI. Chrome 109 is a hard build target.

## 1. Shell & routing

### New shell

`src/AppFront.vue` stops rendering `MainDrawer`. New `src/layouts/AppShell.vue`:

- **Left rail** (fixed 240px at ≥1200px; overlay below): workspace switcher (top), nav entries **Ask / Knowledge base / History / Connectors / Workspace admin / Trash**, footer (account, admin-console link when role allows, sign out). Reuses `WorkspaceMenuList.vue` for switching.
- **Top bar** inside main pane per page (each page owns its header — fixes the current "home has no header" gap).
- Dead code removed with the shell swap: `MainDrawer.vue`, `TaskPanel*`/`src/utils/tasks.ts` registry (nothing calls `createTask`), `DarkSwitchBtn` (dark mode out of scope), hue controls.

### Route map (front app)

| New path | Component | Notes |
|---|---|---|
| `/` | `AskHome.vue` | composer home; `?conversation=` absent |
| `/ask/:conversationId` | `ConversationView.vue` | chat pane + citation preview pane |
| `/history` | `HistoryPage.vue` | conversation list (existing list/rename/archive/delete/retry APIs) |
| `/kb` | `KnowledgeWorkspace.vue` | three-pane; `?folderId=`, `?doc=` |
| `/knowledge/:documentId` | redirect → `/kb?doc=:id` | deep links preserved |
| `/connectors` | existing `WorkspaceConnectors.vue` (restyled) | moved from `/workspace/connectors` |
| `/workspace`, `/workspace/tags`, `/workspace/models` | existing pages, restyled | keep tab layout |
| `/trash`, `/settings`, `/account*`, auth, oauth, invitations | unchanged components, restyled where cheap | |

`WorkspaceLayout`'s route-tab bar is dropped; its pages become rail entries under a "Workspace" group. `/workspace/ask` (GroundedAskPage) is deleted — replaced by AskHome/ConversationView.

## 2. Ask experience

- Reuse `src/composables/use-grounded-knowledge.ts` (SSE `delta/citations/completed/knowledge_gap/cancelled/error`) and its unused conversation management (list/rename/archive/delete/retry) — wire it, don't rewrite it.
- `AskComposer.vue`: autosize input; **scope selector** (workspace fixed + folder picker, default "whole workspace") rendered as a chip inside the composer left; submit → POST `/workspaces/{id}/ask` then route to `/ask/:id`.
- `ConversationView.vue`: message list with **markdown rendering** (existing md renderer used by notes? if none, add `marked` + DOMPurify — check deps first; Quasar has no md renderer), streaming cursor, numbered superscript citation buttons inline in the rendered HTML (post-process `[n]` marks from citation events), follow-up composer at bottom, per-answer actions: **save as note**, retry on error.
- **Citation preview pane**: right side pane (collapsible) showing the cited document: notes → rendered markdown; files → `/documents/{id}/file/preview` iframe. Highlight: citation carries `quote` text; for notes, wrap first exact match in `<mark>`; for files, open preview (highlight best-effort, documented limitation).
- `HistoryPage.vue`: table/list of conversations (title, updated time), open → `/ask/:id`, rename/delete menu, empty state.

## 3. Knowledge workspace (three-pane)

`KnowledgeWorkspace.vue` = `FolderTreePane` (reuse `FolderTree.vue`, add **New folder** button → existing folder-create API) | `ItemListPane` (reuse `KnowledgeList.vue`, add header actions **New note**, **Upload**, tag filter, sort) | `PreviewPane` (reuse note render/iframe preview from `KnowledgeDocumentPage` logic, extracted into `DocPreview.vue`; "Ask about this document" button pre-fills composer scope and focuses home composer via router state).

- Create note: `CreateNoteDialog` → `knowledgeClient.createNote` → open in preview pane editor mode (textarea + rendered side-by-side replaces current raw `<pre>` dump).
- Upload: revive `FileInputArea.vue` (currently dead) inside `UploadDialog` → existing `uploadFile`/upload-ticket mutations.
- Keep `KnowledgeDocumentPage` as the full-page editor route? No — editor lives in PreviewPane; `/knowledge/:id` redirects. Version history dialog reused in PreviewPane.

## 4. Theme & visual language

- New `src/styles/tokens.css`: fixed palette (Semi-inspired): bg `#fff`, surface `#f7f8fa`, border `rgba(0,0,0,0.08)`, text `rgba(0,0,0,0.85/0.6/0.4)`, accent `#0077fa`, radius 6px, spacing 4/8 scale, shadow-sm/md. Light theme only.
- Replace `--a-*` HCT hue engine: delete hue store/settings; map legacy var names to tokens in one place during migration, then remove.
- Quasar brand colors set from tokens in `quasar.config.ts` (brand primary = accent).
- Density: content-first lists (36–40px rows), calm headers (16/14/13px type ramp).

## 5. Chrome 109 contract

- `quasar.config.ts`: `build: { target: { browser: ['chrome109'] } }` for both TARGET_APP builds (overrides Quasar's `baseline-widely-available` = chrome111 default).
- Forbidden in app CSS/JS: CSS nesting, `color-mix()`, `oklch()`, container queries, unprefixed `background-clip: text`, `Array.prototype.toSorted/toReversed` (Chrome 110+), `structuredClone` is OK (98+), `:has()` allowed only non-critical.
- Verification: builds succeed with target; grep dist for `toSorted|toReversed|color-mix|@container` as a manual gate step; real-Chrome-109 check deferred to operator (documented).

## 6. i18n

All new strings via existing i18n (`i18n/zh-CN.json`, `en-US` etc.), English keys; touched legacy keys updated; no global sweep.

## 7. e2e & tests strategy

- e2e suites reference old IA (drawer nav, `/workspace/ask`). Update per phase: identity/auth suites untouched (auth routes unchanged); knowledge/ask/model-governance suites rewritten against new routes/selectors using roles/text (stable `data-testid` added on rail entries, composer, citation marks).
- vitest: update component tests for deleted components; add unit tests for citation-mark post-processing and scope selector.
- Gate after each phase: lint 0/0 + test:unit + builds; full matrix (incl. e2e 42-equivalent and caddy drill) at the end.

## 8. Risks & tradeoffs

- **e2e churn**: IA change breaks selectors; mitigated by phased e2e updates + stable testids.
- **Markdown renderer dependency**: if no md renderer exists in front app, add `marked`+`dompurify` (small, Chrome109-safe); XSS-reviewed.
- **Preview highlight for files**: iframe preview can't be highlighted cross-origin; accepted limitation (notes highlight, files open at doc).
- **Settings hue removal** changes settings UX; acceptable per PRD (calm fixed palette).
- Admin app untouched except optional token import; separate URL remains.

## 9. Rollout / rollback

Pure frontend change; rollback = revert commit + redeploy web image. No API/migration coupling.
