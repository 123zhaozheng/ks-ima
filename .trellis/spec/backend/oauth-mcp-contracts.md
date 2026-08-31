# OAuth and MCP Service Principal Contracts

> Executable contracts for the OAuth 2.1 authorization server, service principals, and the Python MCP tool surface. Source modules: `ima/domain/oauth.py`, `ima/application/oauth.py`, `ima/application/mcp.py`, `ima/infrastructure/oauth.py`, `ima/api/oauth.py`. See also [Legacy Migration and Cutover Contracts](./legacy-migration-cutover-contracts.md).

Captured from task `08-24-oauth-service-principals-mcp` implementation and check sessions.

---

## Contract: Authorization is user-level; every tool call re-checks the target knowledge base

### Scope / Trigger

OAuth grants no longer bind a single knowledge base: a grant belongs to the
user and covers every knowledge base they can reach. `McpActor` carries only
`user_id` (human) or `principal_id` (service principal) plus canonical
scopes. `McpAuthorizationService.authorize_tool` authorizes each tool call
individually; `McpToolAdapter._execute` / `_document` translate the outcome
into MCP tool errors.

### Rule

Every tool call must pass `authorize_tool(actor, tool_name,
target_kb_id=...)` before touching content:

- Scope first: the tool's canonical scope (`SCOPE_TOOL_MAP`) must be in
  `actor.scopes`, else `insufficient_scope`.
- Membership second: when a tool targets a knowledge base, the caller's live
  role comes from `KbService.list_knowledge_bases`; missing membership is
  `policy_denied` ("Knowledge base is not accessible").
- Role third: `TOOL_MIN_ROLE` requires `editor` or better for the
  `mcp:knowledge:write` tools and `viewer` for everything else.
- Service principals are judged by their owner's membership
  (`effective_user_id` resolves `principal.owner_user_id`); `kb_ask`
  additionally refuses non-human actors at execution time.
- Document-scoped tools (`kb_get_note`/`kb_get_file`/`kb_update_note`/
  `kb_move`/`kb_delete`) authorize scope and grant lifecycle before loading
  the document, then re-authorize against the document's own knowledge base.

Denials keep their own code and detail: the adapter catches
`McpAuthorizationError`, `KbError`, `KnowledgeError`, and `SearchError` and
re-raises `ToolError(f"{code}: {detail}")`. Never catch a broad `Exception`
and collapse a policy denial into `INTERNAL_ERROR` or a blanket 404.

### Wrong

```python
try:
    await runtime.authorization.authorize_tool(actor, tool_name, target_kb_id=kb_id)
except Exception:
    raise ToolError("INTERNAL_ERROR: target operation failed")
```

Every policy denial (missing membership, insufficient role, revoked grant,
inactive principal) surfaces as an internal error, hiding the real reason
from clients and diverging from the audited `mcp.tool.denied` rows.

### Correct

```python
except (McpAuthorizationError, KbError, KnowledgeError, SearchError) as exc:
    code = getattr(exc, "code", None) or getattr(exc, "reason", "POLICY_DENIED")
    raise ToolError(f"{code}: {getattr(exc, 'detail', 'Target operation denied')}") from exc
```

Keep this pattern in every MCP tool adapter path; allowed and denied calls
both append `mcp.tool.allowed` / `mcp.tool.denied` audit rows with tool and
knowledge base identifiers.

### Tests Required

- Unit/ASGI tests: a human grant whose membership was revoked receives
  `policy_denied` for each knowledge-base tool; a viewer's write tool call
  fails with the role-denial code, not a blanket error; service principals
  inherit the owner's current role and `kb_ask` refuses them.

---

## Contract: Grants and service principals are user-level; consent chooses scopes only

### Rule

- Human grants bind the user, never a knowledge base: new grants always keep
  `mcp_grants.kb_id` null and cover every knowledge base the user can reach.
  The OAuth consent flow selects scopes only; the consent view carries no
  knowledge-base or folder selection.
- The scope vocabulary is exactly `mcp:knowledge-bases:read`,
  `mcp:knowledge:read`, `mcp:knowledge:search`, `mcp:knowledge:ask`, and
  `mcp:knowledge:write`. `parse_scopes` rejects unknown scopes so a typo can
  never silently grant nothing.
- Service principals belong to their creator (`owner_user_id`) and may reach
  every knowledge base the creator is a member of. Their scopes are limited
  to `SERVICE_PRINCIPAL_SCOPES` (everything except `mcp:knowledge:ask`), and
  their effective content identity is always the owner's current membership.
  Creating a principal for an inactive owner is rejected.
- Users administer their own surface: `GET/DELETE /api/v1/oauth/grants`
  lists and revokes connected grants; `/api/v1/service-principals*` manages
  principals and one-time credentials. There is no per-knowledge-base grant
  administration.

### Tests Required

- Consent preview/submit never accepts knowledge-base or folder parameters.
- A granted user's `kb_list_knowledge_bases` returns owned and shared
  libraries; removing a membership shrinks the next tool call immediately.
- Service principal creation with `mcp:knowledge:ask` is rejected; owner
  membership loss denies the principal's next call.

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

`/oauth/token`, `/oauth/revoke`, and authorize redirects must return OAuth-spec error forms (JSON `error`/`error_description` or redirect error params). Any internal domain error raised inside these handlers — including `KbError` from knowledge-base policy evaluation reached through `McpAuthorizationService` — must be translated to `McpAuthorizationError` before it can escape the handler. Only non-OAuth API surfaces may fall through to the global RFC 9457 Problem Details handler.

### Wrong

```python
async def authorize_preview(...):
    # KbError from knowledge-base policy evaluation escapes the
    # McpAuthorizationError catch and renders as RFC 9457 JSON on /oauth/authorize
    role = await self._kb.require_membership(user_id, kb_id)
```

### Correct

```python
try:
    role = await self._kb.require_membership(user_id, kb_id)
except KbError:
    raise McpAuthorizationError("policy_denied", "Knowledge base is not accessible")
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

`McpToolAdapter._execute` takes an explicit `timeout_seconds` per tool (default 15s). Long-running tools override it. Example: `kb_ask` uses a 30s inner bounded Ask budget, a 45s outer timeout, under the 60s lease TTL.

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
- [Knowledge Base Authorization Contracts](./kb-authorization-contracts.md) — membership-role boundary semantics
- [Error Handling](./error-handling.md) — RFC 9457 rules for non-OAuth surfaces
