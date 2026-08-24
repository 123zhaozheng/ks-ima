# Identity And Platform Contracts

## 1. Scope / Trigger

Apply this specification to local accounts, sessions, TOTP/recovery, platform
roles, user/workspace administration, legacy identity migration/projection,
the Bun session bridge, and Caddy routing for `/api/v1/auth|account|admin/*`.
Python is the sole browser identity authority. Platform roles never imply
knowledge-content access.

## 2. Signatures

```text
POST /api/v1/auth/sign-in|totp/verify|recovery/verify|sign-out|register
POST /api/v1/auth/invitations/accept|password/forgot|password/reset
GET  /api/v1/auth/session|csrf
GET/PATCH /api/v1/account/profile
GET/DELETE /api/v1/account/sessions[/{id}]
POST/DELETE /api/v1/account/totp/*
GET/POST/PATCH/DELETE /api/v1/admin/users|workspaces|settings|audit-events
POST /api/v1/internal/session/introspect   # private; absent from OpenAPI/Caddy

ima bootstrap-admin
ima migrate-legacy-identity plan|apply|verify|report
```

Application services use `ima.application.contracts` and transport-neutral
`RequestLike`/`ResponseLike` protocols. They must not import FastAPI or API DTO
modules.

## 3. Contracts

- Passwords use Argon2id PHC; successful login rehashes obsolete parameters.
- Opaque session, CSRF, reset, invite, challenge, and recovery values are stored
  only as peppered digests. TOTP secrets are AES-GCM encrypted with user-bound
  AAD. CSRF comparisons use `hmac.compare_digest`.
- Unsafe cookie requests require an exact allowed Origin, active security-stamp
  bound session, and matching CSRF cookie/header/digest. Pre-auth endpoints also
  require Origin and rate limits.
- Sensitive password/TOTP/role/disable/delete operations require recent auth and
  revoke affected sessions. TOTP/recovery challenges re-check active users.
- `super_admin` alone manages platform roles. `platform_admin` manages ordinary
  users, workspaces, and settings. `security_auditor` reads audit/workspace
  registry only. Role authorization, actor/target locks, last-super advisory
  lock, mutation, and audit share one transaction.
- User/workspace cursors are opaque base64url JSON containing `(createdAt,id)`;
  SQL uses the same descending tuple order and explicit asyncpg casts.
- Migration checkpoints live in `ima.legacy_identity_migration`. Apply commits
  per record, resumes failed records, imports only parse-compatible PHC/TOTP,
  revokes legacy sessions, and never copies legacy session tokens. Verify checks
  every source user's password/reset/TOTP/recovery/projection/userData/workspace
  outcome and every source workspace without printing secrets.
- Python writes only the legacy `public.user`/`userData` projection. Bun keeps a
  minimal `legacy-user.ts`; Better Auth account/session/verification/TOTP schema
  and runtime are forbidden.
- The bridge accepts only a constant-time credential at a private URL, forwards
  the Python cookie, returns minimal active identity, and fails closed.

## 4. Validation & Error Matrix

| Condition | Required result |
|---|---|
| Missing/mismatched Origin or CSRF | 403 Problem Details; no mutation |
| Invalid/disabled credentials | Generic 401; no enumeration |
| Rate bucket exceeded | 429 with audited safe reason |
| Expired/reused invite/reset/challenge/recovery | 400/401; atomic single use |
| SMTP disabled | Explicit unavailable state; issued token unusable |
| Lower role grants any platform role | 403 in locked mutation transaction |
| Final active super mutation races | At least one active super remains |
| Invalid cursor | 400; never silently restart pagination |
| Incompatible legacy PHC/TOTP | Forced reset / TOTP disabled; no guessed import |
| Migration checkpoint failed | Report/verify fails; apply can resume |
| Public `/api/v1/internal/*` request | 404; never Bun fallback |
| Bridge timeout/token/session failure | Null identity / protected route denial |

## 5. Good / Base / Bad Cases

- Good: two concurrent super demotions serialize; one fails and audit matches the
  committed mutation.
- Good: repeat legacy apply is idempotent and verify reports no secret values.
- Base: SMTP is absent; password reset/invite clearly report unavailable.
- Bad: check a role in one transaction and mutate in another.
- Bad: paginate only by `created_at`, or bind an uncast null asyncpg cursor.
- Bad: keep `auth.gen.ts` because legacy relations need only `public.user`.

## 6. Tests Required

1. Unit crypto/digest/redaction/ID/mail compatibility tests.
2. Fresh/repeat Alembic plus forced PostgreSQL gate with
   `IMA_REQUIRE_POSTGRES=1`; zero skips.
3. Atomic reset/recovery use, rate limits, session/TOTP lifecycle, projection
   side effects, compatible/incompatible migration, repeat apply, and verify.
4. Actual concurrent final-super mutation with the invariant checked afterward.
5. Bridge wrong-host/token/timeout/revoked/disabled tests and public OpenAPI/Caddy
   absence.
6. Residue scan for Better Auth runtime/schema, direct session calls, hidden role
   acquisition, trusted-device, placeholders, and secret output.

## 7. Wrong vs Correct

### Wrong

```python
if await service.has_capability(actor, "roles_manage"):
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM role ..."))
```

### Correct

```python
async with engine.begin() as conn:
    await conn.execute(text("SELECT pg_advisory_xact_lock(...)"))
    actor_roles = await locked_roles(conn, actor_id)
    await authorize_and_mutate_role(conn, actor_roles, target_id, role)
    await append_audit(conn, actor_id, "role.revoked")
```

