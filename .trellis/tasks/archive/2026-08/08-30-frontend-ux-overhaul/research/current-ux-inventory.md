# Research: Current UX Inventory (front + admin apps)

- **Query**: Precise inventory of current user-facing UX to plan an ima-style redesign
- **Scope**: internal
- **Date**: 2025-08-30

## 0. App topology (corrects task assumptions)

- There is **no `src-admin/` directory**. The admin app lives at `src/admin/` and is the *same* Quasar project compiled twice: `quasar.config.ts` aliases `@routes` to `src/admin/routes` when `TARGET_APP=admin` (quasar.config.ts:89-93). Scripts: `dev:front` / `dev:admin` / `build:front` (PWA) / `build:admin` (package.json).
- Deployment (Caddyfile): front app on `:8080` (`/srv/front`), admin app on `:8081` (`/srv/admin`). Same API proxy rules on both. **There is no in-app link from the front app to the admin console** — it is a separate URL only.
- Shared code: `src/utils/identity-client.ts` (API client + `session` query), `src/api/*` clients, `src/components/*` (some reused by admin), i18n, theme engine.
- Front app is a PWA (service worker handling in `src/AppFront.vue:19-32`).

## 1. Routes & screens

### Front app (`src/router/routes.ts`, `src/router/auth.ts`)

| Path | Component | Purpose |
|---|---|---|
| `/` and `/welcome` | `src/pages/WorkspaceKnowledgePage.vue` (in `MainLayout`) | Home: knowledge list of current folder (workspace root or `?folderId=` subfolder) |
| `/knowledge/:documentId` | `src/pages/KnowledgeDocumentPage.vue` | Document detail: note editor or file preview/replace |
| `/chat/:rest*` | redirect → `/` | Legacy chat deep links (chat was removed with "Zero-bound chat experience") |
| `/workspace` | `WorkspaceOverview.vue` (in `WorkspaceLayout`) | Workspace administration: members, groups, directory permissions |
| `/workspace/connectors` | `WorkspaceConnectors.vue` | Agent access: MCP URL, interactive OAuth grants, service principals + credentials |
| `/workspace/models` | `WorkspaceModels.vue` | Read-only list of workspace capabilities (grounded_ask, embedding, reranking) |
| `/workspace/tags` | `WorkspaceTags.vue` | Tag CRUD (create/rename/merge/delete); no assignment to documents |
| `/workspace/ask` | `GroundedAskPage.vue` | Grounded Ask (SSE answer + citations) and keyword search |
| `/trash` | `TrashLayout.vue` | Trash list with restore / delete-permanently |
| `/invitations/:token` | `InvitationLayout.vue` | Accept workspace invitation (one button) |
| `/settings` | `SettingsLayout.vue` | Personal settings (appearance, theme hue, language, send-key) |
| `/account` | `AccountLayout.vue` | Profile: name, email, links to security & change-password |
| `/account/security` | `AccountSecurity.vue` | Profile, TOTP setup/recovery codes, active sessions |
| `/auth/sign-in` | `SignInForm.vue` (in `AuthLayout`) | Sign in (+ TOTP dialog) |
| `/auth/sign-up` | `SignUpForm.vue` | Sign up |
| `/auth/reset-password` | `ResetPasswordForm.vue` | Reset password via `?token=` |
| `/auth/accept-invite` | `AcceptInviteForm.vue` | Invitation bootstrap account form |
| `/oauth/consent` | `OAuthConsentPage.vue` | OAuth consent for agent (MCP) connections |
| `/:catchAll(.*)*` | `NotFoundPage.vue` | 404 |

### Admin app (`src/admin/routes.ts`)

| Path | Component | Purpose |
|---|---|---|
| `/` | `EmptyPage.vue` | Redirect: → `/users` if logged in, else sign-in |
| `/users` | `UsersPage.vue` | User table: search, create, edit, roles, reset password/TOTP, ban, revoke sessions |
| `/workspaces` | `WorkspacesPage.vue` | Workspace table: search, create (name + initial admin), archive/restore/delete |
| `/models` | `ModelsPage.vue` | Model governance with tabs: Gateways, Models, Profiles, Assignments & impact |
| `/audit` | `AuditPage.vue` | Plain audit-event table (time/action/target/result) |
| `/auth/*` | reused `authRoute` | Same auth forms as front app |

**Note:** there is **no OAuth-clients admin page** (the task brief mentioned it; it does not exist in code or routes). OAuth surface that exists is user-facing: consent page + WorkspaceConnectors grants.

## 2. Per-screen layout (structural level)

