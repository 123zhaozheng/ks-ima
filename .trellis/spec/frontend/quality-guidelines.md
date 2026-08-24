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
`bun test`, `bun run lint`, and the relevant Quasar build before handoff.

---

## Forbidden Patterns

<!-- Patterns that should never be used and why -->

Do not hand-edit generated OpenAPI files, duplicate API clients, or migrate
product state into Vue Query during the foundation phase.

---

## Required Patterns

<!-- Patterns that must always be used -->

Register shared query behavior in `src/boot/vue-query.ts`; keep API calls in the
generated client/composables and preserve existing product stores.

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
