# UX Design Language (ima-style workbench)

> The front app follows Tencent ima's "search–read–write" workbench philosophy
> with a Semi Design-inspired visual language on Quasar. This document is the
> single source of truth for tokens, information architecture, the Ask/citation
> UX contracts, the Chrome 109 compatibility policy, and testid conventions.

---

## 1. Design tokens

All colors/radii/spacing/shadows come from `src/styles/tokens.css` (`--tk-*`
custom properties, light theme only — dark mode is out of scope). Do NOT
introduce new hue-driven theming (the old HCT `--a-*` engine was deleted) and
do NOT hardcode palette colors in components; reference tokens.

### Palette

| Token | Value | Use |
|---|---|---|
| `--tk-bg` | `#ffffff` | Page/panel background |
| `--tk-surface` | `#f7f8fa` | Rail, headers, answer bubbles base |
| `--tk-surface-deep` | `#f2f3f5` | Inset surfaces (code, hover) |
| `--tk-border` | `rgba(0,0,0,0.08)` | Hairline borders |
| `--tk-border-strong` | `rgba(0,0,0,0.15)` | Emphasized borders (blockquotes) |
| `--tk-text` / `-secondary` / `-tertiary` | `rgba(0,0,0,0.85/0.6/0.4)` | Text ramp |
| `--tk-accent` | `#0077fa` | Single accent (Quasar brand `primary`) |
| `--tk-accent-hover/active/soft` | `#3395fb` / `#005fd6` / `rgba(0,119,250,0.08)` | Accent states/tints |
| `--tk-danger` / `-soft` | `#f93920` / `rgba(249,57,32,0.08)` | Error surfaces |
| `--tk-success` / `--tk-warning` | `#4cbf50` / `#ff8800` | Status colors |

### Shape, spacing, shadows

- Radii: `--tk-radius-sm: 4px`, `--tk-radius: 6px`, `--tk-radius-lg: 8px`.
- Spacing scale (4/8pt): `--tk-space-1..6` and `--tk-space-8` = 4/8/12/16/20/24/32px.
- Shadows: `--tk-shadow-sm` (cards), `--tk-shadow-md` (composer, popovers).
- Density: content-first lists (36–40px rows), calm headers with a 16/14/13px
  type ramp. Shared scaffolding classes: `.tk-header`, `.tk-page`, `.tk-card`,
  `.tk-card-title`, `.tk-card-subtitle`, `.tk-caption`.

---

## 2. Information architecture — left rail + morphing main pane

`src/layouts/AppShell.vue` owns the shell: a persistent left rail (Quasar
drawer, 240px, breakpoint 1200px, overlay below) with durable nouns. No nested
drawers, no global top bar — each page owns its own header (`q-header` +
`.tk-header` styling) with a menu button that toggles the rail on small widths.

Rail order: **knowledge base switcher** (`kb-switcher`, top — `KbMenuList`
popover: switch between memberships, create, join via share link) → **Ask
(`/`)** → **Knowledge base (`/kb`)** → **History (`/history`)** →
**Connectors (`/connectors`)** → **Settings (`/settings`)** → conditional
**Admin console** external link (only for `super_admin` / `platform_admin` /
`security_auditor`; separate deployment on the same host, port 8081 in
production, 9015 in local dev) → Sign out.

### Route map (front app)

| Path | Component | Notes |
|---|---|---|
| `/` | `AskHome.vue` | calm composer home; includes create/join knowledge base onboarding |
| `/ask/:conversationId` | `ConversationView.vue` | chat pane + citation pane |
| `/history` | `HistoryPage.vue` | conversation list (open/rename/archive/delete/retry) |
| `/kb` | `KnowledgeBase.vue` | three-pane; `?folderId=`, `?doc=` query state |
| `/connectors` | `ConnectorsPage.vue` | MCP/OAuth connector management |
| `/settings` | `SettingsLayout.vue` | single settings page (profile, security, sessions); the old `/account*` pages are gone |
| `/join/:token` | `JoinKnowledgeBase.vue` | knowledge base share-link join |
| `/oauth/consent` | `OAuthConsentPage.vue` | scope-only MCP consent |
| auth routes, catchAll | unchanged / `NotFoundPage.vue` | restyled with tokens |

