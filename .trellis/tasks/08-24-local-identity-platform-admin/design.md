# Local Identity And Platform Administration Design

## 1. Architecture Decision

Python is the sole browser authentication and platform-administration authority.
Bun remains a temporary protected-resource consumer through internal session
introspection; it never verifies Python cookies or reimplements auth policy.

```text
Vue -> /api/v1/auth/*, /api/v1/admin/* -> Python identity/application services
  |                                           |
  | Python HttpOnly cookie                    | ima.* target tables
  v                                           | minimal compatibility projection
Bun legacy route -> internal introspection ---+-> public.user/userData only
```

Better Auth session tokens are invalidated at cutover. No dual password write,
cookie-format emulation, or hidden admin-acquisition route is allowed.

## 2. Python Modules And Dependencies

```text
backend/src/ima/domain/identity/
backend/src/ima/domain/platform/
backend/src/ima/application/identity/
backend/src/ima/application/admin/
backend/src/ima/infrastructure/auth/
backend/src/ima/infrastructure/mail/
backend/src/ima/api/v1/auth.py
backend/src/ima/api/v1/account.py
backend/src/ima/api/v1/admin_users.py
backend/src/ima/api/v1/admin_workspaces.py
backend/src/ima/api/internal/session_bridge.py
```

Use `argon2-cffi` for PHC verification/hashing, `cryptography` AES-GCM for TOTP
secret envelope encryption, `pyotp` for RFC 6238, `email-validator`, and
`aiosmtplib` for optional SMTP. Pin exact versions and remove any unused auth
library after implementation.

Domain/application services do not import FastAPI. Repositories use SQLAlchemy
and one unit-of-work transaction per security mutation.

## 3. Target Tables

All new tables are in `ima` with UTC timestamps and explicit constraints:

- `users`: id, normalized email, display name/image, active/disabled state,
  security stamp, password-reset-required, created/updated/disabled metadata.
- `password_credentials`: user, PHC hash, algorithm/parameter version, changed.
- `sessions`: token digest, user, security stamp, CSRF digest, idle/absolute
  expiry, last activity, source/user-agent summary, recent-auth time, revoked.
- `totp_credentials`: user, encrypted secret/cipher version, confirmed time.
- `recovery_codes`: user, code digest, used/created time.
- `auth_tokens`: invite/reset purpose, digest, user/email, expiry, used time.
- `platform_role_assignments`: user, role, grantor, created time.
- `auth_rate_limits`: bucket digest, action, window, attempts/blocked-until.
- `system_settings`: singleton registration/mail/security policy and version.
- `workspaces`: preserved ID, name, active/archived state, platform creator and
  lifecycle timestamps; no owner/plan/payment/quota/content fields.
- `audit_events`: sequence/id, actor/auth context, action, target reference,
  result/reason code, correlation/source/time, redacted metadata.
- `legacy_identity_projection`: migration/user projection status and last error.

Use partial/unique constraints for normalized email and the last-super-admin
mutation service uses row/advisory locking to remain correct concurrently.

## 4. Password And Token Security

- Argon2id PHC parameters are configured/versioned. Login verifies the stored
  PHC and rehashes inside the successful-login transaction when needed.
- Session/invite/reset/recovery raw values use cryptographic randomness, appear
  only at issuance, and are stored as HMAC-SHA-256 digests with a secret pepper.
- TOTP secrets use AES-256-GCM with key version, random nonce, authenticated user
  ID/purpose data, and a deployment key supplied as secret configuration.
- Password/TOTP/session/token values are typed secrets and recursively redacted.
- Password policy is length-based and permits password managers; never silently
  truncate. Compromised-password checks are deferred because public egress is
  forbidden unless an internal service is configured later.

## 5. Browser Session And CSRF

Cookie contract:

```text
ima_session=<opaque>; HttpOnly; Secure(prod); SameSite=Lax; Path=/
ima_csrf=<opaque>; Secure(prod); SameSite=Lax; Path=/
X-CSRF-Token: <same raw csrf value>
```

The database stores only digests. Unsafe authenticated requests require:

1. allowed `Origin` matching configured public/admin origin;
2. session cookie resolves active, unexpired, matching security stamp;
3. CSRF cookie equals header in constant time and digest matches session.

Login/invite/reset are pre-auth flows protected by exact Origin, one-time token
where applicable, rate limits, and generic credential/account messages.

Activity writes are throttled. Rotation/revocation is atomic. Security-stamp
changes make all outstanding sessions invalid even before cleanup.

## 6. TOTP And Recovery

Enrollment returns an `otpauth://` URI/QR payload only after recent auth, stores
an unconfirmed encrypted secret, then requires a valid code before activation.
Confirmation generates a fixed set of high-entropy recovery codes shown once.
Only digests are stored.

Login is two-step: password verification creates a short-lived, single-purpose
challenge; TOTP or unused recovery code consumes it and creates the real session.
Recovery-code consumption is transactional. Disabling/resetting TOTP requires
recent auth and revokes sessions. Trusted-device bypass is not implemented.

## 7. Platform Capabilities

