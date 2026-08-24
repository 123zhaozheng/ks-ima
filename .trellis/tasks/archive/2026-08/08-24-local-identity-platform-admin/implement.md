# Local Identity And Platform Administration Implementation

## 1. Preflight And Migration Fixtures

- Inventory Better Auth tables/versions, PHC samples, TOTP representation,
  sessions, platform admins, users without credentials, duplicates, and existing
  workspaces on a disposable database copy.
- Add versioned legacy fixtures and an import report contract before changing
  live auth routes.
- Add exact Python auth dependencies and lock; reject unused packages.

## 2. Schema And Crypto Foundation

- Add Alembic identity/platform tables, indexes, constraints, enums/checks, and
  rollback-safe migration.
- Implement clocks/random/token digest, Argon2id verifier/rehash, AES-GCM key
  ring, TOTP, recovery code, rate limit, and redaction services with unit tests.
- Implement identity/platform repositories and transaction boundaries.
- Extend config with cookie/session/crypto/SMTP/bridge/security values and
  production validation.

## 3. Identity Application Services

- Implement registration policy, admin create/invite, accept invite, sign in,
  password/TOTP/recovery challenge, sign out, current session, CSRF, password
  change/forgot/reset, profile, session listing/revocation, TOTP lifecycle.
- Implement security-stamp/session revocation rules and recent-auth checks.
- Implement non-enumerating rate-limited failures and complete audit events.
- Implement SMTP adapter with deterministic fake and disabled-state behavior.

## 4. Platform Administration

- Implement platform capabilities, hierarchy, concurrent last-super invariant,
  bootstrap CLI, and no HTTP acquisition endpoint.
- Implement user cursor/search/detail and every lifecycle/security action.
- Implement typed settings and platform workspace registry lifecycle.
- Add audit listing with auditor/admin policy and redacted metadata.

## 5. Legacy Import And Projection

- Implement `ima migrate-legacy-identity plan|apply|verify|report` or equivalent
  resumable commands with checkpoints and idempotency.
- Verify/copy compatible PHC hashes; force reset incompatible credentials.
- Migrate/reset TOTP according to proven compatibility, never guess.
- Import platform admins/workspace registry, establish/verify super admin, and
  invalidate legacy sessions.
- Upsert minimum `public.user/userData` projection transactionally; assert no
  account/session/TOTP/workspace/member/entity side effects.

## 6. Bun Identity Bridge

- Add Python internal introspection endpoint and bridge token validation; keep it
  out of public Caddy/OpenAPI.
- Add one Bun session adapter with validated internal URL/deadline/no-redirect.
- Replace all 19 direct Better Auth session lookups across Zero, KB, connectors,
  AI, search, S3, and admin routes.
- Add bridge contract/smoke/security/failure tests and metrics.
- Remove `/admin/aquireRole`, Better Auth handler/hook, and fallback session
  parsing after cutover.

## 7. Vue Contract And Complete UX

- Extend/export OpenAPI and regenerate TypeScript.
- Add central identity client, auth-session store, CSRF behavior, and route guard;
  update Zero user ID from Python session.
- Migrate sign-in, invite/open signup, forgot/reset, TOTP/recovery challenge,
  account profile/password/TOTP/sessions, admin users/roles/workspaces/audit.
- Remove Better Auth types/client, email-verification-only UI, trusted-device
  checkbox, recovery TODO, and obsolete components after replacements work.
- Add component tests and Playwright role/account journeys with all UI states.

## 8. Coexistence And Cutover

- Add exact Caddy Python auth/account/admin-user/workspace/audit routes while
  preserving later Bun model/knowledge routes.
- Add internal API/bridge configuration to Bun/Compose without public exposure.
- Run disposable migration, bootstrap, frontend cutover, bridge calls for every
  legacy route, then revoke Better Auth sessions.
- Prove no account creation creates a personal workspace.
- Document one routing/data rollback and rehearse before removing runtime auth.

## 9. Deletion Gate

- Remove Better Auth runtime/server route, frontend client/plugins/types,
  `/admin/aquireRole`, auth creation hook, unfinished recovery/TOTP paths,
  no-longer-used SMTP/config/i18n/dependencies.
- Retain old auth schema only as named read-only migration/rollback data.
- Record bridge/projection deletion milestone in final migration task.
- Run residue searches for `better-auth`, `auth.api.getSession`, `aquireRole`,
  `VerifyEmail`, `trustDevice`, and auth TODOs; classify every remaining match.

## 10. Validation Gates

Backend:

```text
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
OpenAPI export/drift
fresh Compose PostgreSQL auth/migration/bridge gate with no skips
```

Frontend/legacy:

```text
bun run generate:api
bun run lint
bunx vue-tsc --noEmit
bun test
bun run build:front
bun run build:admin
bun run build:server
Playwright auth/admin/role journeys
```

Security/review:

- Password/TOTP/token/session/CSRF values absent from response/log/audit/OpenAPI/
  browser persistence.
- Concurrent last-super and token-single-use tests pass.
- All Bun callers use the one bridge and fail closed.
- No direct Better Auth runtime usage or automatic workspace creation remains.
- No accepted flow has placeholder, TODO, mock-only, or undocumented manual SQL.
- `trellis-check` passes; update executable identity/bridge specs; commit and
  archive this child before starting authorization core.

## 11. Rollback Point

- Preserve pre-cutover DB/object/deployment snapshot and old frontend artifact.
- Before old auth table deletion, restore Caddy/frontend/Bun auth and snapshot;
  invalidate Python sessions. Do not reverse-sync changed passwords.
