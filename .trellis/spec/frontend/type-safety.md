# Type Safety

> Type safety patterns in this project.

---

## Overview

<!--
Document your project's type safety conventions here.

Questions to answer:
- What type system do you use?
- How are types organized?
- What validation library do you use?
- How do you handle type inference?
-->

Frontend DTO types are generated from the checked backend OpenAPI document.
The handwritten `src/api/ima-client.ts` adapter is the only typed runtime client
for this foundation proof; it remains outside the generated tree so normal
source linting covers its error handling and fetch behavior.

---

## Type Organization

<!-- Where types are defined, shared types vs local types -->

Keep generated DTOs under `src/api/generated/`; expose domain-specific query
composables such as `useSystemInfo` from `src/composables/`.

---

## Validation

<!-- Runtime validation patterns (Zod, Yup, io-ts, etc.) -->

OpenAPI generation and drift checks provide compile-time contract safety, not
runtime validation of untrusted JSON. Use the central client for HTTP failures
and add a shared runtime decoder when a boundary requires validation; do not
duplicate backend schemas or cast payloads independently in components.

---

## Common Patterns

<!-- Type utilities, generics, type guards -->

Use Vue Query signal cancellation and typed client return values. Keep generated
files immutable and avoid broad `any` or unchecked response transformations.

---

## Forbidden Patterns

<!-- any, type assertions, etc. -->

Do not hand-edit generated schema output, cast API payloads to unrelated domain
types, or introduce a second client with overlapping endpoints.
