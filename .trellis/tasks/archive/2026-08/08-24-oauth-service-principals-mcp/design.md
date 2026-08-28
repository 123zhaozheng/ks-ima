# OAuth Service Principals and MCP Design

## Decisions

| Decision | Chosen contract |
|---|---|
| Interactive authorization | OAuth 2.1 Authorization Code with mandatory PKCE S256 and explicit consent |
| Desktop continuity | Short access tokens plus rotating refresh-token families |
| Protected resource | Canonical public HTTPS `<IMA_PUBLIC_ORIGIN>/mcp`; optional `/api/mcp` aliases it, never becomes another audience |
| Client onboarding | Administratively pre-registered enabled clients only; no DCR or client-metadata documents |
| Token form | High-entropy opaque values; server-side pepper-digest lookup and immediate state evaluation |
| Unattended access | Service principals as finite, constrained delegated grants, not target ACL subjects |
| MCP transport | Pinned official Python MCP SDK Streamable HTTP in FastAPI, stateless mode after compatibility verification |
| Business ownership | Existing target Python application services and target authorization remain authoritative |

## Boundaries

```text
MCP client
  -> public Caddy: /mcp, well-known metadata, /oauth/*
  -> Python FastAPI resource/authorization server
       -> McpAuthorizationService
          -> OAuth/service-principal repositories + rate buckets + audit
          -> WorkspaceService current membership/folder ACL decisions
       -> McpService
          -> KnowledgeService / StorageService / SearchService
  -> official Python MCP Streamable HTTP transport

Browser consent/admin Vue
  -> generated OpenAPI DTOs + central cookie/CSRF client
  -> Python session-protected OAuth and service-principal APIs
```

Caddy is the only public reverse-proxy boundary. Exact `/mcp`, optional legacy
`/api/mcp`, `/.well-known/oauth-protected-resource`, resource-specific protected
metadata, `/.well-known/oauth-authorization-server`, and `/oauth/authorize`,
`/oauth/token`, `/oauth/revoke` match Python before generic `/api/*`. Public
`/api/v1/internal/*` remains a `404`; no private bridge routes are proxied.

The new resource server does not adapt browser cookies into bearer credentials.
Browser sessions authenticate the authorization/consent UI only. MCP bearer
validation creates a normalized `McpActor`; target service calls receive the
actor's delegated authorization context through a dedicated transport-neutral
adapter, not a synthetic cookie session.

## Authorization Model

### Human grants

An interactive grant persists user, client, canonical resource, one workspace,
optional folder root, approved scope set, duration, state, revision/revocation
epoch, and audit references. Authorization codes, access tokens, and refresh
tokens refer to this grant. An opaque access-token lookup must validate all of:

1. pepper digest and record lifecycle/expiry;
2. canonical resource/audience, client, and grant binding;
3. active client, user, user security stamp, and grant;
4. active workspace and active user membership;
5. requested tool scope and folder boundary; and
6. the current target ACL action required by the specific service operation.

A scope is an upper bound, not an ACL replacement. `ask` additionally requires
current content visibility; file download retains its target dependent actions.
Target-hidden resources remain hidden under the target contract rather than
being transformed into a permissive OAuth error.

### Service-principal grants

A service principal has a workspace-admin-approved delegated policy: workspace,
optional folder root, allowed scopes, owner/purpose, finite expiry, lifecycle,
optional CIDR/IP policy, rate/concurrency limits, and audit identity. It has no
user row and is not written into target ACL subject tables. `WorkspaceService`
exposes a dedicated delegated-policy authorization entry point that reuses its
current workspace/folder lifecycle, ancestry, and action checks without calling
user-membership subject loading. The MCP authorization adapter supplies the
principal's workspace/root/action ceiling to that entry point; neither layer
treats creator/admin status as standing principal permission.

A credential has an ID, nonsecret display prefix, pepper digest, finite expiry,
usage/revocation timestamps, replacement lineage, and optional overlap expiry.
The raw credential is generated once. The credential exchange authenticates the
principal and returns only a short-lived opaque access token for `/mcp`; it
cannot issue a refresh token or enter user consent/code routes.

## OAuth and Metadata Contract

`IMA_PUBLIC_ORIGIN` supplies normalized public HTTPS URLs. The initial defaults
are a 60-second authorization code, a 10-minute access token, and a rotating
refresh family with a 30-day absolute lifetime. Configuration may shorten these
values but may not exceed those caps. Service-principal credentials require an
explicit expiry no later than 90 days; any rotation overlap is capped at 10
minutes and never extends either credential or principal expiry.

Protected-resource
metadata declares the canonical `/mcp` resource, authorization-server origin,
supported MCP scopes, and Bearer header authentication. Authorization-server
metadata declares issuer, authorization, token, and revocation endpoints;
`response_types_supported=["code"]`; authorization-code and refresh grant
types; S256; and only the pre-registered client authentication methods actually
implemented. It does not contain registration metadata/endpoints or claims for
unsupported flows.

A missing, malformed, expired, revoked, wrong-resource, or otherwise invalid
bearer credential gets `401` and the resource-metadata challenge. An
authenticated request that lacks required scope gets an OAuth Bearer
`insufficient_scope` challenge with the required scope. Policy denials from the
target authorization layer preserve its non-disclosing semantics. Authorization
and token errors follow OAuth response rules; other public API failures use the
existing RFC 9457 Problem Details contract.

### Interactive sequence