- **App shell** `src/AppFront.vue`: `q-layout view="lHr Lpr lFf"` rendering **MainDrawer globally** + `router-view`. Every front route (including auth/consent) sits under the drawer.
- **MainLayout** (`src/layouts/MainLayout.vue`): only `StateHeader` (a dismissible global error banner, `src/components/StateHeader.vue`) + `router-view`. **The home/knowledge route has no top bar, no title, no toolbar** — drawer + content only.
- **WorkspaceKnowledgePage**: single pane — full-height `KnowledgeList` (flat item list of folders/files/notes with icons; cursor "Load more"; loading/error/empty states). No preview pane, no detail split, no breadcrumbs; folder context comes only from the drawer tree + `?folderId` query. Empty-workspace state shows a spinner/"no workspace" placeholder.
- **KnowledgeDocumentPage**: one column. Top action row (back, borderless title input, History, Replace, Download, Preview, Cancel/Retry ingestion, Save). Error/conflict/ingestion banners. For `file`: title, version caption, and an **iframe** filled by a presigned preview URL (only after clicking Preview). For `note`: raw markdown `textarea` **side by side with a plain `<pre>` text dump** (not rendered markdown). History = modal dialog with version list (notes: click to restore).
- **WorkspaceLayout** (`src/layouts/WorkspaceLayout.vue`): its own `q-header` (menu toggle + workspace name) and a **q-route-tab bar**: Overview | Capabilities | Agent access | Tags | Ask. All workspace subpages render below the tabs; each page is a centered single column (`max-width: 800–900px`) — no secondary pane.
- **WorkspaceOverview**: tabs (Members / Groups / Directory permissions) implemented as `q-tabs` + `q-tab-panels` *inside* the page (nested tabs under the layout tabs). Heavy use of `$q.dialog` prompts for add/invite/role/group actions.
- **WorkspaceConnectors**: two stacked "band" sections (Agent access: MCP URL + connected grants list; Service access: admin-only create form grid + principals list with credential rows).
- **WorkspaceModels / WorkspaceTags / GroundedAskPage / TrashLayout / SettingsLayout / AccountLayout**: single-column lists/cards. **GroundedAskPage** is a 2-column `row` (left: search input + results list; right: question textarea + Ask button + plain-text answer + citations list). No chat history, no message bubbles, no conversation sidebar.
- **AuthLayout**: centered `max-w: 500px` form column under a title header. **InvitationLayout**: centered icon + text + one join button. **OAuthConsentPage**: centered card with header icon, "Connection" list, "Access" scope badges + write-access warning, Deny/Approve footer.
- **Admin MainLayout** (`src/admin/layouts/MainLayout.vue`): `AdminDrawer` (its own drawer, `v-model` local ref) + header (menu toggle, route title, `SystemStatusIndicator`) + page container. Admin pages are toolbar row + `q-table` (+ tabs on ModelsPage).

## 3. Navigation model

- **MainDrawer** (`src/components/MainDrawer.vue`, width 275, breakpoint 1200 — `src/stores/ui-state.ts`), always `show-if-above` on desktop:
  1. Workspace switcher item (avatar + name, dropdown → `WorkspaceMenuList.vue`: current workspace → `/workspace`, list of member workspaces to switch, "+" Join-by-link dialog, Account, Sign Out).
  2. `FolderTree.vue` — lazy-loaded folder tree (folders only) driving `/?folderId=`.
  3. Bottom list: **Ask** (`useAskKnowledge` → router.push `/workspace/ask`), **Tasks** (`TaskPanelBtn` → `TaskPanel` dialog), **Trash**, **Workspace Settings** (`/workspace`), then a footer row: Personal Settings button + `DarkSwitchBtn`.
- Workspace switching: `workspaceStore.switchWorkspace` (`src/stores/workspace.ts`) cancels/removes query caches, persists `lastWorkspaceId`, and always routes to `/`.
- Per-section headers exist only in sub-layouts (Workspace/Trash/Settings/Account/Auth have a `q-header` with a menu toggle). **The root knowledge page has none**, and below the 1200px breakpoint there is no visible way to reopen the drawer on `/`.
- Admin entry: none in front UI; separate deployment on port 8081. Admin role guard in `src/admin/AppAdmin.vue:20-34` (super_admin / platform_admin / security_auditor).
- `src/App.vue` sets `document.title` from `route.meta.title`.

## 4. Key interactions (as implemented today)

