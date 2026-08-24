# Local identity and platform administration

## Goal

Make the Python backend the sole browser authentication authority and deliver a
complete local-account and platform-administration experience while preserving
the still-live Bun/Zero product through a narrow, fail-closed session bridge.
Users and operators must be able to complete every supported account lifecycle
without Better Auth UI/runtime behavior, automatic personal workspaces, hidden
bootstrap endpoints, plaintext secrets, or placeholder recovery paths.

## Requirements

### R1. Local Identity Data And Migration

- Add target-schema users, password credentials, sessions, TOTP credentials,
  recovery codes, trusted security state, invite/reset tokens, platform role
  assignments, auth rate-limit state, auth audit events, typed system settings,
  and the platform workspace registry.
- Preserve existing opaque user/workspace IDs where valid. Add an idempotent,
  resumable preflight/import command for Better Auth user/account/password/TOTP
  and workspace metadata.
- Accept an existing password hash only when the Python Argon2id verifier proves
  PHC compatibility; otherwise mark the user for forced reset without copying
  unusable credential material.
- Import TOTP only after verified format/decryption compatibility. Otherwise
  disable it safely, revoke old recovery codes, and require re-enrollment.
- Revoke all legacy Better Auth sessions during cutover; never migrate session
  tokens or dual-write password changes.

### R2. Passwords, Sessions, CSRF, And Rate Limits

- Use Argon2id with versioned parameters and rehash on successful login when
  parameters are obsolete.
- Store only high-entropy opaque session token hashes. Enforce configurable idle
  and absolute expiry, security-stamp binding, activity throttling, rotation,
  session listing, current/other/all-session revocation, and immediate account
  disablement.
- Use HttpOnly/Secure/SameSite browser session cookies in production. Unsafe
  cookie-authenticated API requests require same-origin validation and a
  session-bound CSRF token/header.
- Add per-account and per-source login/reset/invite/TOTP rate limits with safe
  non-enumerating messages and auditable outcomes.
- Password change, reset, TOTP change, platform-role change, disablement, and
  security recovery revoke affected sessions immediately.

### R3. Complete Human Flows

- Implement sign in, sign out, current session, CSRF bootstrap, password change,
  forgot/reset password when SMTP is configured, session list/revoke, TOTP
  enroll/confirm/disable, one-time recovery-code generation/download, and TOTP or
  recovery-code login challenge.
- Default registration policy is closed. Platform administrators can create a
  user with a temporary password or send a single-use expiring account invite;
  optional open registration is an explicit platform setting.
- Password reset and invite links are single-use, expiring, hashed at rest,
  origin-bound, and never logged. SMTP-disabled installations expose a clear
  administrator/user unavailable state rather than a fake success path.
- Remove the unfinished trusted-device/recovery placeholder from the old UI;
  every TOTP-enabled login requires a TOTP or recovery code in the MVP.

### R4. Platform Roles And Bootstrap

- Implement `super_admin`, `platform_admin`, and `security_auditor` assignments
  with server-side capability checks and hierarchy constraints.
- Super admins can manage platform roles. Platform admins manage ordinary users,
  sessions, workspaces, and system settings but cannot grant super-admin or read
  workspace content by platform role. Auditors have read-only security/audit
  access.
- Prevent removal, disablement, deletion, or demotion of the final active super
  administrator. Sensitive role/security actions require recent authentication.
- Implement `ima bootstrap-admin` using interactive input or explicit sealed
  deployment inputs. Refuse normal bootstrap when an active super admin exists.
  No HTTP role-acquisition or first-admin endpoint may remain.

### R5. User And Workspace Administration

- Complete cursor-paginated user search/list/detail plus create/invite, edit
  profile/email, enable/disable/restore, password reset, TOTP reset, session
  revoke, role assignment, and safe deletion rules.
- Complete the platform workspace registry: list/search/create/archive/restore
  and permanent deletion when no target dependencies remain. Workspace creation
  is platform-admin-only and never happens as a side effect of account creation.
- Platform workspace metadata never includes knowledge folders/documents. The
  next authorization child owns membership, groups, and content access.
- Record every platform/auth action in append-only audit events without secret,
  password, token, TOTP, recovery-code, or document content.

### R6. Legacy Bun/Zero Compatibility

