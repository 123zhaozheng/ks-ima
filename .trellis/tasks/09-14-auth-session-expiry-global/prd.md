# Session expiry auto sign-out across SSE, admin, and system paths

## Problem

Users report: pages left open for a long time never sign themselves out. The UI keeps
rendering as if authenticated while every API call returns 401.

Browser auth is an opaque server-side session cookie (`ima_session`), not a JWT:

- `backend/src/ima/application/identity.py:686-703` sets the cookie with **no**
  `max_age`/`expires`, so the browser keeps sending it after the server-side row expired.
- Expiry is enforced server-side only (`identity.py:705-752`), via
  `session_idle_seconds` (86400) and `session_absolute_seconds` (2592000)
  in `backend/src/ima/config.py:38-45`.
- There is **no** browser session refresh endpoint (`backend/src/ima/api/v1/auth.py:87-189`).

A partial fix already exists (commit `9bea2ac`): `request()` in
`src/utils/identity-client.ts:80-86` and `IMAClient.request()` in
`src/api/ima-client.ts:25-30` call `revalidateSession()` on 401, and per-page
`useRequireLogin()` watchers then redirect. That coverage is incomplete.

## Confirmed gaps (root cause of the report)

1. **SSE bypasses the 401 handler.** `src/api/grounded-client.ts:34-56` (`streamRequest`)
   uses a raw `fetch` and throws `IMAApiError` without calling `revalidateSession()`.
   A user sitting on a conversation page who asks a question after expiry sees only an
   error toast and stays "logged in".
2. **`getSystemInfo()` bypasses it too.** `src/api/ima-client.ts:36-45` is a second raw
   `fetch` with no 401 branch.
3. **Admin console has no session watcher.** `src/router/index.ts:29-35` only gates
   `requiresAdmin` routes by *role*, and admin pages do not call `useRequireLogin()`
   (only `SettingsLayout`, `AskHome`, `ConnectorsPage`, `ConversationView`,
   `HistoryPage`, `KnowledgeBase` do). An expired session on `/admin/*` shows empty
   tables instead of redirecting.
4. **No global route guard for authentication.** Login enforcement is per-page opt-in,
   so any page that forgets `useRequireLogin()` silently keeps a dead session.

## Goal

Any expired session reliably lands the user on `/auth/sign-in?redirect=<current>`,
regardless of which code path first observes the 401 (JSON fetch, SSE, admin API,
system info), and without breaking the recent-auth 401 flow.

## Requirements

1. Route every authenticated browser request through one shared fetch wrapper that
   handles 401 exactly once.
2. SSE (`streamRequest`) must trigger the same `revalidateSession()` path on 401.
3. `getSystemInfo()` must use the shared wrapper.
4. Add a **global** `router.beforeEach` authentication guard driven by route meta
   (`requiresAuth`), covering `/admin/*` and every protected page; keep the existing
   role-based admin gate.
5. Preserve the redirect query so the user returns to where they were.
6. **Do not** break recent-auth: a 401 from a sensitive operation where the session is
   still valid must NOT sign the user out. `revalidateSession()` already distinguishes
   these by re-checking `/auth/session`; keep that semantics.
7. Public routes (sign-in, sign-up, reset password, share-link join, OAuth consent)
   must stay reachable while signed out.

## Non-goals

- Implementing a refresh-token mechanism or sliding session renewal.
- Changing session lifetimes.
- Reworking the admin console IA.

## Acceptance criteria

- Vitest covers: SSE 401 clears session; `getSystemInfo()` 401 clears session;
  global guard redirects an unauthenticated visit to a protected route; recent-auth
  401 does **not** sign out.
- `bun lint`, `bun type-check` (or project equivalents) and `bun vitest run` pass.
- No behavioural change while the session is valid.

## Key files

- `src/utils/identity-client.ts` — `request()`, `session`, `revalidateSession()`
- `src/api/ima-client.ts` — `request()`, `getSystemInfo()`
- `src/api/grounded-client.ts` — `streamRequest()`
- `src/router/index.ts`, `src/router/routes.ts` — global guard + route meta
- `src/composables/require-login.ts` — existing per-page watcher
- `src/composables/recent-auth.ts` — recent-auth semantics to preserve