The legacy admin pages (Overview/Tags/Models), `/trash`, and the
`/knowledge/:documentId` redirect are deleted; `MainDrawer`, task panel code,
and the hue engine are gone.

---

## 3. Ask experience contracts

### Composer (`src/components/AskComposer.vue`)

- One generous autosize textarea; **Enter sends**, Shift+Enter newline.
- Left of the send row: the **scope control** (`data-testid="ask-scope-chip"`).
  Home mode without document scope: folder picker button (default label "Whole
  knowledge base") opening `FolderPickerList`. With a document scope (one-shot from
  the knowledge pane via `src/stores/ask-context.ts`): a removable primary chip
  showing the document title; removing it restores the folder picker.
- The model picker slot (`<slot name="model" />`) stays empty until a gateway
  is configured; never render a fake model selector.
- Send is disabled while empty/busy; busy swaps send for Stop.

### Ask home (`AskHome.vue`)

Search-engine calm: product name, one-line grounding statement, composer,
curated hint chips (`data-testid="ask-hint"` fill the composer), footnote.
Submitting requires a selected knowledge base — without one the composer
blocks send and the page offers create/join onboarding; with one it
starts the shared stream (provided by AppShell under `groundedKey`) and routes
to `/ask/:conversationId` as soon as the stream reports an id, so the stream
keeps running across navigation.

### Conversation (`ConversationView.vue`)

- Chat thread: user bubbles right, assistant answers left inside `.md-body`
  markdown rendering (`src/utils/markdown.ts`: `marked` + DOMPurify, `mark`
  allowed). Streaming shows a live overlay that is replaced by the persisted
  thread once the last message reaches a terminal state with the streamed id.
- **Numbered citation marks**: `[n]` markers in answer content are
  post-processed into clickable superscripts (`.citation-mark`,
  `data-testid="citation-mark"`, `data-citation="n"`), only for ranks present
  in the message's citations; markers inside `<pre>/<code>` are untouched.
- Clicking a mark (or a `citation-source` row under live answers) opens the
  **citation pane** (`data-testid="citation-pane"`) — an in-app `DocPreview`
  that never navigates away. Notes highlight the cited passage by wrapping the
  first exact quote match in `<mark>`; files open the preview iframe
  (cross-iframe highlight is a documented limitation).
- Per-answer actions: **Save as note** (`save-as-note` → `SaveAnswerDialog`
  with folder picker; answer + Sources appendix become the note) and **Retry**
  on failed/cancelled answers (existing retry API).
- Terminal states render deterministically: `knowledge_gap` → calm "no answer
  in the knowledge base" row; `failed`/`cancelled` → error row + Retry.

### History (`HistoryPage.vue`)

Rail-level conversation list (`history-list`/`history-item`): title, updated
time, overflow menu (Rename / Archive-Restore / Delete). Opening navigates to
`/ask/:id`.

---

## 4. Knowledge base — three-pane page (`KnowledgeBase.vue`)

No membership renders the onboarding state (`kb-onboarding`: create
`kb-create` / join via share link `kb-join`); with memberships the header
carries the manage entry (`kb-manage` → `KbManageDialog` with members and
share-link panels). Pane 1 **tree** (`kb-tree-pane`): `FolderTree` + **New
folder** action (`kb-new-folder`). Pane 2 **list**: `KnowledgeList` rows
(36px+, status) with header actions **New note** (`kb-new-note`) and
**Upload** (`kb-upload`). Pane 3 **preview** (`kb-preview-pane`):
`DocPreview` — markdown render/edit for notes (editor + live render
side-by-side), iframe preview for files, version history, ingestion banners;
top-right **"Ask about this document"** (`doc-ask-button`) pre-scopes
the home composer through the ask-context store. Selection lives in the URL
(`?folderId=`, `?doc=`) so deep links and refresh survive; `/kb` with no
query means the knowledge base root. New notes open straight in editor mode.
Tags and trash UIs are deleted — delete is a direct hard delete gated by
dependency checks on the server.

