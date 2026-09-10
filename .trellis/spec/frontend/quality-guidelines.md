# Quality Guidelines

> Code quality standards for frontend development.

---

## Overview

<!--
Document your project's quality standards here.

Questions to answer:
- What patterns are forbidden?
- What linting rules do you enforce?
- What are your testing requirements?
- What code review standards apply?
-->

The retained Vue 3/TypeScript frontend uses Quasar and TanStack Vue Query. Run
`bun test`, `bun run lint`, and the Quasar PWA build before handoff. The
release matrix is: `bun run lint` (0 errors/0 warnings), `bunx vue-tsc --noEmit`,
`bun test`, `bun run test:unit`, `bun run build`, `bun run test:e2e` (against
the isolated Postgres, default port override `IMA_E2E_POSTGRES_PORT`), and
`bun run test:caddy-routing`.

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

Do not hand-edit generated OpenAPI files, duplicate API clients, or migrate
product state into Vue Query during the foundation phase.

Chrome 109 is the hard build target (`build.target.browser: ['chrome109']` in
`quasar.config.ts`): never use `toSorted`/`toReversed`/`toSpliced`, CSS
nesting, `color-mix()`, `oklch()`, container queries, or unprefixed
`background-clip: text` in app code. Full policy in
[UX Design Language](./ux-design-language.md) §5.

---

## Required Patterns

<!-- Patterns that must always be used -->

Register shared query behavior in `src/boot/vue-query.ts`; keep API calls in the
generated client/composables and preserve existing product stores.

### Admin bundle isolation (single-app console)

The admin console lives at `/admin/*` in the **same** PWA, with lazy
`() => import('src/admin/...')` routes. Its JS/CSS must never reach end-user
first load or the service-worker precache. Enforced in `quasar.config.ts`:

- `build.extendViteConf` → `rollupOptions.output.chunkFileNames` and
  `assetFileNames` route admin-owned output to `assets/admin/[name]-[hash].*`.
- `pwa.extendGenerateSWOptions` → `cfg.globIgnores = ['**/assets/admin/**']`.

Three non-obvious traps (all previously shipped bugs):

1. **Match root-relative names too.** Vite passes `assetFileNames` names like
   `src/admin/pages/UsersPage.vue` (no leading slash). Use
   `/(^|[\\/])src[\\/]admin[\\/]/`, not `id.includes('/src/admin/')`.
2. **CSS is an asset, not a chunk.** Admin page stylesheets are emitted by
   `assetFileNames` (named after the chunk), so a `chunkFileNames`-only rule
   leaves `assets/UsersPage-*.css` in the precache. Route admin assets too.
3. **Shared vendor chunks need their own pattern.** A component used only by
   admin pages (e.g. `QTable`) is lifted by Rollup into a vendor-only chunk with
   no `/src/admin/` module id, so the path check misses it and it gets precached
   for everyone. Match the vendor path explicitly
   (`node_modules/quasar/src/components/(table|markup-table)/`).

Assertion point after `bun run build`: `dist/pwa/assets/admin/` exists; the
`sw.js` precache manifest and `index.html` contain **zero** `assets/admin`
entries.

---

## Testing Requirements

<!-- What level of testing is expected -->

Generated files are checked for OpenAPI drift; source code must pass ESLint and
the target Quasar build. Keep generated `src/api/generated/**` excluded from
style rules while still compiling it.

---

## Code Review Checklist

<!-- What reviewers should check -->

Verify browser-to-Caddy-to-FastAPI paths, query loading/error states, generated
client changes, and that legacy routes remain untouched.