- **Create note**: **no UI.** `knowledgeClient.createNote` (`src/api/knowledge-client.ts:45`) exists but no component calls it.
- **Upload file**: **no UI for first upload.** `uploadFile` mutation (`src/composables/use-knowledge.ts:91`) is unused by any `.vue`. Only **Replace** exists (on `KnowledgeDocumentPage`, `replaceFile` mutation, XHR PUT with progress + abort). `FileInputArea.vue` (drag/click/paste dropzone) is imported only by admin's `FileInputDialog.vue`, which itself is **dead code** (imported nowhere).
- **Ask copilot**: drawer "Ask" → `/workspace/ask`. `GroundedAskPage` calls `useGroundedKnowledge` (`src/composables/use-grounded-knowledge.ts`): SSE stream via `groundedClient.ask`, events `delta`/`citations`/`completed`/`knowledge_gap`/`cancelled`/`error`. Answer rendered as raw `whitespace-pre-wrap` text (no markdown rendering). Ctrl+Enter submits.
- **Citations**: list under answer — "Source {rank}" + 2-line quote; click → `/knowledge/{documentId}` (full page navigation, no inline highlight/popup). Search results work the same.
- **Conversation management**: composable supports list/rename/archive/delete/retry of conversations, **but no UI uses any of it** — each Ask is stateless in the UI.
- **Connectors/MCP**: `/workspace/connectors` shows the MCP endpoint URL (copy), interactive connected-agent grants (revoke), and for workspace admins a create-service-principal form (name/purpose/owner/folder-root/expiry/scopes) with one-time secret banner, rotate/revoke credential actions.
- **Document lifecycle**: edit note (textarea) + save with optimistic-concurrency banners (`VERSION_CONFLICT`), history dialog + restore, download, iframe preview, ingestion status banner with cancel/retry (1.5s poll in `useKnowledgeIngestion`). **Missing UI**: trash a document (`trashDocument` mutation unused), move document, create folder, assign tags to documents (`replaceTags` unused). Trash page itself restores/deletes fine.
- **Tasks panel**: `src/utils/tasks.ts` defines a reactive task registry, but **nothing calls `createTask`** — the Tasks button always shows an empty dialog.

## 5. Component inventory (`src/components/`)

Structural (layout shells / navigation):
- `MainDrawer.vue` — global left drawer (switcher + tree + bottom nav)
- `FolderTree.vue` — folder navigation tree (lazy load, expand state)
- `WorkspaceMenuList.vue` — workspace switcher menu
- `KnowledgeList.vue` — folder contents list (the main content pane)
- `KnowledgeTrashList.vue` — trash list with actions
- `SettingsList.vue` — settings form list
- `StateHeader.vue` — global error banner header
- `TaskPanel.vue` / `TaskPanelBtn.vue` — tasks dialog + trigger

Leaf widgets:
- `AAvatar.vue` (text/icon/url/svg avatar), `DenseItem.vue`, `MenuItem.vue`, `CommonItem.vue`, `WorkspaceItem.vue` (list rows)
- `DarkSwitchBtn.vue` (auto/dark/light cycle), `HueSlider.vue`, `HueSliderDialog.vue`, `HctPreviewCircle.vue` (theme hue picker)
- `SendKeySelect.vue`, `SetPasswordInputs.vue`, `FileInputArea.vue` (dropzone), `HintCard.vue` (empty-state image+text, used by NotFoundPage)
- Auth/account dialogs & forms: `SignInForm.vue`, `SignUpForm.vue`, `ResetPasswordForm.vue`, `AcceptInviteForm.vue`, `ForgotPasswordDialog.vue`, `ChangePasswordDialog.vue`, `VerifyTotpDialog.vue`, `FolderAclDialog.vue`
- `AInput.js` — plain JS wrapper component (Quasar input preset)

Admin components (`src/admin/components/`): `AdminDrawer.vue`, `SystemStatusIndicator.vue`, `UpdateSettingsDialog.vue`, `CreateUserDialog.vue`, `UpdateUserDialog.vue`, `BanUserDialog.vue`, `FileInputDialog.vue` (dead), `NumberUnitInput.vue`.

## 6. i18n + theming

