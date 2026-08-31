# UX Audit Report — Nya AI Front (http://localhost:9015)

- **Date**: 2026-08-30 (continued session; screenshots 00–34 by prior agent, 35–44 by this session)
- **Scope**: front app only (`/`, `/kb`, `/history`, `/connectors`, `/workspace*`, `/trash`, `/settings`, `/account`, auth pages), desktop 1440×900-ish and mobile 390×844 (CDP emulation)
- **Accounts used**: `e2e-platform@example.com` (super admin, no workspace selected), `e2e-oauth-chromium@example.com` (member of "OAuth Workspace (chromium)"), and a brand-new self-serve account `audit-new-7k2m@example.com` created during this session via `/auth/sign-up`
- **Method**: real Chrome driven via agent-browser-cli; screenshots in `audit-shots/`; live re-probes of KB write flows with network capture
- **Environment notes** (important for reproducing):
  - At session start the Python API on :8000 was **down** (front on :9015 up). Restarted with `IMA_DATABASE_URL=postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app` etc. On Windows the API only boots when the asyncio policy is forced to `WindowsSelectorEventLoopPolicy` (plain `uvicorn ima.main:app` dies with `psycopg_pool.PoolTimeout` / ProactorEventLoop warnings). Dev-experience trap worth fixing.
  - Self-serve registration is gated by `ima.system_settings.allow_registration` (DB row). The row was absent; signup answered `404 "Registration is not available"` while the signup page itself stayed fully visible. The row was inserted to perform the first-run audit.
  - Green/white floating widgets at the right edge of many screenshots belong to the browser-extension used for automation, **not** to the app. Do not fix.

---

## 1. Per-screen findings

Paths are relative to this directory (`research/`).

