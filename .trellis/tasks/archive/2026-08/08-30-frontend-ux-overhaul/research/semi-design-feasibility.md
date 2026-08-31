# Research: Semi Design feasibility for Vue 3 + Quasar frontend (Chrome 109 hard requirement)

- **Query**: Can Semi Design (semi.design) be used for the nyaai frontend UX overhaul, given a hard requirement to support Chrome 109? Covers browser compat, Vue port maturity, Vite build-target angle, verdict matrix, and the mcp-skills page.
- **Scope**: external (web/npm/GitHub research) + internal stack check (`package.json`)
- **Date**: 2026-08-30 (all URLs fetched / commands run this day)

## Summary

**Do not adopt Semi Design as a component library for this project.** Semi is a **React-only** design system whose official browser policy is "latest 2 versions" of Chrome/Firefox/Safari/Electron — Chrome 109 (early 2023) is far outside that window and is not a supported target. There is **no official Vue port**; the only substantial community port (`@kousum/semi-ui-vue`, 199★) is ~16 months behind upstream (2.78.4 vs 2.102.0), effectively single-maintainer, and would still inherit the same unguaranteed old-Chromium situation. A second port (`@transsionfe/semi-ui-vue`) is a 2-week burst of 0.x releases in Jan 2026, then silent. The `mcp-skills` URL the user provided is documentation for Semi's **official MCP server + AI Skills for building React UIs** — it reinforces that Semi is a React-first ecosystem, not a bridge to Vue.

Empirically, current Semi CSS is *mostly* parseable by Chrome 109 (no `color-mix`, `oklch`, container queries, nesting, or `@layer` in the shipped CSS; only 3 uses of `:has()`, which Chrome 109 supports). One real defect found: **unprefixed `background-clip:text`** (needs `-webkit-` prefix before Chrome 120). But this is incidental, not contractual — Semi does not test or guarantee old browsers.

**Recommendation: keep Vue 3 + Quasar and borrow Semi's visual language (design tokens, radius, spacing, typography, dark-mode palette) as a custom theme**, and explicitly pin `build.target` to `chrome109` (Vite's current default `baseline-widely-available` = chrome111 already excludes Chrome 109).

## Chrome 109 compatibility

### Official policy

- Semi README "Platform Support": "Semi UI supports all major modern browsers" — table lists Chrome / Firefox / Safari / Electron at **"latest 2 versions"**, IE/Edge column = "Edge" (i.e., legacy IE dropped). Source: `README.md` of `DouyinFE/semi-design`, fetched 2026-08-30.
- DeepWiki analysis of the repo confirms: **no `.browserslistrc` / `browserslist` config exists**; the stance is documented-only ("latest 2 versions"), and dark mode/theming depends on CSS variables (no IE11). Source: https://deepwiki.com/search/what-browsers-does-semi-design_c9eae847-b574-467e-9b99-c7067048f9d2 (2026-08-30).
- As of 2026-08, "latest 2 versions" of Chrome is roughly Chrome 140±. **Chrome 109 is ~31 major versions outside the support window.** No compatibility guarantee, and Semi can ship breaking-for-old-browser code at any release without it being considered a bug.
- Semi is actively maintained: `@douyinfe/semi-ui` latest 2.102.0 published 2026-07-31, 2.101.1 on 2026-07-20 (npm registry), ~31k weekly downloads (npmjs.com package page).

### Empirical audit of shipped CSS (`@douyinfe/semi-ui@2.102.0`, `dist/css/semi.min.css`, 682 KB, via unpkg, 2026-08-30)

| Feature | Chrome support | Occurrences in Semi CSS | Risk on Chrome 109 |
|---|---|---|---|
| `color-mix()` | 111+ | **0** | none |
| `oklch()` / `lab()` / `lch()` | 111+ | **0** | none |
| `@container` | 105+ | **0** | none (and 109 would support it anyway) |
| Native CSS nesting | 112+ | **0** (SCSS fully expanded) | none |
| `@layer` | 99+ | **0** | none |
| `@property` | 85+ | **0** | none |
| `dvh`/`svh` units | 108+ | **0** | none |
| `:has()` | 105+ | **3** (all `:not(:has(> .semi-button-content-right))` for AI-gradient buttons) | none — supported on 109 |
| `position: sticky` | 56+ | 7 | none |
| `background-clip: text` **unprefixed** | **120+ unprefixed; `-webkit-` prefix works everywhere** | **5 occurrences, 0 with `-webkit-` prefix** | **BREAKS on 109**: gradient text in AI "colorful" Button variants degrades (background renders as block behind transparent text) |