| Capability | Super admin | Platform admin | Security auditor |
|---|---:|---:|---:|
| Manage super/platform/auditor roles | yes | no | no |
| Manage ordinary users/sessions/TOTP reset | yes | yes | read only |
| Workspace registry lifecycle | yes | yes | read only |
| Change system registration/mail policy | yes | yes | read only |
| Read security/platform audit | yes | policy-limited | yes |
| Read workspace knowledge by platform role | no | no | no |

The final active super admin cannot be disabled/deleted/demoted. Destructive
security actions require `recentAuthAt` inside the configured window.

## 8. API Contract

```text
POST /api/v1/auth/sign-in
POST /api/v1/auth/totp/verify
POST /api/v1/auth/recovery/verify
POST /api/v1/auth/sign-out
GET  /api/v1/auth/session
GET  /api/v1/auth/csrf
POST /api/v1/auth/register
POST /api/v1/auth/invitations/accept
POST /api/v1/auth/password/forgot
POST /api/v1/auth/password/reset
POST /api/v1/account/password/change
GET  /api/v1/account/sessions
DELETE /api/v1/account/sessions/{id}
POST/DELETE /api/v1/account/totp/*
GET/PATCH /api/v1/account/profile
GET/POST/PATCH /api/v1/admin/users/*
POST /api/v1/admin/users/{id}/invite|disable|restore|reset-password|reset-totp|revoke-sessions
PUT/DELETE /api/v1/admin/users/{id}/roles/{role}
GET/POST/PATCH/DELETE /api/v1/admin/workspaces/*
GET /api/v1/admin/audit-events
POST /api/v1/internal/session/introspect
```

OpenAPI contains public/admin contracts but excludes the internal bridge from
the browser client document. All errors use existing Problem Details with
stable auth codes and generic unauthenticated messages.

## 9. Bun Session Bridge

Create one `src-server/auth/session.ts` helper used by every legacy route. It:

- forwards only the Python session cookie and safe request metadata;
- calls configured `PYTHON_API_INTERNAL_URL` with a high-entropy
  `X-IMA-Bridge-Token` secret;
- applies a short deadline, no redirects, same-intranet URL validation, and
  fail-closed null identity;
- returns a minimal `{ user: { id, name, email, image, platformRoles } }` shape;
- never caches longer than session/security changes can tolerate.

The Python internal endpoint is not included in Caddy public matchers, checks
the bridge token in constant time, and resolves the normal session service. A
bridge outage returns 401/503 through legacy endpoints without falling back to
Better Auth.

## 10. Legacy Projection And Cutover

The Python identity transaction upserts `public.user` and `public.userData` only
for active compatibility. It never writes `public.account`, `public.session`,
`public.two_factor`, or creates workspace/member/entity records. Projection
failure aborts user creation/import while legacy slices require it.

Cutover order:

1. Migrate/import users/workspace registry and produce compatibility report.
2. Bootstrap/verify Python super admin.
3. Deploy Python auth/admin and bridge; switch exact Caddy auth/admin paths.
4. Deploy Vue Python auth/admin client and invalidate Better Auth sessions.
5. Replace all Bun session reads with bridge and remove `/admin/aquireRole`.
6. Remove Better Auth server/client runtime and unused dependency.
7. Keep old auth tables read-only for rollback/data verification until final
   migration; remove bridge/projection in the final cutover child.

Rollback before legacy auth table deletion invalidates Python sessions and
restores prior frontend/Caddy/Bun auth plus the pre-cutover database snapshot.
No reverse password dual-write is attempted.

## 11. Frontend State And UX

Use generated DTOs plus a handwritten `identity-client.ts`, Vue Query for server
lists, and one reactive auth-session store for route guards and Zero user ID.
Tokens never enter local/session storage. The CSRF value stays in memory/readable
cookie only as needed by the central client.

Admin tables implement cursor pagination, search, loading/empty/error/retry, and
capability-aware actions. Account surfaces implement password/TOTP/recovery/
sessions. Remove email-verification and trusted-device UI unless their behavior
is fully in target scope; invite/reset links replace the old incomplete path.

## 12. Observability And Audit

Audit login results, password/TOTP/session changes, invites/resets, bootstrap,
role/user/workspace lifecycle, bridge denials, and migration outcomes. Store
safe action/target/result/reason metadata only. Metrics include rate-limit,
login/TOTP failures, active/revoked sessions, bridge latency/failures, mail
delivery result, and auth migration counts.

## 13. Testing Strategy

- Unit: password rehash, token digest, encryption, TOTP windows/replay, CSRF,
  expiry, rate limits, capability hierarchy, last-super invariant.
- PostgreSQL: concurrent login/rate/role mutations, session revocation, token
  single use, audit append, projection transaction, import idempotency.
- Migration fixtures: compatible/incompatible PHC, malformed/unknown TOTP,
  duplicate email, disabled/admin users, existing workspaces, no personal
  workspace side effect.
- Bridge: every Bun caller, timeout, wrong token, public route absence, revoked/
  disabled/expired session, no Better Auth fallback.
- Frontend: sign-in/TOTP/recovery/invite/reset/account/admin states and generated
  contract drift.
- Playwright: ordinary user, super admin, platform admin, auditor, disabled user,
  expired session, closed registration, SMTP unavailable.
- Security: logs/OpenAPI/browser storage/history contain no secret material.
