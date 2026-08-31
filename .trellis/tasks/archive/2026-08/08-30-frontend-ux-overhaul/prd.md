# PRD: Frontend UX Overhaul — ima-style Knowledge Workbench

## Goal

Rework the front app's UX to follow Tencent ima's design philosophy (research/ima-design-philosophy.md): a calm, knowledge-base-centric "search–read–write" workbench. The current shell is a drawer-plus-single-column layout carried over from the legacy product; the owner wants it torn down and rebuilt around ima's IA and interaction patterns while keeping the Vue 3 + Quasar stack and the existing Python API contract.

Hard constraint: the built app must run on **Google Chrome 109** (early-2023 Chromium).

## Users

Internal employees of a private deployment: ordinary users (view/ask/edit per ACL), workspace admins, and platform admins (admin app stays separate; only a light consistency pass here).

## Scope (MVP)

### R1. Information architecture — left rail + morphing main pane

- Replace the global MainDrawer navigation with a persistent narrow left rail holding durable nouns: **Ask (home)**, **Knowledge base**, **Connectors**, **History**, **Settings**, plus workspace switcher at top and user/admin footer.
- The main pane morphs per selection; no nested drawers for primary navigation.
- Home (Ask) is a search-engine-calm surface: one generous composer, workspace/folder **scope selector as a first-class control next to the composer**, model picker slot (visible only when a gateway is configured), curated empty-state hints.

### R2. Ask experience with trustworthy citations

- Conversations stream into a chat-style main pane; follow-ups continue in context.
- Answers carry **numbered citation marks**; clicking one opens the cited document **in an in-app preview pane and highlights the cited passage** (never navigates away).
- Conversation history is a first-class surface (History rail entry): list, reopen, retry failed answers via existing API.
- One-click "save answer as note" into a chosen folder (closes the search–read–write loop).

### R3. Knowledge base — three-pane workspace

- Pane 1: folder tree (existing FolderTree, restyled) with **new folder** action.
- Pane 2: item list with AI/ingestion status, tags, sort; **create note** and **upload files** actions live here (APIs already exist: POST /folders/{id}/notes, upload tickets).
- Pane 3: preview pane (markdown render for notes, file preview endpoint for files) with a contextual **"Ask about this document"** entry top-right that pre-scopes the composer.
- Trash/restore reachable from the tree context (existing APIs).

### R4. Visual language — Semi-inspired tokens on Quasar

- Adopt Semi Design's visual language as a custom Quasar theme (do NOT adopt Semi UI itself — see research/semi-design-feasibility.md): calm neutral surfaces, single accent, 4/8pt spacing scale, 6–8px radii, content-first density, light theme.
- Replace the current HCT-hue-driven `--a-*` theme with a fixed token set; keep dark mode out of scope.
- i18n: keep existing mechanism; all new/changed UI strings go through i18n (zh-CN + en-US parity for touched keys).

### R5. Chrome 109 compatibility contract

- Pin Vite/Quasar build target to `chrome109` for front and admin builds.
- CSS feature policy: no CSS nesting, no `color-mix()`, no container queries, no unprefixed `background-clip: text` (use `-webkit-` prefix), keep `:has()`/`oklch()` out entirely.
- The contract is enforced by build target + a documented forbidden-features list in the frontend spec + review checklist (no new lint tooling).

### R6. Gates stay green

Full existing matrix must pass after the overhaul: lint (0/0), bun test, test:unit, build:front, build:admin, e2e (updated to the new IA), caddy drill, backend matrix untouched.

### R7. Right-side preview panes collapse by default (owner feedback, 2026-08-30)

- Every right-hand preview pane (KB document preview, and any future sibling) defaults to **collapsed**, showing only a slim reopen rail; it auto-expands when the user selects a document (or deep-links one) and can be closed again.
- The conversation citation pane already opens on demand and stays that way.

### R8. ChatGPT/Claude-grade Ask hero and composer aesthetic (owner feedback, 2026-08-30)

- Ask home is a vertically and horizontally centered hero (like ChatGPT/Claude): display title, one-line greeting, single composer card, hint chips, footnote — never pinned to the top.
- Composer is a white elevated card (20px radius, hairline border, soft shadow that deepens on focus), 16px input, round accent send button.
- Conversation thread and follow-up composer stay centered in a ≤860px column.

## Out of scope

- React or Semi UI migration (decision recorded in research/semi-design-feasibility.md).
- Admin app redesign (consistency pass only: shared tokens if cheap).
- Discovery plaza / public knowledge bases; smart writing / podcast / mind-map generation; mobile apps.
- i18n sweep of untouched legacy keys; dark mode.
- Backend API changes (the existing contract covers all MVP needs).

## Acceptance criteria

1. Opening the app lands on the calm composer home; a user can ask a scoped question and receive a streamed answer with numbered citations.
2. Clicking a citation opens the in-app preview at the cited passage (highlighted), without leaving the conversation.
3. A user can create a folder, create a markdown note, and upload a file — entirely within the three-pane knowledge workspace.
4. History lists past conversations; reopening shows the full thread; retry works for failed answers.
5. "Save answer as note" persists an answer into a chosen folder and it appears in the knowledge list.
6. The app renders and functions on Chrome 109 (build target pinned; no forbidden CSS/JS syntax in shipped bundles — verified by build + targeted manual check).
7. All release gates green, including updated e2e suites.