```text
1. Client requests /mcp without bearer -> 401 resource_metadata challenge.
2. Client resolves protected-resource and AS metadata.
3. Client calls /oauth/authorize with registered client, exact redirect, state,
   canonical resource, allowed scope, challenge, and S256.
4. Python validates the request and active local browser session. The user logs
   in if needed. Consent presents the complete exact grant.
5. Approval persists/reuses an eligible grant and creates a short-lived,
   one-time pepper-digested code bound to all request parameters.
6. Python redirects exactly to the registered URI with code, unchanged state,
   and issuer. Denial sends the safe OAuth error response.
7. Client posts code, client authentication where registered, redirect URI,
   resource, and verifier to /oauth/token. A locked transaction validates and
   consumes the code then issues opaque access and rotating refresh records.
8. /mcp validates the access token and current target authorization per tool.
9. Refresh rotates atomically. Reuse or explicit revocation invalidates the
   family/grant so subsequent use fails.
```

Consent is required for a first or expanded combination of client, resource,
workspace, folder boundary, scope, or duration. Reuse only occurs for a current
eligible subset. Write and long-lived refresh approval require the project’s
current-session/recent-auth policy. Token issuance may reduce scope but can
never increase it or expand workspace/folder bounds.

## Persistence and Transaction Rules

New migrations are exclusively in schema `ima`. Names may follow existing model
conventions, but the data model needs these durable records:

- clients and registered exact redirects/client auth policy;
- human grants and optional normalized folder-root rows;
- authorization codes with one-time consumption state;
- access tokens and refresh tokens with resource/client/grant bindings;
- refresh families, replacement/replay/revocation state;
- service principals, delegated roots/policy, and credentials;
- peppered rate/concurrency buckets or leases; and
- audit rows using the existing append-only safe metadata contract.

Every secret-bearing lookup uses the same HMAC/pepper digest approach as
identity/session records, constant-time comparisons where relevant, indexes on
lookup digest/expiry/lifecycle, UTC timestamps, and foreign-key/lifecycle
constraints. Raw code/token/verifier/secret data is not persisted. Authorization
code consumption, refresh rotation/replay family revocation, credential
rotation, and state-changing lifecycle/audit writes execute in a single locked
transaction. The implementation must explicitly test competing exchanges and
revocation-versus-tool races.

## Tool Contract

Tool schemas are versioned, bounded, and map deterministic safe service errors
to MCP results. Tool visibility derives from scope, while invocation also
performs the dynamic authorization described above.

| Scope | Tool family | Target service boundary |
|---|---|---|
| `mcp:workspaces:read` | workspace listing | `WorkspaceService` |
| `mcp:knowledge:read` | directory/tree, note/file metadata/content, tags, authorized download | `KnowledgeService`, `StorageService` |
| `mcp:knowledge:search` | target search | `SearchService` |
| `mcp:knowledge:ask` | non-streaming bounded MCP Ask result with safe citations | New public `SearchService.ask_bounded` method that reuses the same `_folders(..., AclAction.ASK)`, profile, target `search(..., action=ASK)`, citation filtering, model gateway, cancellation, and persistence path as browser Ask, but returns a size-capped typed result instead of SSE bytes; MCP does not consume or parse the browser stream |
| `mcp:knowledge:write` | mkdir, note create/update, bounded upload/ticket, move, tags, trash-delete | `KnowledgeService`, `StorageService` |

Writes carry the target expected-version/concurrency data and use actual
source/destination/parent authorization. `kb_upload_file` permits only a small,
configured bounded inline payload; other files use a target upload-ticket
protocol. `kb_get_file` never exposes storage credentials. Cancellation,
timeout, schema validation, response/body limits, per-principal concurrency,
and per-source/principal rate limits are enforced at the MCP adapter boundary.

## User Experience

The consent page is a Python-session-protected Vue route. It presents client
identity and redirect identity, canonical resource, workspace, folder root,
scope/action descriptions, write indication, expiry, refresh behavior, and
approve/deny. It supports active-session, expired-session, recent-auth, denial,
and broader-request states without exposing protocol secrets.

Workspace access management has separate interactive and unattended paths.
Interactive setup provides the discovery/resource URL and connected-grant list
with revoke. Service administration provides list/detail/create/one-time secret
reveal/rotation/revoke and safe last-use/policy/expiry projections. Browser code
uses generated DTOs, central `identityClient`, and typed errors. No OAuth or
service-secret material is stored in browser persistence or later list results.

## Coexistence, Rollout, and Rollback

1. Install Python-owned schema, application services, discovery/OAuth routes,
   MCP transport, UI, Caddy exact routes, and tests without changing
   `public.connector` or legacy `/api/mcp` behavior.
2. Release canonical `/mcp` as the preferred documented resource and emit safe
   adoption/deprecation observations. Legacy `/api/mcp` may remain solely under
   an explicit compatibility setting and is not a new OAuth audience.
3. Validate real clients and target parity. Inventory active legacy credentials
   and copied configs. An administrator reissues a scoped finite principal
   credential or explicitly revokes/reports each legacy credential; raw legacy
   secrets are never migrated.
4. After announced sunset and acceptance, remove the compatibility route and
   legacy connector UI/config/test/dependency ownership in the parent cleanup
   milestone. This child does not prematurely delete retained coexistence code.

Before sunset, rollback switches Caddy to the tested legacy route/deployment and
uses the pre-cutover database/deployment snapshot if required. After destructive
legacy cleanup, only the approved snapshot/previous deployment restores it.