- Replace every Bun `auth.api.getSession` call with one shared internal identity
  adapter that introspects the Python session using the forwarded cookie and a
  dedicated bridge credential over a configured internal Python URL.
- The bridge endpoint is not routed by public Caddy paths, returns only the
  minimal active user/platform identity, validates a constant-time bridge
  credential, and fails closed on timeout/error/disablement/revocation.
- During coexistence, Python maintains only the minimum legacy `public.user` and
  `public.userData` projection required by Zero relations. It does not create a
  workspace, Better Auth account/session/TOTP record, or duplicate password.
- Document bridge/projection metrics and deletion owner. Both are removed by the
  final cutover child after all product slices use Python identity/data.
- Delete Better Auth server/client runtime, `/api/auth`, `/admin/aquireRole`,
  authentication hooks, and related unused dependencies after the bridge and
  Python frontend are active.

### R7. Vue Migration

- Replace Better Auth client/types with the generated Python API client, a
  central auth/session store, CSRF handling, and route guards.
- Migrate sign-in, invite/open registration, forgot/reset, TOTP/recovery
  challenge, account profile/password/TOTP/session management, admin user pages,
  platform roles, workspace registry, audit, and all loading/empty/error/expired/
  disabled/recent-auth states.
- Keep existing visual conventions for now. Do not restore commercial, model,
  workspace-membership, or content-administration controls in this child.

### R8. Completeness, Operations, And Removal

- Add unit, PostgreSQL integration, security matrix, OpenAPI/generated-client,
  frontend component, Playwright journey, migration fixture, bridge failure,
  SMTP fake, rate-limit, and session/TOTP/recovery tests.
- Add required configuration, key generation/rotation guidance, migration and
  rollback runbooks, health/readiness, redaction, and operator documentation.
- Remove unused Better Auth UI/server packages, dead components, duplicated
  adapters, TODO recovery behavior, obsolete auth routes/config, and old session
  creation hooks at the named cutover gate.
- No placeholder invitation, mail, TOTP, role, audit, workspace, or bridge
  behavior satisfies this task.

## Acceptance Criteria

- [x] Existing compatible Argon2id users can sign in through Python; incompatible
      credentials enter a tested forced-reset path; legacy sessions are rejected.
- [x] A local user can complete sign-in, CSRF-protected session use, password
      change/reset, TOTP enrollment/challenge/disable, recovery-code login, and
      session review/revocation through the Vue UI and Python API.
- [x] Registration is closed by default; administrator create/invite and optional
      open registration are complete, single-use, expiring, and rate-limited.
- [x] Bootstrap creates the first super admin only through CLI and refuses unsafe
      repetition; the last-super-admin invariant holds under concurrent changes.
- [x] Platform role/capability tests prove administrators do not gain workspace
      content access; auditors cannot mutate; lower roles cannot grant higher.
- [x] Platform user and workspace registry workflows cover create/read/update,
      disable/archive, restore, safe delete, pagination/search, audit, and error
      states without automatic personal workspace creation.
- [x] All legacy Bun/Zero authenticated routes accept active Python sessions via
      the one bridge, reject revoked/disabled/expired sessions immediately, and
      expose no public introspection endpoint or bridge secret.
- [x] New/imported users have only the minimum legacy user projection; no Better
      Auth credential/session/TOTP row or workspace side effect is created.
- [x] Better Auth runtime/client, first-admin endpoint, unfinished recovery UI,
      and obsolete auth hooks/dependencies are removed after cutover; any retained
      auth schema exists only as explicitly documented migration/rollback data.
- [x] Secrets and sensitive auth data never appear in API responses, OpenAPI,
      logs, audits, browser storage/history, generated files, or error messages.
- [x] Clean migration, repeat migration, rollback rehearsal, backend/frontend
      checks, production builds, Docker coexistence, and browser role journeys
      pass with no accepted auth test skipped.

## Out Of Scope

- Workspace membership, groups, directory ACL, and knowledge-content access;
  these belong to `workspace-authorization-core`.
- Model gateways/profiles, document ingestion, RAG, OAuth Agent grants, service
  principals, and MCP authorization.
- Direct LDAP/OIDC login, trusted-device bypass, impersonation, public signup by
  default, or email verification as a separate product requirement.
