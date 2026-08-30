# Implement: Frontend UX Overhaul (ima-style)

Ordered checklist for `08-30-frontend-ux-overhaul`. Design in `design.md`. Each phase ends with its gate; do not start the next phase with a red gate.

## Phase 0 — Foundations (theme + build target)

1. Add `build.target.browser ['chrome109']` to `quasar.config.ts` for both apps; verify builds still pass.
2. Create `src/styles/tokens.css` (Semi-inspired palette/spacing/radius per design §4); wire into both apps; set Quasar brand colors.
3. Map legacy `--a-*` vars onto tokens (compat shim), delete hue engine + `DarkSwitchBtn`; simplify Settings appearance section (language + send-key only).
4. Gate: `bun run lint`, `test:unit`, `build:front`, `build:admin`.

## Phase 1 — Shell & routing

5. Add `AppShell.vue` (left rail + per-page headers), rewire `AppFront.vue`; nav entries Ask / Knowledge / History / Connectors / Workspace group / Trash + footer (account, admin link by role, sign out).
6. Remap routes per design §1 (home → AskHome placeholder, `/kb`, `/ask/:id`, `/history`, `/connectors`, redirects `/knowledge/:id` → `/kb?doc=`, delete `/workspace/ask` route + `GroundedAskPage`).
7. Delete dead shell code: `MainDrawer.vue`, `TaskPanel*`, `src/utils/tasks.ts`.
8. Add stable `data-testid`s on rail entries/composer.
9. Gate: lint/unit/builds + smoke (dev server: nav works, old deep links redirect).

## Phase 2 — Knowledge three-pane workspace

10. Build `KnowledgeWorkspace.vue` (tree | list | preview). Extract `DocPreview.vue` from `KnowledgeDocumentPage` (markdown render for notes, iframe preview for files, history dialog, ingestion banner).
11. Add actions: NewFolderDialog, CreateNoteDialog, UploadDialog (revive `FileInputArea.vue`), tag filter/sort in list, trash/move document actions.
12. "Ask about this document" button → composer scope prefill.
13. Gate: lint/unit/builds + vitest for new components + manual dev-server pass of PRD criteria 3.

## Phase 3 — Ask home, conversations, citations

14. `AskComposer.vue` with scope chip; `AskHome.vue` calm empty state with example hints.
15. `ConversationView.vue`: streaming markdown answers, numbered citation superscripts, follow-ups, retry, save-answer-as-note dialog.
16. Citation preview pane (note highlight via `<mark>` on quote match; file → preview iframe).
17. `HistoryPage.vue` (list/rename/delete/open).
18. Markdown rendering: verify existing renderer; if absent add `marked` + `dompurify` (XSS review).
19. Gate: lint/unit/builds + unit tests for citation post-processing + manual pass of PRD criteria 1, 2, 4, 5.

## Phase 4 — Restyle remaining pages + cleanup

20. Restyle Connectors, Workspace admin pages (Overview/Tags/Models), Trash, Account/Auth surfaces with tokens; drop `WorkspaceLayout` tab bar.
21. i18n parity for all touched/new keys (zh-CN + en-US).
22. Remove leftover `--a-*` shim if unused; sweep unused components.
23. Gate: lint/unit/builds.

## Phase 5 — e2e + final gates + spec

24. Rewrite affected e2e suites to new IA (knowledge, ask, model-governance admin unchanged, identity unchanged); keep desktop+mobile projects; add testids where needed.
25. Full matrix: `bun run lint`, `bun test`, `test:unit`, `build:front`, `build:admin`, `IMA_E2E_POSTGRES_PORT=55433 bun run test:e2e`, `test:caddy-routing`; backend matrix untouched (spot check pytest).
26. Chrome-109 residue check: grep dist bundles for forbidden syntax (`toSorted|toReversed|color-mix|@container`); document operator manual-check note.
27. Update `.trellis/spec/frontend/` (component/quality guidelines + new `ux-design-language.md` capturing tokens, IA, citation UX contracts, chrome109 policy).
28. trellis-check pass; commit; archive task.

## Rollback points

Each phase is an independent commit; revert per-phase to roll back. No backend/schema coupling.
