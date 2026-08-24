# Research: Local identity and legacy identity bridge

- Query: Design the Python-owned local authentication and platform-admin slice, including compatibility with the current Better Auth/Bun/Zero runtime and a deletion path for Better Auth.
- Scope: mixed (repository and external security/library guidance)
- Date: 2026-08-24

## Findings

### 1. Current identity ownership and migration constraints

The repository currently has one Better Auth installation in the Bun/Hono server, but it is a dependency of almost every authenticated product slice. The Python foundation currently owns only health and system paths, so this child must add identity paths without broad Caddy takeover until the bridge is ready.

Files found:

- `src-server/auth/auth.ts:1-92` configures Better Auth with the Drizzle adapter, Bun Argon2id password hashing, email/password sign-in, email verification/reset callbacks, a five-minute cookie cache, the admin plugin, and the two-factor plugin.
- `src-server/schema/auth.gen.ts:3-93` is the generated Better Auth schema: `user`, `session`, `account`, `verification`, and `two_factor`.
- `src-server/auth/routes.ts:1-7` forwards all `/api/auth/*` GET/POST requests directly to `auth.handler`.
- `src-server/index.ts:19-32` mounts auth, Zero, AI, admin, KB, MCP, and connector routes in one Hono app.
- `src-server/zero/routes.ts:10-40` derives the Zero context by calling `auth.api.getSession` and passes `userId` plus `isAdmin` into query/mutator handling.
- `src-server/zero/mutators.ts:1-16` performs a second authorization check against the session user and workspace/entity ACL before delegating to shared mutators.
- `src-server/utils/permissions.ts:36-138` has the useful existing actor contract (`userId`, workspace role, folder root, read/readwrite mode), but `actorFromSession` currently accepts only a user ID supplied by Better Auth.
- `src-server/admin.ts:25-105` checks `session.user.role === 'admin'` directly and currently contains the unsafe first-user `/aquireRole` endpoint. This endpoint must be deleted or disabled when Python bootstrap is available.
- `src/utils/auth-client.ts:1-9` and the auth Vue components call Better Auth client methods directly for session, email sign-in/sign-up, reset password, password change, admin operations, and TOTP.
- `src/utils/zero-session.ts:1-67` rebuilds the Zero client when `authClient.useSession()` changes. The Python replacement must keep the authenticated user ID and role in the same server-owned session response until Zero is removed.
- `src-server/connectors.ts:18-135` creates long-lived `ima_` bearer keys for MCP and returns a configuration containing the raw key once. This is an existing compatibility path, not a browser session; it must be bridged to the new service-principal/OAuth design in a later child.
- `src-server/mcp.ts:95-108` currently allows `Access-Control-Allow-Origin: *` and authenticates only `Bearer ima_...`. This is acceptable only for the connector/MCP compatibility path and must not be copied to cookie-auth API routes.
- `Caddyfile:7-29,45-63` currently sends `/api/*` to Bun, explicitly forbids `/api/admin*`, `/api/auth/admin*`, and `/api/zero*` on the user origin, and sends only `/health/*` and `/api/v1/system/*` to Python. Identity cutover therefore needs exact route matchers and separate admin-origin behavior.
- `backend/src/ima/api/app.py`, `backend/src/ima/api/dependencies.py`, and `backend/src/ima/config.py` establish the FastAPI application, dependency injection, and `IMA_`-prefixed immutable settings conventions. New auth settings and routes should follow these boundaries.
- `backend/pyproject.toml:1-53` currently has FastAPI, SQLAlchemy async, psycopg, Alembic, and Procrastinate, but no password, TOTP, cryptography, Redis, or OAuth/OIDC library.

The current Better Auth migration-specific data is:

```text
user.id, name, email, email_verified, image, created_at, updated_at,
role, banned, ban_reason, ban_expires, two_factor_enabled
account.id, account_id, provider_id, user_id, password, created_at, updated_at
session.id, expires_at, token, created_at, updated_at, ip_address, user_id,
impersonated_by
verification.id, identifier, value, expires_at, created_at, updated_at
two_factor.id, secret, backup_codes, user_id
```

