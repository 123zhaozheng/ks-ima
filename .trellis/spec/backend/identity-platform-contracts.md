# Identity And Platform Contracts

## 1. Scope / Trigger

Apply this specification to local accounts, sessions, TOTP/recovery, platform
roles, user/workspace administration, and Caddy routing for
`/api/v1/auth|account|admin/*`. Python is the sole browser identity authority.
Platform roles never imply knowledge-content access. The legacy identity
importer, the `public.user`/`userData` projection, and the Bun session bridge
were retired by the legacy deletion release; `/api/v1/internal/*` stays a
terminal public 404.

## 2. Signatures

```text
POST /api/v1/auth/sign-in|totp/verify|recovery/verify|sign-out|register
POST /api/v1/auth/invitations/accept|password/forgot|password/reset
GET  /api/v1/auth/session|csrf
GET/PATCH /api/v1/account/profile
GET/DELETE /api/v1/account/sessions[/{id}]
POST/DELETE /api/v1/account/totp/*
GET/POST/PATCH/DELETE /api/v1/admin/users|workspaces|settings|audit-events

ima bootstrap-admin
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
- Better Auth account/session/verification/TOTP schema and runtime are
  forbidden. No code path writes the retired legacy `public` schema; the
  `ima.legacy_identity_projection` checkpoint table survives as migration
  history only.

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
| Public `/api/v1/internal/*` request | Terminal 404 at the edge; no backend mount |

## 5. Good / Base / Bad Cases

- Good: two concurrent super demotions serialize; one fails and audit matches the
  committed mutation.
- Base: SMTP is absent; password reset/invite clearly report unavailable.
- Bad: check a role in one transaction and mutate in another.
- Bad: paginate only by `created_at`, or bind an uncast null asyncpg cursor.
- Bad: reintroduce any read or write against the dropped legacy `public`
  identity tables.

## 6. Tests Required

1. Unit crypto/digest/redaction/ID/mail compatibility tests.
2. Fresh/repeat Alembic plus forced PostgreSQL gate with
   `IMA_REQUIRE_POSTGRES=1`; zero skips.
3. Atomic reset/recovery use, rate limits, session/TOTP lifecycle, and the
   invite-unavailable-without-SMTP audit path.
4. Actual concurrent final-super mutation with the invariant checked afterward.
5. Contract proof that `/api/v1/internal/*` has no backend mount and the edge
   answers a terminal 404.
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

