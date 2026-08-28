# OAuth and MCP Service Principal Contracts

> Executable contracts for the OAuth 2.1 authorization server, service principals, and the Python MCP tool surface. Source modules: `ima/domain/oauth.py`, `ima/application/oauth.py`, `ima/application/mcp.py`, `ima/infrastructure/oauth.py`, `ima/api/oauth.py`.

Captured from task `08-24-oauth-service-principals-mcp` implementation and check sessions.

---

## Contract: Delegated-policy errors must propagate with their own status/code/detail

### Scope / Trigger

Every service that authorizes an `McpActor` (service principal or delegated bearer) re-checks current workspace/folder state through `WorkspaceService.authorize_delegated_boundary`. Denials arrive as `WorkspaceError` with a meaningful `status`, `code`, and `detail`.

### Rule

Each `_authorize` / authorization path that calls `authorize_delegated_boundary` must catch `WorkspaceError` specifically and re-raise its own domain error carrying the same `status`, `code`, and `detail`. Never catch a broad `Exception` and collapse the denial into a generic 404.

### Wrong

```python
try:
    await self._workspaces.authorize_delegated_boundary(actor, action, ...)
except Exception:
    raise StorageError(status=404, code=DOCUMENT_NOT_FOUND, ...)
```

Every policy denial (archived workspace, revoked membership, folder ACL deny, revoked principal) surfaces as "document not found", diverging from `knowledge.py` behavior and hiding the real denial reason from audit and clients.

### Correct

```python
try:
    await self._workspaces.authorize_delegated_boundary(actor, action, ...)
except WorkspaceError as exc:
    raise StorageError(status=exc.status, code=exc.code, detail=exc.detail) from exc
```

Keep the same pattern across `storage.py`, `knowledge.py`, `search.py`, and any future target service entry point used by MCP tools.

### Tests Required

- Unit/ASGI test: service principal with archived workspace / revoked folder ACL receives the `WorkspaceError` status and code (e.g. 403 with the policy code), not a blanket 404, for each target service that accepts `McpActor`.

---

## Contract: Every grant/credential invalidation path bumps `revocation_epoch`

### Rule

All lifecycle paths that invalidate already-issued tokens or grants must increment `revocation_epoch` in the same transaction that performs the invalidation:

- explicit revoke (token / grant / principal / credential);
- refresh-token replay detection (family revocation);
- authorization-code reuse detection (grant revocation);
- credential rotation/replacement;
- user disable / security-stamp change paths that invalidate sessions.

Verification on each bearer request compares the presented token's epoch against the current `revocation_epoch`; a missed bump leaves supposedly-dead tokens usable.

### Wrong

```python
# Code-reuse detection revokes the grant but forgets the epoch bump
await conn.execute(
    update(grants).where(grants.c.id == grant_id).values(status="revoked")
)
```

### Correct

```python
await conn.execute(
    update(grants)
    .where(grants.c.id == grant_id)
    .values(status="revoked", revocation_epoch=grants.c.revocation_epoch + 1)
)
```

### Tests Required

- PostgreSQL test for each invalidation path: token/grant issued before the event is denied immediately after; assert the row's `revocation_epoch` increased.

---

## Contract: OAuth endpoints speak OAuth error forms; RFC 9457 only elsewhere

### Rule

`/oauth/token`, `/oauth/revoke`, and authorize redirects must return OAuth-spec error forms (JSON `error`/`error_description` or redirect error params). Any internal domain error raised inside these handlers — including `WorkspaceError` from delegated-policy evaluation during service-credential exchange — must be translated to `McpAuthorizationError` before it can escape the handler. Only non-OAuth API surfaces may fall through to the global RFC 9457 Problem Details handler.

### Wrong

```python
async def exchange_service_credential(...):
    # WorkspaceError from authorize_delegated_boundary escapes the
    # McpAuthorizationError catch and renders as RFC 9457 JSON on /oauth/token
    boundary = await self._workspaces.authorize_delegated_boundary(actor, ...)
```

### Correct

```python
try:
    boundary = await self._workspaces.authorize_delegated_boundary(actor, ...)
except WorkspaceError:
    raise McpAuthorizationError("policy_denied")
```

The handler then renders `{"error": "access_denied", ...}` on the token endpoint.

### Tests Required

- Contract test: expired/revoked credential exchange at `/oauth/token` returns OAuth JSON `access_denied` (not a Problem Details document, not a 500).

---

## Contract: Per-tool timeout hierarchy must sit under the lease TTL

### Rule

MCP tool execution has three nested budgets. They must satisfy:

```
inner bounded budget < outer per-tool timeout < lease TTL (default 60s)
```

`McpService._execute` takes an explicit `timeout_seconds` per tool (default 15s). Long-running tools override it. Example: `kb_ask` uses a 30s inner bounded Ask budget, a 45s outer timeout, under the 60s lease TTL.

### Wrong

```python
async def _execute(self, ...):
    async with asyncio.timeout(15):  # kills kb_ask before its 30s budget can finish
        ...
```

### Correct

```python
await self._execute(request, handler, timeout_seconds=45)  # kb_ask
```

When adding a tool whose inner budget exceeds 15s (model calls, bounded Ask, large uploads), raise its outer timeout explicitly and keep it below the lease TTL.

### Tests Required

- Unit test: `kb_ask` completes when the inner path needs ~30s (outer timeout must exceed it); tool exceeding its outer timeout is cancelled with a bounded error, and the lease does not leak.

---

## Related Specs

- [Identity And Platform Contracts](./identity-platform-contracts.md) — digests, sessions, audit, internal routes
- [Workspace Authorization Contracts](./workspace-authorization-contracts.md) — delegated-policy boundary semantics
- [Error Handling](./error-handling.md) — RFC 9457 rules for non-OAuth surfaces