| # | Screen | Shots | Observed bugs | UX complaints |
|---|--------|-------|---------------|---------------|
| 1 | Home / Ask, super admin, no workspace | `01-home-before-rail-1440.png`, `03-home-super.png`, `13-ask-home-super-nows.png` | Rail header shows orange "未选择工作区" yet the composer offers scope "整个工作区" and submitting only yields a toast (see #3). Rail exposes the whole "工作区管理" section (概览/标签/模型/回收站) with no workspace selected. | Page is a bare centered form floating in whitespace: no header/toolbar, no large-title, no visual anchor. Suggestion chips promise capabilities the backend cannot deliver. |
| 2 | Ask submit, no workspace | `14-ask-submit-super.png`, `14b-ask-after-submit.png` | Submit → orange toast "未选择工作区"; nothing else happens. Scope dropdown contains a single fake option "整个工作区 ✓" and zero real workspaces. | Composer lets the user author and send a question that is guaranteed to fail; scope picker should block or guide, not pretend. |
| 3 | Ask submit, workspace selected | `21-ask-submit-workspace.png`, `22-ask-error-toast.png` | Submit → red toast **"Grounded Ask is unavailable"** (English string in a zh-CN UI). The product's core function fails even in the fully-configured state. | No inline explanation, no retry affordance, no link to workspace capabilities; answer area never renders. |
| 4 | KB, no workspace | `04-kb-super.png`, `04b-kb-super-settled.png`, `37-firstrun-kb-deadend.png` | Dead-end icon + "未选择工作区 / 平台管理员必须为您分配一个工作区。" — no CTA. Copy is wrong for self-serve users (and absurd when the logged-in user *is* the platform admin). | Empty state violates the project's own Apple spec (§6: icon + title + subtitle + **one CTA**). No "创建/加入工作区" action anywhere on this screen. |
| 5 | KB, with workspace | `15-kb-with-workspace.png`, `18-kb-new-note-attempt.png` | Three panes; middle list shows "没有项目"; right pane permanent dead space "选择一篇文档以预览". | No guidance to create content in an empty KB; toolbar buttons (新建笔记/上传) exist but both are broken (see #6/#7). Tag filter dropdown on an empty list is noise. |
| 6 | KB create-folder | `16-kb-new-folder-dialog.png`, `17-kb-folder-created.png`, `18` | Dialog ("新建文件夹" + 创建) works visually, but the created folder ("Audit Folder") never appears in the folder pane in subsequent shots (18, and live re-check). | Same broken folder-id plumbing as #7 likely; silent failure — no error toast observed, folder just absent. |
| 7 | KB create-note | `19-kb-upload-attempt.png`, `44-kb-note-create-folder-not-found.png` | **Broken (live-verified)**: 创建 → warning toast **"Folder not found"** (English), dialog stays open, nothing created. | Error is a raw backend string, wrong language, no recovery hint. |
| 8 | KB upload | `19`, `20-kb-note-create-attempt.png`, `44` | **Broken (live-verified)**: file row shows red **"Document not found"**. Network capture: `POST /api/v1/folders/e2e-oauth-chromium-ws/files/upload-ticket` → 404 `{"code":"DOCUMENT_NOT_FOUND"}` — the **workspace id is sent where a folder id is expected**. | Upload dialog keeps the failed row with only "关闭"; no retry; English error in zh UI. |
| 9 | KB modal stacking | `19-kb-upload-attempt.png` | 上传 dialog and 新建笔记 dialog can be open **simultaneously**, stacked translucent-on-translucent (title "上传文件" ghosting behind "新建笔记"). | Opening a second modal should close or disable the first; the叠影 looks broken. |
| 10 | History | `05-history-super.png`, `23-history-workspace.png` | Left list empty state ("暂无对话 / 你发起的对话将显示在这里。") is acceptable copy but has **no CTA**; right 2/3 of the viewport is a permanent blank pane. | Dead space; empty state should offer "去提问" action per spec §6. |
| 11 | Connectors | `06-connectors-super.png`, `24-connectors-workspace.png`, `25-connectors-copy-toast.png`, `26/27-sp-create(d).png` | Copy works (toast), service-principal create flow completes with one-time secret. | Densest page in the app; bands read as utilitarian; but functionally the healthiest surface audited. |
| 12 | Workspace admin (overview/members) | `28-workspace-overview-member.png`, `29/29b-add-member` | Add-member dialog functional. | Dialogs are default Quasar prompts — boxed, 4px radii, hard shadow; far from spec §4 (12–18px radii, whisper shadows). |
| 13 | Workspace tags / models / trash | `08`, `30`, `09`, `31-workspace-models-member.png` (8 KB, blank), `31b`, `10`, `32` | `31` initial paint is a blank white pane before content settles (`31b`). | No skeleton/loading state; models page is read-only with no explanation of who can change anything. |
| 14 | Settings / Account | `11-settings-super.png`, `12-account-super.png` | Functional. | Sparse single card in an ocean of gray; "这台设备" card uses boxed border instead of ground-alternation (spec §3). |
| 15 | Sign-up page | `33-signup-page.png`, `34-after-signup.png` | Auth pages render inside the app shell with an **empty leftover rail column** ("登录/注册" only). Card is shoved to the left third, not centered in the remaining space. Validation errors from a failed submit persist stale ("名称至少 2 个字符" shown while a 15-char name is present). Raw failure strings: "注册失败：Request failed", "注册失败：Registration is not available". | No brand/hero, no value proposition, no password-requirement hint before submit, no success delight. |
| 16 | Post-signup | `35-after-signup-redirect-to-signin.png` | New account is **not signed in** after registration; bounced to `/auth/sign-in` with "账户已创建，现在可以登录了。" and must re-type credentials immediately after typing them. | Friction a big-company product never ships (auto-session or magic continue button). |
| 17 | First-run home (brand-new user) | `36-firstrun-home.png` | **No rail at all, no hamburger, no header** — nav links exist in DOM but the drawer is parked off-screen with no visible opener. User cannot reach KB/History/Settings/Sign-out except by typing URLs. Composer sits left-shifted against a huge empty right half. | Complete dead end; the only screen a new user sees offers a question box that fails with a toast (see #2). |
| 18 | First-run rail (opened from /kb) | `38-firstrun-rail-open.png` | Rail shows "未选择工作区" plus the full "工作区管理" section (概览/标签/模型/回收站) to a user with **zero** workspaces — every item is a dead link (`/workspace` = blank page, see #21). | No "创建工作区" entry; no onboarding section; nav promises admin powers the user cannot exercise. |
| 19 | Workspace switcher menu (first-run) | `39-firstrun-workspace-switcher.png`, `39b-firstrun-create-workspace.png` | Menu card is clipped to ~124 px; the "加入工作区" item renders **half-invisible outside the menu card** (ghost text over the rail). The round "+" button is icon-only, unlabeled, and **dead** (click → nothing, verified twice). | The two most important actions in the product (create / join) are respectively invisible and non-functional. |
| 20 | Join-workspace dialog | `39c-firstrun-join-dialog.png` | Works: 邀请链接 input + 确定. | Only path into the product is knowing someone with an invite link; dialog is a bare default Quasar card. |
| 21 | `/workspace` as no-workspace user | `39d-firstrun-workspace-blank.png` | **Pure white blank page** — no message, no header, no rail opener. | Worst dead end in the audit; a route listed in the rail must never render nothing. |
| 22 | Mobile 390×844 home | `40-mobile-home.png` | No header/hamburger → **zero navigation** on the landing screen (new user). Composer and chips do fit width correctly. | Mobile is un-designed, not responsive: pages that rely on the desktop auto-open rail are stranded. |
| 23 | Mobile KB | `41-mobile-kb.png` | Hamburger present; dead-end message fits. | Acceptable skeleton, but the dead end is the same as desktop (#4). |
| 24 | Mobile rail open/close | `42-mobile-rail-open.png`, `43-mobile-rail-closed.png` | Drawer overlay opens/closes correctly over scrim. | Drawer is the only nav; on `/` it cannot be opened at all (see #17/#22). |

---

## 2. Prioritized bug list

### P0 — broken flows / dead ends

1. **KB upload is broken**: `POST /api/v1/folders/{workspaceId}/files/upload-ticket` 404 `DOCUMENT_NOT_FOUND` — front passes the *workspace id* as *folder id* (`20`, `44`, network capture `correlationId c7c6c494-…`).
2. **KB note creation is broken**: 创建 → toast "Folder not found", dialog left open, nothing created (`44`, live-verified).
3. **KB folder creation never lands**: created folder absent from the folder pane afterwards (`17`→`18`, live re-check) — same folder-id plumbing suspect.
4. **Grounded Ask fails even with a configured workspace**: red toast "Grounded Ask is unavailable" (`22`). The hero feature of the home page cannot succeed.
5. **Ask composer allows guaranteed-fail submits** with no workspace (toast-only failure, `14b`) and offers a fake "整个工作区" scope when zero workspaces exist.
6. **First-run dead end**: brand-new user lands on a home with **no navigation at all** (`36`); the only create-workspace control ("+") is dead (`39b`); "加入工作区" renders half-invisible (`39`); `/workspace` is a blank white page (`39d`). A self-serve user can never reach value without an external invite link.
7. **Signup page exposed while registration is disabled** (DB flag): user fills the whole form and gets "注册失败：Registration is not available"; when the API is down the page shows raw "注册失败：Request failed" (`34`, `35`).

### P1 — missing / confusing UX

8. Home page has **no header, no hamburger, no rail** whenever the drawer isn't auto-open (new users on desktop, everyone on mobile) — `36`, `40`.
9. Rail shows the full "工作区管理" section to users with no workspace; every entry dead-ends (`38`, `39d`).
10. Workspace switcher menu clipped to 124 px with ghosted overflow item; "+" unlabeled (`39`).
11. No auto sign-in after signup; immediate re-authentication required (`35`).
12. i18n inconsistency: English backend strings surfaced raw in zh-CN UI — "Grounded Ask is unavailable", "Folder not found", "Document not found", "Registration is not available".
13. Stale/incorrect client validation on signup (errors persist after valid input) (`34` vs live run).
14. Two modals can stack at once on KB (`19`).
15. Empty states lack the spec-mandated single CTA (KB `04b`, History `05`); KB preview pane is permanent dead space.
16. `/workspace/models` first paint is blank with no skeleton (`31` vs `31b`).
17. Auth pages render a leftover empty rail column and a left-jammed card (`33`).

### P2 — visual polish (vs `apple-design-language.md`)

18. Type: bold-700 centered "Nya AI" title instead of 600 semibold left large-title with −0.022em tracking; body text 12–14 px instead of 17/1.47 (`03`, `36`).
19. Shape/depth: 4–8 px radii and boxed bordered cards everywhere (`11`, `16`, `39c`) vs spec 12–18 px radii, hairlines, ground-alternation; dialogs carry hard shadows.
20. Color discipline: saturated default blue + orange warning text in rail header + red/orange toasts of differing styles; spec demands one restrained `#0071e3` accent and HIG semantic colors (`03`, `14b`, `22`).
21. Lists/rows denser than spec (36–40 px vs 44–56 px), hover/selected states use flat blue tints instead of subtle fills (`38`).
22. No frosted header/large-title toolbar pattern; pages separate by gray voids rather than whitespace rhythm (`05`, `11`).
23. Motion: default Quasar snaps; no 200–300 ms decelerate curves, no press feedback language.
24. Signup/account surfaces lack any brand moment — feels like an internal demo, not a product.

---

## 3. First-run narrative (brand-new user)

1. User finds the signup URL, fills four fields, presses 注册. If the deployment left `allow_registration` off (the default), the reward is "注册失败：Registration is not available" — a full-form dead end with no explanation of *why* or *who can fix it*.
2. With registration on, the account is created and the user is immediately bounced to the sign-in page to re-type the credentials they just typed (`35`).
3. After login they land on Home: a question box floating in a half-empty viewport, **no sidebar, no menu, no logo bar, no settings, no sign-out** (`36`). The product's only visible affordance is a question they have no knowledge base to ask.
4. Submitting a question produces an orange toast "未选择工作区" (`14b`).
5. If they guess `/kb`, the screen says "平台管理员必须为您分配一个工作区" — instructing them to wait for an admin who, in a self-serve deployment, will never come (`37`). No button offers to create or join anything.
6. The curious user finds the hamburger on /kb, opens the rail, and sees "工作区管理" entries that all lead to blank pages (`38`, `39d`).
7. The workspace switcher hides the two lifelines: an invisible "加入工作区" ghost and a dead "+" (`39`, `39b`). Joining requires pasting an invite link nobody sent them.
8. On a phone it is worse: Home has no hamburger at all (`40`); the app is a cul-de-sac with one broken question box.

The story is: **the product assumes every user arrives pre-provisioned by an admin, and punishes everyone else with silent dead ends.** There is no onboarding, no create-workspace flow, no "invite your team", no sample workspace, no demo content.

## 4. Verdict — does this feel like a big-company product?

**No.** Functionally it is below the bar of a shipped commercial tool: two of three KB write flows 404, the flagship Ask fails in its happy path, and a self-serve account is a dead end within 60 seconds. Visually it is a competent Quasar/Material admin demo — uniform gray grounds, boxed cards, default dialogs — which is exactly the "flat and slightly saturated" baseline `apple-design-language.md` was commissioned to replace. Concretely against that spec: no large-title toolbars, no whitespace-first separation, no pill CTAs, no 17 px reading type, no semibold-with-tight-tracking headings, no whisper shadows, no frosted surfaces, empty states without CTAs, three different toast/error styles, mixed EN/CN system messages, and mobile that was never designed. Connectors (the one flow that works end-to-end) hints at real product thinking; almost nothing else does. The distance to "高端大气" is not a token swap — it is fixing the seven P0 flow breaks first, then an onboarding/first-run story, then the visual grammar.