---

## 5. Chrome 109 compatibility contract (hard requirement)

The built app must run on Chrome 109 (early-2023 Chromium).

- `quasar.config.ts`: `build.target.browser = ['chrome109']` for BOTH apps
  (overrides Quasar's chrome111 default). Keep it pinned.
- Forbidden in app code (JS and CSS):
  - `Array.prototype.toSorted` / `toReversed` / `toSpliced` (Chrome 110+) —
    copy first (`[...x].sort()`).
  - CSS nesting, `color-mix()`, `oklch()`, container queries (`@container`),
    unprefixed `background-clip: text` (use `-webkit-background-clip`).
  - `:has()` only for non-critical enhancement; keep it out of app CSS.
- v-html content (markdown, citation marks) must stay sanitized (DOMPurify) and
  styled with FLAT selectors in unscoped blocks — no nesting, Chrome 109.
- Verification: builds pass with the target; manual gate step greps dist for
  `toSorted|toReversed|toSpliced|color-mix|@container|oklch` (third-party
  wrappers that never execute on the forbidden path are acceptable only when
  identified and recorded; app code must have zero hits). Real Chrome 109
  verification is an operator manual step.
- Recorded finding (2026-08-30): the only `toSorted`/`toReversed`/`toSpliced`
  hits in `dist/` come from Vue's reactivity array wrapper
  (`@vue/reactivity`), which merely defines delegating methods; app/test code
  has zero call sites, so they stay inert on Chrome 109. `color-mix()`,
  `@container`, and `oklch()` have zero hits.

---

## 6. Testid conventions

Stable `data-testid`s are the e2e contract (Playwright `getByTestId`); add
them when touching these surfaces and never rename without updating
`tests/e2e/`:

- Rail: `kb-switcher`, `rail-nav-ask`, `rail-nav-kb`, `rail-nav-history`,
  `rail-nav-connectors`, `rail-nav-settings`.
- Knowledge base switcher/menu: `kb-add`, `kb-switch-item`, `kb-empty`,
  `kb-create-entry`, `kb-join-entry`, `kb-create-bottom`, `kb-join-bottom`,
  `kb-name-input`, `kb-create-button`.
- Ask: `ask-composer`, `ask-send`, `ask-stop`, `ask-scope-chip`, `ask-hints`,
  `ask-hint`.
- Conversation: `conversation-view`, `conversation-title`,
  `conversation-reload`, `assistant-answer`, `save-as-note`, `answer-retry`,
  `citation-mark` (injected by `injectCitationMarks`), `citation-source`,
  `citation-pane`.
- Knowledge: `kb-onboarding`, `kb-create`, `kb-join`, `kb-manage`,
  `kb-manage-dialog`, `kb-tree-pane`, `kb-new-folder`, `kb-new-note`,
  `kb-upload`, `kb-preview-pane`, `kb-preview-reopen`, `doc-ask-button`,
  `doc-close-button`, `folder-name-input`, `folder-create-button`,
  `note-title-input`, `note-create-button`, `upload-dropzone`, `folder-picker`.
- History: `history-list`, `history-item`, `history-item-menu`.
- Save answer: `save-as-note-dialog`, `save-as-note-title`,
  `save-as-note-confirm`.

---

## 7. e2e strategy (mirrors design §7)

Identity/auth and model-governance suites are unchanged by the IA overhaul.
The grounded-Ask and knowledge suites in `tests/e2e/` drive the real app
served from `dist/` with seeded accounts (`e2e-*@example.com`); because the
e2e environment has no model gateway or object storage, the Ask suite mocks
the knowledge-base Ask SSE endpoint at the browser edge (same protocol as the backend:
`conversation`/`message`/`citations`/`delta`/`completed`/`knowledge_gap`/
`error` frames) while citation previews and note creation stay on the real
API. Keep desktop `chromium` + `mobile-chromium` projects green.

---

## 8. i18n

All new UI strings go through `t('English key')` (i18n-pro, English keys).
zh-CN and zh-TW locale files must stay at parity (0 missing) for every touched
key; check with the i18n tooling before handoff. No global legacy sweep.