The `account.password` field is the source of the local password hash. Do not assume every user has one: Better Auth can represent non-password accounts, and null must become an explicit `password_auth_enabled = false` state or be rejected by the local sign-in path.

### 2. Recommended Python libraries and version policy

Use small, well-understood libraries and pin them in `backend/pyproject.toml` and `backend/uv.lock`. The Python standard library should handle random token generation, constant-time comparison, URL parsing, and HMAC primitives where possible.

Recommended additions:

| Concern | Library | Recommendation | Reason / boundary |
|---|---|---|---|
| Password hashing | `argon2-cffi` (current stable 25.x line) | Pin a tested minor release | `PasswordHasher` verifies PHC strings and exposes `check_needs_rehash`; use Argon2id only |
| TOTP | `pyotp` 2.9.x | Pin exact version initially | RFC 6238 HOTP/TOTP implementation and provisioning URI; configure SHA-1, 6 digits, 30 seconds for compatibility |
| Encryption | `cryptography` current stable 46.x line | Pin a tested minor release | AES-GCM or Fernet for TOTP secret and recovery-code encryption at rest; prefer AES-GCM with key versioning |
| HTTP client | existing `httpx` dev dependency, promote pinned runtime dependency if needed | Use only for internal Bun-to-Python bridge and configured SMTP/model calls | Explicit timeout, no redirect following for auth bridge |
| Password policy | Pydantic + application code | No extra package | Length/normalization/compromised-password policy is a product contract |
| Rate limiting | PostgreSQL row/window algorithm first; optional `redis.asyncio` only if already deployed | Do not add Redis solely for auth | The product already requires PostgreSQL; a durable DB limiter avoids a new mandatory service |
| OAuth/OIDC provider | Python stdlib + `authlib` only when the OAuth child starts | Do not add now | Local login owns the substrate; Agent OAuth is a later child using the same policy service |

Do not use JWTs for the browser session. JWT revocation, role freshness, and logout semantics would add avoidable state and make emergency revocation harder. Do not use `itsdangerous` as the primary session store; it signs bearer data but does not provide server-side revocation or device/session administration.

External references:

- Argon2 RFC 9106: `https://www.rfc-editor.org/rfc/rfc9106`.
- OWASP Password Storage Cheat Sheet: `https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html`.
- OWASP Session Management Cheat Sheet: `https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html`.
- OWASP CSRF Prevention Cheat Sheet: `https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html`.
- RFC 6238 TOTP: `https://www.rfc-editor.org/rfc/rfc6238`.
- FastAPI security: `https://fastapi.tiangolo.com/tutorial/security/`.
- `argon2-cffi` API: `https://argon2-cffi.readthedocs.io/en/stable/api.html`.
- PyOTP API: `https://pyauth.github.io/pyotp/`.
- Python `secrets`: `https://docs.python.org/3/library/secrets.html`.

Version caveat: package releases can move after this research date. Pin the versions selected by `uv lock`, run the full security suite, and do not silently upgrade Argon2/TOTP behavior during a data migration.

### 3. Python identity data model

Put identity tables in the `ima` schema and keep Better Auth tables in `public` until the final deletion gate. Use SQLAlchemy/Alembic models, not runtime-created tables. Keep timestamps UTC `timestamptz`.

#### 3.1 Account and platform role

```text
ima.user_account(
  id same type as existing user.id primary key,
  email citext unique not null,
  display_name text not null,
  avatar_url text nullable,
  email_verified_at timestamptz nullable,
  platform_role enum('platform_admin','platform_operator','platform_auditor','user') not null,
  status enum('active','invited','suspended','deleted') not null,
  password_hash text nullable,
  password_hash_version text not null,
  must_change_password boolean not null default false,
  failed_login_count integer not null default 0,
  locked_until timestamptz nullable,
  last_login_at timestamptz nullable,
  password_changed_at timestamptz nullable,
  created_at/updated_at timestamptz not null
)
```

Preserve the existing Better Auth user ID: public workspace/member/entity foreign keys and Zero's 16-character IDs depend on identity continuity. Use lower-case Unicode-normalized email for lookup and a deterministic lower-case unique index (or `citext`), not application-only uniqueness.