- JS: distributed as Babel-compiled ESM (`lib/es`) + CJS; no ES2023+ builtins spotted in sampling; Chrome 109 implements full ES2022, so JS syntax is low-risk today — but again, unguaranteed going forward since Semi targets latest-2-versions.
- Tailwind-integration path uses `@layer` (Chromium 99+) per repo docs — fine on 109, but only relevant if using that integration.

**Verdict on (1): Chrome 109 is not officially supported. Current artifacts happen to mostly work, with at least one known visual defect (`background-clip:text`), and zero future guarantee.**

## Vue port maturity

There is **no official Vue implementation**, and DeepWiki confirms the repo has no `packages/semi-ui-vue` and no plans for non-React implementations. Semi's FA (Foundation-Adapter) architecture (`@douyinfe/semi-foundation` holds logic; UI layer is thin) is explicitly designed to make ports possible, and community ports exploit this.

| Port | Repo / npm | Stars | Last npm release | Version vs official (2.102.0) | Assessment |
|---|---|---|---|---|---|
| **@kousum/semi-ui-vue** | https://github.com/rashagu/semi-design-vue | 199★ / 16 forks / 11 open issues (2026-08-30) | 2.78.4 on **2025-04-14** | **~24 minor versions / 16 months behind** | Only substantial port. Built on official `@douyinfe/semi-foundation`, `semi-theme-default`, `semi-animation`. Vue ≥ 3.3.4 peer dep. ~70 component dirs incl. newer "Plus"/AI ones (`chat`, `markdownRender`, `codeHighlight`, `hotKeys`, `audioPlayer`, `jsonViewer`, `lottie`…). Repo last push 2026-02-16 but no npm release since Apr 2025. Single primary maintainer. TODO list still says "bug fix & unit test coverage" and missing Vue docs. |
| **@transsionfe/semi-ui-vue** | https://github.com/fx1422/semi-ui-vue (repo created 2026-01-23, 5★) | 5★ | 0.1.0 on **2026-01-29** | claims parity direction, 0.x maturity | 11 versions all published 2026-01-13 → 2026-01-29, then silence for 7 months. Too young to bet on. |
| `semi-design-vue` (npm name) | n/a | — | 0.0.0 on 2024-07-04 | placeholder | Empty parked package (275 bytes). Ignore. |
| Other forks (`angularning/vue-semi-design`, `just5even/semi-design-vue2`, etc.) | GitHub search, 2026-08-30 | ≤2★ | dead since 2021–2023 | — | Ignore. |

**Risks of adopting @kousum/semi-ui-vue:**
- Frozen at Semi 2.78 features: misses everything since (incl. new AI components like `AIChatInput`, `AIChatDialogue`, `Sidebar`, and any Chrome-compat or a11y fixes upstream).
- Bus factor 1; no SLA; 11 open issues; its own version scheme invites confusion with official Semi versions.
- Inherits Semi's own CSS, so the `background-clip:text` Chrome-109 defect applies too.
- Semi's MCP/AI tooling, Design-to-Code, and theme store (DSM) are React-oriented and won't serve a Vue port.

## Vite / build-target notes

Facts from https://vite.dev/config/build-options (fetched 2026-08-30, current Vite major):

