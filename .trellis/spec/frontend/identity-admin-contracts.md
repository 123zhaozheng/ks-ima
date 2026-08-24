# Identity And Administration Frontend Contracts

## 1. Scope / Trigger

Apply this specification to Vue authentication, account security, admin users,
workspace registry, audit/settings screens, route guards, generated identity
types, and identity Playwright/component tests.

## 2. Signatures

```text
src/utils/identity-client.ts       # one cookie/CSRF transport and session ref
src/api/generated/schema.ts        # generator-owned DTO source
src/pages/AccountSecurity.vue      # profile, TOTP, recovery, sessions
src/admin/pages/UsersPage.vue      # user/security/role lifecycle
src/admin/pages/WorkspacesPage.vue # role-aware registry lifecycle
src/admin/pages/AuditPage.vue      # typed read-only audit data
src/components/AcceptInviteForm.vue

bun run generate:api
bun run test:unit
bun run test:e2e
```

## 3. Contracts

- Identity/admin payloads come from generated `components['schemas']`. Do not
  recreate Better Auth-shaped clients, `LooseInput`, or auth
  `Record<string,unknown>` DTOs.
- Cookies remain HttpOnly; CSRF comes from the readable cookie and is added only
  by the central client to unsafe requests. Tokens are never persisted in local
  or session storage.
- Successful password/TOTP/recovery authentication refreshes the central
  session ref. Route guards watch both pending state and identity, because
  `undefined -> undefined` user IDs do not trigger a user-ID-only watcher.
- The admin SPA is capability-aware: auditors see workspace/audit read views and
  Sign Out, but no user/workspace/settings mutation controls. Only super admins
  see role actions. API authorization remains authoritative.
- Account security exposes current/other/all session revocation, TOTP
  enrollment/confirmation/disablement, and one-time recovery display/download,
  with loading/empty/error/expired/recent-auth states.
- Front and admin builds share Quasar generation state and must not run dev/build
  concurrently. E2E builds sequentially, then serves `dist/pwa` and `dist/spa`
  through independent static API proxies.

## 4. Validation & Error Matrix

| Condition | Required UI/result |
|---|---|
| Session pending | Stable loading state; no premature redirect |
| Session absent/expired | Sign-in redirect or explicit expired account state |
| `totp_required` 200 response | Open verification dialog; do not treat as login |
| Recovery code reused | First succeeds; second 401 and visible failure |
| Registration closed | Signup surface may render; API 404 handled clearly |
| SMTP disabled | Explicit unavailable reset/invite state |
| Auditor opens admin | Audit/workspaces read-only; settings/mutations hidden |
| Generated API error | Typed message; no internal response/secret logging |
| Invalid invite | Safe error; token never rendered/logged after submission |

## 5. Good / Base / Bad Cases

- Good: TOTP/recovery verification refreshes session and closes the challenge.
- Good: auditor sees workspace rows but no create/archive/restore/delete actions.
- Base: empty users/workspaces/sessions render stable empty states.
- Bad: rename a Better Auth facade to `identity-client` without changing types.
- Bad: start front/admin Quasar dev servers concurrently in one worktree; the
  shared `.quasar` directory can swap applications nondeterministically.
- Bad: use Bun test to import `.vue`; Bun returns the path string, not a compiled
  SFC. Use Vitest + Vue plugin + happy-dom.

## 6. Tests Required

1. Bun tests for typed client CSRF/error behavior and Bun bridge behavior.
2. Vitest mounts real SFCs and asserts concrete rows, errors, role controls, and
   session/TOTP actions; `wrapper.exists()` alone is insufficient.
3. Playwright global setup creates a test-only database/seed, runs Python with
   `PYTHONWARNINGS=error`, builds both SPAs sequentially, serves real API
   proxies, and tears down processes/container/network/volume.
4. Browser journeys cover closed registration, invite, SMTP unavailable,
   ordinary account security, super/platform/auditor roles, disabled/expired
   sessions, TOTP, and recovery single use with zero skips.
5. Lint, `vue-tsc`, PWA/Admin/Server builds, OpenAPI/Zero regeneration, and drift
   checks pass after component changes.

## 7. Wrong vs Correct

### Wrong

```ts
type LooseInput = Record<string, unknown>
authClient.signIn.email(input)
```

### Correct

```ts
type SignInRequest = components['schemas']['SignInRequest']
const result = await identityClient.signIn(input satisfies SignInRequest)
if (result.data?.status === 'totp_required') openTotp(result.data.challenge)
```