`platform_admin` is the only role allowed to manage platform identity, workspace lifecycle, model/provider secrets, and global policy. There must always be one active admin; the final one cannot be suspended, deleted, or demoted. Operators may administer users/workspaces only through explicit capabilities; auditors are read-only and cannot read password hashes, TOTP secrets, connector secrets, model keys, or document content by default.

Do not copy Better Auth's free-form `role` into authorization checks. Import `role=admin` as `platform_admin` only after bootstrap/migration validation and record the mapping in audit.

#### 3.2 Opaque sessions

```text
ima.auth_session(
  id uuid primary key,
  token_hash bytea unique not null,
  user_id references ima.user_account,
  created_at/last_seen_at/expires_at/idle_expires_at timestamptz not null,
  revoked_at timestamptz nullable,
  rotated_from uuid nullable references ima.auth_session(id),
  ip_address inet nullable,
  user_agent text nullable (bounded),
  auth_strength enum('password','password_totp','recovery_code','bootstrap')
)
```

Generate at least 32 random bytes with `secrets.token_urlsafe(32)` for the opaque cookie. Store only `SHA-256(raw_token)` (or HMAC with a server key if database-only attackers are in scope). The cookie is `ima_session=<raw>` with `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and server-controlled max age.

Rotate after password login, TOTP completion, password change, privilege elevation, and legacy bridge exchange; revoke the old row in the same transaction. Logout and admin “revoke all” set `revoked_at`, never relying on cookie expiry. Check user status and role freshness on every request or a very short bounded cache so suspension/revocation is immediate.

#### 3.3 TOTP, recovery, and one-time tokens

```text
ima.totp_factor(
  user_id primary key references user_account,
  secret_ciphertext bytea not null,
  secret_key_version text not null,
  issuer text not null, digits smallint default 6, period smallint default 30,
  algorithm text default 'SHA1', enabled_at timestamptz nullable,
  created_at/updated_at timestamptz not null
)
ima.recovery_code(id uuid, user_id references user_account, code_hash bytea,
  used_at timestamptz nullable, created_at timestamptz)
ima.one_time_token(id uuid, purpose, subject_user_id nullable, identifier,
  token_hash bytea unique, expires_at, consumed_at nullable, attempts,
  created_by nullable, created_at)