- **i18n**: `i18n-pro` library; English strings are the source keys, wrapped with `t(...)` from `src/utils/i18n.ts`. Translations: `i18n/zh-CN.json`, `i18n/zh-TW.json` (~818 entries each; many stale chat/plan/model-era keys). Extraction config: `i18nrc.ts` (scans `src/**`, auto-translates en→zh via googlex). Locale picked in `src/utils/local-data` + `getLocale` (`i18n/index.ts`); switching reloads the page. Note: several admin pages (`WorkspacesPage`, `AccountSecurity`, `AccountLayout`) use **hard-coded English strings** without `t()`.
- **Theme engine** (`src/composables/set-theme.ts`): Material Color Utilities (HCT). A single user-pickable **hue** (default `135` — green, `src/utils/config.ts`) generates a full M3-like token set written as `--a-*` CSS vars (pri/sec/ter/err/suc/warn, containers `pri-c`…, surfaces `sur`, `sur-c-lowest…highest`, on-colors, outline, inverse). Dark/light tone ramps are explicit; applied app-wide via `useSetTheme` in `AppFront.vue` (front, hue from perfs store) and `AppAdmin.vue` (fixed default hue).
- **Token plumbing**: `uno.config.ts` maps UnoCSS attributify utilities (`bg-sur-c`, `text-on-sur-var`, …) to `--a-*` vars; shortcuts `item-rd`, `route-active`, `pri-link`, `shadow-default`. `src/css/materialize.scss` bridges Quasar (`--q-primary: var(--a-pri)` etc.) and restyles q-field/q-menu/q-toggle. `src/css/quasar.variables.scss` holds Quasar defaults (largely overridden at runtime).
- **Current visual tone**: M3-ish tonal surfaces, rounded items (`item-rd`), Material Symbols Outlined icons (`sym_o_*`), Roboto, subtle shadows, no gradients/illustrations, hue default green. Settings expose dark mode (auto/light/dark) + hue picker + language.
- **Leftover assets**: `app.scss` imports `md-editor-v3` preview CSS and `md-theme-override.scss`, but **md-editor-v3 / katex / @vue-office are not imported by any component** — chat-era deps still in package.json and CSS.

## 7. Pain-point candidates for an ima-style three-pane overhaul

1. **No persistent middle/preview pane**: home is drawer + single list; opening a document is a full page push (`/knowledge/:id`) with back button. ima-style tree → list → reader/preview split requires restructuring `WorkspaceKnowledgePage`/`KnowledgeDocumentPage` into one routed workspace screen with internal selection state.
2. **Drawer carries everything**: workspace switcher, folder tree, Ask, Tasks, Trash, Settings all live in one drawer (MainDrawer is rendered even on auth/consent pages). ima model wants a slim icon rail + collapsible library pane; current drawer mixes navigation, content tree, and utility entries.
3. **Home route has no header/top bar** at all (MainLayout = error banner only); search, breadcrumbs, and primary actions have no home. Below 1200px the drawer cannot be reopened from `/`.
4. **Missing primary content actions**: no create-note, no upload, no new-folder, no doc context menu (rename/move/trash/tag) despite API+mutations existing (`createNote`, `uploadFile`, `moveDocument`, `trashDocument`, `replaceTags`). An ima-style "+" experience must be built from scratch on top of `useKnowledgeMutations`.
5. **Ask is a settings-tab, not a workspace citizen**: it sits under `/workspace/ask` among admin tabs, is a two-column form with plain-text answer, no markdown rendering, no conversation history UI (composable already supports conversations), citations navigate away. ima-style copilot needs a right pane / floating panel with streaming markdown and inline citations.
6. **Concern-mixing pages**: `WorkspaceOverview` nests members/groups/ACL tabs inside the layout's own tab bar (double tabs); `WorkspaceConnectors` mixes end-user grant view with admin credential management; Models/Tags/Capabilities are read-mostly admin surfaces mixed into the user's workspace tabs.
7. **Fragmented header patterns**: each layout re-implements its own `q-header` (some with menu toggle, some without); `StateHeader` error banner is a separate component only in MainLayout.
8. **Legacy baggage**: `/chat/*` redirect, chat-era `Perfs` defaults (`sendMessageKey`, `mdPreviewTheme`, `expandReasoningContent`, chat scroll keys…) in `src/stores/perfs.ts`, dead `TaskPanel`/`FileInputDialog`, md-editor CSS import, stale i18n keys ("Plans", "Guest", chat strings).
9. **Preview quality**: files render via raw iframe of presigned URL only after an explicit "Preview" click; notes preview is a `<pre>` dump, not rendered markdown (deps like `@vue-office/*`, katex, md-editor already in package.json but unwired).
10. **Admin/front inconsistency**: admin has its own drawer/header/table style and hard-coded English strings; if the redesign touches brand/theme, both apps diverge (admin is pinned to default hue).
11. **i18n hazard for redesign**: strings are English source keys in code (`t('...')`), so renaming UI copy changes translation keys — a bulk redesign should run `bunx i18n t` afterwards and expect stale-key cleanup.

## Caveats / Not found

- No `src-admin/` directory exists; task brief's "OAuth clients" admin page does not exist in code.
- I did not run the app; descriptions are from template/script reading. Visual screenshots not captured.
- Backend behavior (e.g., how trash gets populated without a UI trash action) not verified.