- `build.target` default is now `'baseline-widely-available'` = **`['chrome111', 'edge111', 'firefox114', 'safari16.4', 'ios16.4']`** — i.e. **Vite's default output already excludes Chrome 109**. You MUST set `build.target: ['chrome109']` (or `'es2020'`-ish) explicitly; Oxc/esbuild will then down-level JS syntax. Transform is performed on the final bundle (including dependencies), so Semi/kousum JS syntax would be down-leveled automatically.
- `build.cssTarget` defaults to the same as `build.target`. CSS minification/transformation uses **Lightning CSS by default** (`build.cssMinify: 'lightningcss'`); Lightning CSS downgrades CSS *syntax* (e.g., native nesting → flat) to the target, but does **not** polyfill capabilities like `color-mix()` — irrelevant for Semi today since it ships none.
- Dependency CSS ships precompiled; it still passes through Vite's CSS pipeline (cssTarget + minifier), so parseability on chrome109 is preserved, but pre-existing unprefixed properties (`background-clip:text`) need a manual override/patch (e.g., a small global CSS adding `-webkit-background-clip: text; background-clip: text;` on the relevant `.semi-*` classes) or a PostCSS prefixing step with a `chrome 109` browserslist.
- Runtime APIs (e.g., `Array.toSorted`, ES2023) are NOT polyfilled by build targets — if any dep starts using them, add core-js polyfills.
- **Current project wiring** (`quasar ^2.16.0`, `@quasar/app-vite ^2.4.0`, per `D:\code\python\nyaai\package.json`): Quasar CLI (Vite) exposes `build.target.browser` in `quasar.config` (mapped to Vite's `build.target`), and Quasar's default is likewise `'baseline-widely-available'` now. Set `build: { target: { browser: ['chrome109'] } }` (docs example shows `['es2022','firefox115','chrome115','safari14']` style values) and keep a `browserslist` entry (`chrome 109`) so autoprefixer prefixes accordingly. See Quasar "Browser compatibility" page. Note the existing `baseline-browser-mapping` devDep in the project is already related to target mapping.

## Verdict matrix

| Option | What it means | Chrome 109 | Risk | Effort |
|---|---|---|---|---|
| **(a) Official Semi (React)** | Requires **rewriting the whole frontend in React**. The current stack is Vue 3 + Quasar + Pinia + vue-router + @tanstack/vue-query + i18n-pro + md-editor-v3 + @vue-office/* + UnoCSS + PWA/Workbox + Playwright e2e — every one of those is Vue-specific and needs a React replacement (react-router, zustand/redux, @tanstack/react-query, i18next, etc.), plus rewriting all SFCs to JSX and redoing e2e. Semi itself is excellent and actively maintained, but even then Chrome 109 remains *unsupported-but-incidentally-working*. | incidental only | Very high (new framework for the team + full rewrite) | Months; full project re-platform |
| **(b) `@kousum/semi-ui-vue` community port** | Drop-in-ish Vue 3 components sharing official Semi foundation/theme. But: frozen at Semi 2.78 (16 months stale), 1 maintainer, 199★, 11 open issues, no Vue docs, unknown a11y/i18n parity; future Semi features/AI components never arrive; inherits the `background-clip:text` 109 defect. | incidental only | High (adoption risk + vendor lock-in to a fork) | Medium now, high ongoing |
| **(c) Keep Quasar + adopt Semi visual language as theme** ✅ | Map Semi design tokens (3000+ documented CSS variables `--semi-color-*`, radii, spacing, typography, dark mode) onto Quasar Sass variables / UnoCSS theme / custom SCSS. Semi's tokens & DSM theme editor serve as the design reference. Keep all existing infrastructure, Chrome 109 stays in the test matrix under our own control. | full control (we own the target) | Low | Medium, bounded, incremental |
| (d) Semi Web Components (fallback considered) | Docs advertise a shadow-DOM "web components adapter", but **no npm package exists** (`@douyinfe/semi-web-components` → 404). Nothing shippable. | — | — | n/a |

## What the mcp-skills page is

https://semi.design/zh-CN/start/mcp-skills is Semi's official **"AI Agent MCP/Skills"** documentation page:

- **Semi MCP**: official MCP server, npm package **`@douyinfe/semi-mcp`** (`npm i -g @douyinfe/semi-mcp`; ByteDance intranet variant `@ies/semi-mcp-bytedance`). Tools exposed to AI clients: `get_semi_document`, `get_semi_code_block`, `get_component_file_list`, `get_file_code`, `get_function_code`. Knowledge base is versioned, stable since Semi 2.90.2; recommended env Node ≥ 20.19.0, npm ≥ 11.3.0.
- **Semi Skills**: preconfigured AI skill packs (markdown knowledge files such as `WORKFLOWS.md`, `BEST_PRACTICES.md`) teaching AI assistants correct Semi component usage, theming, extension patterns, React 19 notes.
- Supported clients: Claude Desktop, Claude Code, Cursor, Trae, CodeBuddy, Qwen Code, OpenAI Codex CLI.
- **Implication for us**: this is Semi investing in AI-assisted **React** development. It gives no Vue support; it is only a reason to choose Semi *if* we were going React. Not relevant to a Quasar/Vue app, except as a signal of Semi's ecosystem direction.

## Recommendation

1. **Adopt option (c)**: keep Vue 3 + Quasar; run the UX overhaul by porting Semi's visual language as a theme — extract Semi token values (colors, font stack, border radius, spacing scale, shadows, dark-mode palette) from `@douyinfe/semi-theme-default` / semi.design Tokens page and implement them via Quasar Sass variables + UnoCSS theme + targeted SCSS overrides. This keeps Chrome 109 fully under our control with zero dependency risk.
2. **Regardless of UI library choice**, pin browser targets now: `quasar.config` → `build.target.browser: ['chrome109']` (+ `cssTarget` if customizing), `.browserslistrc` with `chrome 109`, because Vite/Quasar defaults (`baseline-widely-available` = chrome111) already exclude Chrome 109.
3. If a Semi look is wanted for specific hero components only, prefer hand-rolling them with Quasar primitives rather than pulling in a stale Vue port.
4. Re-evaluate Semi only if the team ever decides to migrate to React; in that case official Semi + its MCP/Skills tooling is a strong choice (but still requires an explicit chrome109 workaround strategy and testing, since it's outside Semi's support window).

## Sources

- Semi repo README, Platform Support table — https://github.com/DouyinFE/semi-design (raw `README.md` fetched 2026-08-30)
- DeepWiki: browser support / browserslist / CSS features in semi-design — https://deepwiki.com/search/what-browsers-does-semi-design_c9eae847-b574-467e-9b99-c7067048f9d2 (queried 2026-08-30)
- DeepWiki: MCP package name, Skills files, clients, no-Vue-plans — https://deepwiki.com/search/regarding-the-ai-agent-mcp-ski_f1147494-d324-4e2b-86af-784aad04540d (queried 2026-08-30)
- Semi MCP/Skills doc page — https://semi.design/zh-CN/start/mcp-skills (content fetched 2026-08-30)
- Semi intro page — https://semi.design/en-US/start/introduction (fetched 2026-08-30)
- npm `@douyinfe/semi-ui` registry metadata (2.102.0, 2026-07-31) — https://registry.npmjs.org/@douyinfe%2Fsemi-ui (queried 2026-08-30); package page https://www.npmjs.com/package/@douyinfe/semi-ui
- CSS audit artifact: `https://unpkg.com/@douyinfe/semi-ui@2.102.0/dist/css/semi.min.css` (downloaded & grepped 2026-08-30)
- npm `@kousum/semi-ui-vue` release timeline (2.78.4 @ 2025-04-14) — https://registry.npmjs.org/@kousum%2Fsemi-ui-vue (queried 2026-08-30)
- kousum port repo (199★, pushed 2026-02-16, components listing) — https://github.com/rashagu/semi-design-vue (GitHub API, 2026-08-30)
- npm `@transsionfe/semi-ui-vue` timeline (0.0.1–0.1.0, 2026-01-13 → 2026-01-29) and repo — https://github.com/fx1422/semi-ui-vue (npm CLI + GitHub API, 2026-08-30)
- Parked npm name `semi-design-vue` — https://registry.npmjs.org/semi-design-vue (queried 2026-08-30)
- Vite build options (build.target default chrome111; cssTarget; Lightning CSS minify) — https://vite.dev/config/build-options (fetched 2026-08-30)
- Quasar config `build.target.browser` & defaults — https://quasar.dev/quasar-cli-vite/quasar-config-file and https://quasar.dev/quasar-cli-vite/browser-compatibility (search results fetched 2026-08-30)
- Browser feature support versions (`:has()` 105, nesting 112, `color-mix` 111, unprefixed `background-clip:text` 120) — MDN/CaniUse knowledge, not re-fetched 2026-08-30

## Caveats / Not Found

- No automated render testing on an actual Chrome 109 binary was performed; CSS findings are static-analysis of the shipped minified CSS.
- `:has()`/`background-clip:text` Chrome version thresholds come from remembered MDN/CaniUse data (2023 releases); worth a one-minute caniuse confirmation before the decision meeting.
- kousum component coverage was counted from repo `src/components` directory listing (~70 dirs); per-component API parity vs Semi 2.78 was not verified.
- Could not retrieve Semi FAQ page content (SPA, extraction returned homepage shell); README platform-support table is used as the authoritative statement instead.
- Weekly download figures for the Vue ports were not retrieved (low signal given release cadence).