```

Encrypt TOTP secrets with AES-GCM using a dedicated versioned key from secret management, never a user password. Decrypt with the old key and re-encrypt with the current key during rotation. Generate at least ten recovery codes, show them once, store only hashes, and consume exactly one row under `SELECT ... FOR UPDATE`. Reset, verification, invitation, and bootstrap tokens are opaque, purpose-bound, short-lived, single-use, and hashed at rest.

The Better Auth two-factor plugin stores an encrypted secret and encrypted backup-code blob (generated schema `src-server/schema/auth.gen.ts:79-93`). Import only through a one-off compatibility decoder when the Better Auth secret/configuration is available; otherwise require TOTP re-enrollment. Do not copy the encrypted blob as if it were Python AES-GCM.

### 4. Password compatibility and Argon2id rehash

The current runtime calls `Bun.password.hash` with `algorithm: 'argon2id', memoryCost: 20480, timeCost: 2` (`src-server/auth/auth.ts:23-31`). Bun emits a standard PHC Argon2id string; confirm exact parallelism and encoding against a real exported row before bulk conversion. `argon2-cffi` verifies standard PHC strings.

Migration algorithm:

1. Preserve each `user.id`; copy the password-bearing Better Auth `account` row into the Python credential table and mark `password_hash_version = legacy-better-auth`.
2. Test PHC fixtures generated by the exact Bun version in this repository, including Unicode/long passwords, wrong passwords, and malformed PHC values. Fail closed on malformed rows.
3. On a successful Python sign-in, verify the legacy PHC using `PasswordHasher.verify`. If parameters are below the configured policy, hash the supplied password with current explicit Argon2id settings and replace the hash in the same transaction. Set `password_hash_version = argon2id-v1`.
4. Do not rehash after a failed verification. Unknown email, bad password, disabled user, and expired verification use the same generic response and comparable work (including a dummy hash verify for unknown users).
5. After a bounded migration window, report remaining legacy hashes without revealing accounts and require reset for unsupported rows.

Set explicit memory/time/parallelism settings rather than relying on library defaults. Benchmark them on deployment hardware. Password hashing is blocking and must run in a bounded threadpool/concurrency limiter, never unrestricted on the ASGI event loop. Never trim or normalize the password itself.

### 5. Authentication and browser API contracts

All browser auth endpoints belong to Python under `/api/v1/auth` and use the existing RFC 9457 `application/problem+json` envelope on failure:

```text
GET    /api/v1/auth/csrf
GET    /api/v1/auth/session
POST   /api/v1/auth/sign-in                 { email, password, rememberMe? }
POST   /api/v1/auth/sign-in/totp            { challengeId, code, trustDevice? }
POST   /api/v1/auth/sign-in/recovery        { challengeId, recoveryCode }
POST   /api/v1/auth/sign-up                 { name, email, password }
POST   /api/v1/auth/sign-out
POST   /api/v1/auth/password/change         { currentPassword, newPassword, revokeOtherSessions? }
POST   /api/v1/auth/password/reset/request  { email }
POST   /api/v1/auth/password/reset/consume  { token, newPassword }
POST   /api/v1/auth/email/verify            { token }
POST   /api/v1/auth/totp/enroll/start      { currentPassword }
POST   /api/v1/auth/totp/enroll/confirm     { challenge, code }
POST   /api/v1/auth/totp/disable            { currentPassword, code }
GET    /api/v1/auth/sessions
DELETE /api/v1/auth/sessions/{id}
POST   /api/v1/auth/sessions/revoke-all
```

`GET /session` returns only a safe projection (`id`, display name, email, platform role, status, TOTP enabled, and bounded session metadata). It never returns password hashes, secrets, recovery codes, reset state, provider secrets, or document data. This response becomes the sole frontend auth source; Zero may consume its user ID during the temporary bridge.

If TOTP is enabled, password sign-in must not leave a fully authenticated session. Return a short-lived, single-use challenge bound to the user and purpose. TOTP/recovery completion creates and rotates the real session. Invalidate the challenge after success, expiry, too many failures, or sign-out. A “trust device” option, if retained for UI compatibility, should create a separately hashed, revocable device token with a bounded lifetime (for example 30 days) and must not satisfy sensitive admin re-authentication.

### 6. CSRF, origin, cookies, and proxy rules

Cookie-authenticated state-changing requests need both:

1. Strict `Origin` validation against the exact `IMA_PUBLIC_ORIGIN` and admin origin. For clients that omit Origin, use same-origin Referer only when present; otherwise require the CSRF token. Never accept `Origin: null` for privileged mutation.
2. A synchronizer token returned by `/csrf`, stored server-side or HMAC-bound to the session, required in `X-CSRF-Token` for POST/PUT/PATCH/DELETE. Do not accept a token only supplied as a cookie. Rotate on login and privilege transitions.

Reuse the foundation's `IMA_CORS_ORIGINS` and trusted-proxy parsing in `backend/src/ima/config.py` and `backend/src/ima/api/middleware.py`; do not add a second origin parser. Caddy must preserve Host and forwarded scheme only from configured trusted proxies. Set `Secure` according to the external scheme, not the API container hop.

Bearer service credentials and future OAuth code endpoints do not use browser CSRF tokens and must not fall back to cookies. A request containing both cookie and bearer token has deterministic rules: `/auth/*` ignores bearer, while MCP/service APIs ignore browser cookies unless an endpoint explicitly supports interactive OAuth.

### 7. Rate limits and audit

Start with PostgreSQL fixed/sliding windows in `ima.auth_rate_limit`:

```text
key text primary key                 # login:email_hash, login:ip, reset:email_hash
window_started_at timestamptz
count integer
blocked_until timestamptz nullable
updated_at timestamptz
```

Use an atomic upsert/update, not a read-then-write race. Key by HMAC/hashed normalized email and source IP; never raw identifiers. Initial safe bounds:

- sign-in: five failures per email and IP in 15 minutes, progressive delay;
- reset request: three per email/IP per hour, generic response whether account exists;
- TOTP/recovery: five attempts per challenge in 10 minutes;
- sign-up/invite: five per IP per hour and one-use token;
- admin mutation: authenticated user/IP limiter plus audit.

If Redis is added later, it must not be required by default and sign-in/reset must fail closed when the limiter is unavailable. PostgreSQL remains the authoritative backstop for admin actions.

Create append-only `ima.audit_event`:

```text
id, occurred_at, actor_user_id nullable, action, target_type, target_id,
request_id, ip_address, user_agent, allow-listed metadata, outcome
```

Audit sign-in success/failure (without password or raw email), logout, session creation/revocation, password/TOTP/reset changes, bootstrap, role/status changes, workspace lifecycle, model/provider secret changes, service-principal changes, and ACL changes. Write security audit in the same transaction as the mutation where practical. Metadata must never contain passwords, tokens, TOTP URIs, recovery codes, or document bodies.

### 8. Platform role and admin invariants

Use one Python capability dependency such as `require_capability('platform.users.write')`, never scattered string checks. Capabilities should include:

```text
platform.system.read
platform.users.read / write / delete
platform.sessions.revoke
platform.workspaces.create / read / update / archive / delete
platform.models.read / write / publish
platform.providers.read / write / rotate-secret
platform.audit.read
workspace.members.read / invite / role-change / remove
workspace.content.read / ask / edit / delete / manage
```

Role mapping:

- `platform_admin`: all platform capabilities, including provider/model secret and role management;
- `platform_operator`: user/workspace/support/session operations, no provider secret read and no role elevation;
- `platform_auditor`: read-only metadata/audit access, no secrets, content, or mutations;
- `user`: no platform capabilities; workspace membership/ACL controls content;
- workspace `owner/admin/member/guest` remains separate from platform role.

Platform admins may administer workspace metadata but must not automatically read document bodies. Any support access is an explicit break-glass action with reason, expiry, and audit.

Invariants enforced in serializable/locked transactions:

- bootstrap only when no active platform admin exists;
- at least one active platform admin always remains;
- operators cannot grant/revoke `platform_admin`;
- last-admin self-demotion/deletion/suspension is rejected;
- suspended/deleted users cannot create sessions and lose existing sessions immediately;
- platform admins alone create/archive/delete workspaces; ordinary users never auto-create personal workspaces;
- user deletion is disable/revoke/transfer/archive then delete, not direct row deletion;
- ordinary users see only published capability profiles, never provider keys or raw model parameters.

### 9. Bootstrap CLI and deployment sequence

Add commands consistent with `backend/src/ima/cli.py`:

```text
ima auth bootstrap --email ... --name ... [--password-stdin]
ima auth migrate-better-auth --dry-run
ima auth migrate-better-auth --apply
ima auth check
ima auth revoke-user-sessions <user-id>
```

Bootstrap requires an interactive TTY or secret through stdin/environment, rejects command-line passwords, can generate a displayed one-time headless enrollment token, refuses to overwrite an existing admin, and prints no password/token after success. The first-admin invariant is protected by a database lock/serializable transaction, not CLI preflight only.

Rollout:

1. Alembic creates Python identity tables; no routing change.
2. `migrate-better-auth --dry-run` reports duplicate emails, unsupported hashes, malformed TOTP rows, banned users, and role mappings without secrets.
3. Apply import in batches, preserving IDs and leaving Better Auth data untouched.
4. Deploy Python auth in shadow/session-read mode and compare identity results on test accounts.
5. Switch Vue auth to Python `/session`/sign-in; Bun legacy routes authenticate through the bridge below.
6. Route exact `/api/v1/auth/*` to Python. Keep Better Auth only on an internal, rate-limited migration path and unlink it from UI.
7. Migrate/replace each Zero/Bun vertical slice; each uses the Python identity dependency and existing ACL service.
8. At write-freeze cutover revoke Better Auth sessions, disable Better Auth sign-in, and remove bridge.
9. Snapshot/export old auth data according to retention, then delete Better Auth tables, generated schema, dependency, routes, plugin calls, and frontend client code in one named deletion gate.

### 10. Legacy Bun/Zero bridge while Python is browser authority

Do not make Python parse Better Auth's signed cookie or reuse the raw Better Auth session token as the new cookie. Better Auth generates a 32-character session token and signs the cookie with its secret; its optional cookie cache contains a short-lived serialized user/session projection. These are runtime details and should not become a Python contract.

Use two explicit phases:

#### Phase A: one-time browser exchange

- Python `/api/v1/auth/bridge` receives the legacy cookie forwarded by the browser.
- Python calls a private Bun-only bridge that invokes `auth.api.getSession` and returns only a signed, single-use assertion containing preserved user ID, nonce, `iat`, 60-second `exp`, and audience `ima-python-auth`. It must not return the Better Auth token or password data.
- The nonce is consumed in a shared DB table (or a signed assertion plus DB replay record). Python rejects replay, wrong audience, expiry, and wrong signature.
- Python checks the mapped user status, creates a normal Python session, rotates the cookie, and redirects only to a strict same-origin allow-list path.
- Missing/disabled users receive generic login failure; browser input never supplies the user ID.

The bridge is private-network-only (or an exact Caddy path), protected by a separate internal secret/mTLS, aggressively rate-limited, and removed after the migration window.

#### Phase B: Bun legacy route introspection

Until a Bun slice is migrated, Hono receives the new `ima_session` cookie and calls a private Python introspection endpoint. Python returns only:

```json
{
  "active": true,
  "userId": "preserved-id",
  "platformRole": "user",
  "status": "active",
  "authStrength": "password_totp",
  "expiresAt": "..."
}
```

The endpoint requires service authentication, has a strict timeout, and never returns document/model data. Bun fails closed for mutation when introspection is unavailable. Do not cache revocation longer than a very small bounded interval.

Replace `auth.api.getSession` calls in `src-server/zero/routes.ts`, `ai.ts`, `search.ts`, `s3.ts`, `connectors.ts`, `kb.ts`, and `admin.ts` with one `getPythonIdentity()` adapter, then replace the adapter with native Python application services as each vertical slice migrates.

For Zero, the temporary adapter preserves `Context { userId, locale, isAdmin }`, but maps `isAdmin` from Python's platform role and still runs workspace/folder ACL checks. It must not copy the current browser assumption `isAdmin: true` in `src/utils/zero-session.ts:19`.

The bridge must not accept a cookie and bearer token as interchangeable credentials. Browser cookies authenticate browser-origin REST; OAuth/service credentials authenticate Agent/MCP endpoints.

### 11. Agent OAuth and MCP substrate contract

The local session is the login authority, not the Agent bearer credential. The later OAuth/MCP child should call the same Python identity/policy services:

```text
GET  /.well-known/oauth-authorization-server
GET  /.well-known/oauth-protected-resource
GET  /api/v1/oauth/authorize
POST /api/v1/oauth/token
POST /api/v1/oauth/revoke
GET  /api/v1/auth/consent
```

Use Authorization Code + PKCE S256 for interactive Agents. Register exact redirect URIs; store authorization requests and codes server-side, bind code to client ID, redirect URI, user, scope, and code challenge, expire in about five minutes, and consume atomically. Scope must be explicit (for example `workspace:<id>:knowledge:read`, `knowledge:ask`, and `mcp:tools`) and may not grant a workspace/folder not visible to the approving user.

Issue opaque access tokens (random 32+ bytes, SHA-256/HMAC at rest, one-hour maximum by default) with no document claims. Rotate refresh tokens if refresh is enabled; revoke the entire grant on replay. Unattended Agents use administrator-created service principals with hashed secrets, explicit workspace/folder/action scope, expiry, rotation, and audit. Existing `connector` `ima_` keys may be accepted only as a time-bounded compatibility adapter and must not be treated as the long-term model.

### 12. Better Auth deletion gate

Delete Better Auth only when all are true:

- no frontend import of `better-auth` or `authClient` remains;
- no server import of `better-auth`, `auth.api`, or `src-server/auth/*` remains;
- no Caddy route forwards browser auth to Bun;
- no public route accepts a legacy session cookie;
- Zero/Bun slices use Python identity or have been deleted;
- connector/MCP auth has an independent OAuth/service-principal path;
- migration reports zero active Better Auth sessions and zero unconverted users/hashes/TOTP rows (or an explicit operator waiver);
- Python security, integration, revocation, and route-coexistence gates pass;
- a rollback snapshot/export exists before dropping old auth rows.

Delete as one named cleanup gate: dependency and lock entry, auth config/SMTP callbacks if unused, generated `auth.gen.ts`, Better Auth migrations/snapshots, Hono auth routes, plugin calls, Vue auth client/plugins, old auth dialogs' API calls, and `/aquireRole`. Do not leave a dead compatibility package or generated schema.

### 13. Tests required

Unit tests:

- exact Bun Argon2id PHC fixtures, malformed hashes, wrong passwords, and rehash replacement;
- password policy does not trim/normalize secrets and enforces bounds;
- raw session tokens never persist; expiry, idle expiry, revocation, and rotation reject correctly;
- CSRF token rotation and origin/referer matrix including `Origin: null`, absent origin, proxy headers, and admin origin;
- AES-GCM TOTP encryption/decryption, key rotation, wrong-key failure, and no plaintext secret in logs;
- RFC 6238 current/previous timestep, wrong code, replay protection, and concurrent one-time recovery-code consumption;
- reset/invite token expiry, purpose binding, hash-at-rest, one-use behavior, and generic unknown-user response;
- concurrent rate limiting and progressive lock behavior;
- complete capability matrix and last-platform-admin invariant.

Integration/contract tests:

- Alembic creates only `ima` identity tables and leaves legacy `public` tables unchanged;
- sign-in, TOTP challenge, cookie flags, `/session`, sign-out, revoke-all, reset, and admin mutations use Problem Details/correlation IDs;
- cookie mutation without CSRF is 403 and valid same-origin mutation succeeds;
- concurrent bootstrap creates exactly one admin;
- last-admin demotion/delete fails and suspended users lose sessions immediately;
- bridge rejects replay/expiry/wrong audience/wrong signature and issues only Python cookie;
- Bun/Zero introspection returns bounded identity and fails closed for mutations on Python outage;
- exact Caddy routing sends `/api/v1/auth/*` and internal identity paths to Python while legacy chat/Zero remain Bun;
- audit exists for all security/admin mutations and contains no password/token/TOTP URI/recovery code/document body;
- cleanup test proves no Better Auth import/dependency/public route after deletion.

## Related specs

- `.trellis/spec/backend/python-foundation-contracts.md` — `IMA_` settings, FastAPI/worker boundaries, Problem Details, correlation IDs, and migration rules.
- `.trellis/spec/backend/database-guidelines.md` — SQLAlchemy/Alembic, isolated `ima` schema, UTC timestamps, and no runtime migrations.
- `.trellis/spec/backend/error-handling.md` — error response contract.
- `.trellis/spec/backend/logging-guidelines.md` — structured logging and redaction; extend redaction to auth secrets.
- `.trellis/spec/backend/quality-guidelines.md` — Python quality gates.
- `.trellis/tasks/08-24-python-intranet-ima-migration/design.md` — local-account, OAuth-agent, platform-role, and deletion decisions.

## Caveats / Not Found

- No Python identity implementation, Alembic identity migration, auth settings, Python frontend auth client, or session introspection endpoint exists yet.
- Better Auth's exact Argon2 parallelism and production `BETTER_AUTH_SECRET` are deployment facts, not committed configuration. Obtain a sanitized real PHC fixture and secret-management decision before importing password/TOTP rows.
- Current Drizzle timestamps are not explicitly timezone-aware; Python must normalize imported values to UTC and document assumptions.
- `src-server/utils/db.ts` runs Drizzle migration at import time. Python identity must never copy that startup mutation behavior.
- No Redis deployment is visible. PostgreSQL is the safest first limiter; adding Redis requires a separate availability/fail-closed decision.
- No external Agent OAuth authorization-server implementation exists. The OAuth contract above is a later child and must use the Python session/policy service rather than inventing a second identity store.
- Current MCP has wildcard CORS and static connector keys; retain only as compatibility and replace in the dedicated MCP/OAuth child.
- Current admin UI exposes `role: 'user' | 'admin'`, plan/quota controls, and unsafe first-user role acquisition. These are migration inputs, not a safe target authorization model.
