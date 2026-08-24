# OpenAPI Client Contracts

## 1. Scope / Trigger

Apply this specification whenever a Python API operation, OpenAPI schema,
generated TypeScript type, handwritten client, Vue Query composable, or Caddy
path used by Vue changes.

## 2. Signatures

```text
backend/scripts/export_openapi.py -> frontend/generated/openapi.json
bun run generate:api              -> src/api/generated/schema.ts
src/api/ima-client.ts             -> handwritten runtime transport
useSystemInfo()                    -> GET /api/v1/system/info query
```

Only `schema.ts` is generator-owned under `src/api/generated/`. Handwritten code
lives outside that directory and passes ESLint.

## 3. Contracts

- Backend operation IDs are explicit and stable.
- Checked OpenAPI JSON is deterministic; generated TS is never hand edited.
- Runtime DTOs come from generated `components`/`operations`; do not redefine
  `BuildInfo` or `ProblemDetails`.
- Vue Query owns cancellation, loading/error state, caching, and retry.
- Pinia/Zero keep legacy product state until their owning child migrates it.
- The admin status control renders loading, unavailable, and success and calls
  the real system-info endpoint.
- Type generation is compile-time safety, not runtime validation. Add one shared
  decoder when runtime validation is required; never scatter local casts.

## 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Backend OpenAPI differs from checked JSON | Contract check fails |
| Checked JSON differs from generated TS | Generated diff fails review/CI |
| Non-2xx Problem Details | `IMAApiError` carries generated problem shape |
| Request cancelled | Fetch receives Vue Query `AbortSignal` |
| Python API unavailable | Indicator shows unavailable; legacy UI remains usable |
| Generated style differs | Generated dir skips style-only lint but is type-checked |
| Handwritten client fails lint/type | ESLint/`vue-tsc` fail |

## 5. Good / Base / Bad Cases

- Good: change Pydantic DTO, export OpenAPI, regenerate schema, update one
  runtime client, and compile consumers.
- Base: Python is unavailable during coexistence; admin shows error without
  breaking Bun/Zero screens.
- Bad: put handwritten client code under generated/ so lint ignores it.
- Bad: declare another local `ProblemDetails` that drifts from OpenAPI.

## 6. Tests Required

1. Backend contract asserts path, operation ID, success, and problem responses.
2. OpenAPI export/check and TypeScript regeneration leave no diff.
3. ESLint checks all handwritten client/composable/component code.
4. `vue-tsc --noEmit`, Bun tests, PWA build, and admin build pass.
5. Caddy contract verifies exact Python routing and legacy fallback.

## 7. Wrong vs Correct

### Wrong

```typescript
const data = await fetch('/api/v1/system/info').then(r => r.json()) as {
  version: string
}
```

### Correct

```typescript
type BuildInfo = components['schemas']['BuildInfo']
const { data, isLoading, isError } = useSystemInfo()
```

One generated contract, one runtime adapter, and one query projection own the
boundary.

