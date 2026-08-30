# Research: MCP OAuth Authorization for Local Accounts

- Query: How should this project expose its Streamable HTTP MCP server to external Agent platforms through a browser authorization link, while keeping local accounts, workspace/folder ACLs, and admin-controlled headless credentials?
- Scope: mixed
- Date: 2026-08-24

## Findings

### 1. Current project boundary

The application already has the resource-server side of the problem, but its connector credential is a project-specific bearer key rather than OAuth:

- `src-server/auth/auth.ts:16-45` configures Better Auth with local email/password accounts, an Argon2id password implementation, cookie sessions, admin, and TOTP plugins. This is a suitable human authentication source for an authorization server, but the current configuration does not expose OAuth authorization/token endpoints.
- `src-server/mcp.ts:95-107` accepts only `Authorization: Bearer ima_...`, resolves the key with `actorFromApiKey`, and dispatches a stateless Streamable HTTP request.
- `src-server/mcp-dispatch.ts:94-103` uses the official TypeScript SDK `WebStandardStreamableHTTPServerTransport` with `sessionIdGenerator: undefined`, so MCP protocol state is deliberately independent from user authentication state.
- `src-server/schema/schema.ts:439-456` stores connector credentials as a SHA-256 hash plus prefix, workspace, creator, read/readwrite mode, optional folder root, expiry, revocation, last-use timestamp, and creation timestamp. This is the right shape to preserve as a legacy/service-credential boundary, but OAuth grants need separate client, authorization-code, access-token, refresh-token, and consent records.
- `src-server/utils/permissions.ts:61-91` derives an MCP actor from the connector creator's workspace membership and applies connector folder/mode restrictions. OAuth actors must continue through this same ACL path; OAuth scope must not replace entity ACL checks.
- `src-server/connectors.ts:18-135` allows workspace admin/owner users to create, rotate, and revoke connectors, and returns a URL plus a bearer key. The future UI should add an `Authorize Agent` flow and retain an admin-only service-credential flow rather than exposing model or database details to ordinary users.
- `scripts/mcp-handshake.ts:16-35` and `scripts/mcp-live.ts:41-47` already exercise the official SDK client against Streamable HTTP. These are the base for authenticated OAuth interoperability tests.
- `package.json` uses `@modelcontextprotocol/sdk ^1.25.2`, `better-auth ^1.5.4`, Hono `^4.9.11`, and Zod. Any OAuth implementation must be checked against the exact installed versions; the current Better Auth setup should not be assumed to be an OAuth authorization server.

### 2. Protocol model to implement

The same deployment acts as two OAuth roles:

1. Authorization server: authenticates local users with the existing Better Auth session and displays consent.
2. Protected resource server: `/api/mcp` validates OAuth bearer tokens and maps the token grant to an MCP actor.

The MCP resource identifier must be a canonical absolute URI, for example `https://ima.intra.example/api/mcp` (no fragment and preferably no trailing slash). It must be stable behind the reverse proxy. The OAuth `resource` parameter is required in both authorization and token requests, and the resulting token must be accepted only by that MCP resource. Do not accept an arbitrary bearer token issued for another API, and never forward an Agent's MCP token to an upstream model provider.

The target flow is Authorization Code + PKCE with `S256`:

```text
Agent -> GET /api/mcp without token
MCP  -> 401 + WWW-Authenticate: Bearer resource_metadata="...", scope="kb:read kb:ask"
Agent -> protected-resource metadata -> authorization-server metadata
Agent -> register/pre-registered client ID
Agent -> browser /oauth/authorize?response_type=code&client_id=...&redirect_uri=...
                    &code_challenge=...&code_challenge_method=S256&resource=...&scope=...&state=...
User -> local login (if no Better Auth session) -> consent -> exact redirect URI
Agent -> POST /oauth/token with code + redirect_uri + client_id + code_verifier + resource
AS    -> short-lived access token (+ rotated refresh token when permitted)
Agent -> MCP requests with Authorization: Bearer <access token>
```

OAuth authorization code, PKCE verifier binding, resource binding, and exact redirect matching are separate checks. A valid user session alone must never authorize an Agent without an explicit consent decision.

### 3. Discovery metadata and HTTP errors

MCP clients need standard discovery before they can open a login link. Implement both the challenge and well-known forms:

- On an unauthenticated MCP request, return `401 Unauthorized` with `WWW-Authenticate: Bearer resource_metadata="https://.../.well-known/oauth-protected-resource" scope="kb:read kb:ask"`. Do not include tokens in the URL.
- Serve protected-resource metadata at the root well-known path and at the endpoint-derived path where practical: `/.well-known/oauth-protected-resource` and `/.well-known/oauth-protected-resource/api/mcp`. The document should include:

```json
{
  "resource": "https://ima.intra.example/api/mcp",
  "authorization_servers": ["https://ima.intra.example"],
  "scopes_supported": ["kb:read", "kb:ask", "kb:write"],
  "bearer_methods_supported": ["header"]
}
```

- Serve authorization-server metadata at `/.well-known/oauth-authorization-server` (and, if the issuer has a path, use the RFC 8414 path rules). Recommended fields:

```json
{
  "issuer": "https://ima.intra.example",
  "authorization_endpoint": "https://ima.intra.example/oauth/authorize",
  "token_endpoint": "https://ima.intra.example/oauth/token",
  "revocation_endpoint": "https://ima.intra.example/oauth/revoke",
  "registration_endpoint": "https://ima.intra.example/oauth/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["none", "client_secret_basic"],
  "scopes_supported": ["kb:read", "kb:ask", "kb:write"],
  "authorization_response_iss_parameter_supported": true
}
```

- Return `401` for absent, expired, revoked, malformed, wrong-audience, or otherwise invalid tokens. Return `403` for an authenticated token whose granted scopes or ACL do not permit the operation. For insufficient scopes, include `WWW-Authenticate: Bearer error="insufficient_scope" scope="..." resource_metadata="..."`.
- Authorization-server endpoints must be HTTPS in production. The only practical local-development exception should be loopback development; an intranet deployment should terminate TLS at Caddy/reverse proxy. Do not advertise an HTTP public issuer.

### 4. Client registration and redirect URI policy

Support the registration modes needed by real Agent platforms, while keeping the local installation understandable:

1. Pre-registration: administrator can register a known client with a fixed client ID and exact redirect URIs.
2. Dynamic Client Registration (`POST /oauth/register`): support for interoperability with clients that discover an MCP server and register automatically. It should issue a public-client ID with no secret when `token_endpoint_auth_method=none`, accept only `authorization_code` plus `refresh_token`, and be rate-limited.
3. Client ID Metadata Documents: the current MCP specification prefers this over new DCR. Do not advertise `client_id_metadata_document_supported` until the server implements safe HTTPS metadata fetching, exact `client_id` equality checks, redirect validation, caching, domain/trust policy, and SSRF protections. It can be added without changing the authorization-code contract.

Redirect URI rules:

- Exact string match against the registered URI. Never use prefix matching, wildcard hosts, wildcard ports, or user-supplied redirect URIs.
- Allow `https://` redirects and loopback `http://localhost`, `http://127.0.0.1`, or `[::1]` redirects for native/local Agent clients. Reject non-loopback cleartext HTTP, URI fragments, and unregistered custom schemes for the initial implementation.
- For native/dynamic clients, require `application_type=native` when the client advertises loopback redirects; remote web clients must use `application_type=web` and HTTPS.
- Bind the authorization code to `client_id`, exact `redirect_uri`, `resource`, requested/granted scope, and PKCE challenge. Codes are single-use and expire in about 60 seconds.
- The authorization response should include `iss` and the client must compare it to the issuer recorded from validated authorization-server metadata. The `state` value is generated and checked by the client, but the server must echo it unchanged.

### 5. Scope and resource authorization contract

Use small, stable scopes for Agent consent and keep workspace/entity ACLs as the final decision:

| OAuth scope | MCP tools | Required server-side checks |
|---|---|---|
| `kb:read` | `kb_list_workspaces`, `kb_list_dir`, `kb_get_tree`, `kb_search`, `kb_get_note`, `kb_get_file`, `kb_list_tags` | Token grant, workspace membership/visibility, folder root, `view` ACL |
| `kb:ask` | `kb_ask` | `kb:ask` plus `view`/`ask` ACL, folder root, workspace resource binding |
| `kb:write` | `kb_mkdir`, `kb_create_note`, `kb_update_note`, `kb_upload_file`, `kb_move`, `kb_set_tags`, `kb_delete` | `kb:write` plus `edit`/`delete`/`manage` ACL as appropriate, folder root, workspace membership |

`kb:ask` should not imply `kb:write`. `kb:write` should not imply unrestricted visibility: every operation still calls the existing `can()`/`assertCan()` path. Do not expose an `admin` MCP scope in the first version; platform/workspace administration stays in the authenticated web UI. The existing `mode: read | readwrite` can be retained as a connector compatibility field, but OAuth scopes are the authoritative tool-level gate for new grants.

The authorization screen must show the human-readable Agent/client name, the exact MCP resource URL/host, workspace, optional folder-root scope, requested scopes with read/write/ask descriptions, and expiration. If a requested scope exceeds the selected workspace/folder policy, deny or reduce it before issuing a code; do not silently grant a broader scope.

### 6. Access, refresh, and revocation strategy

Use opaque, high-entropy, database-backed tokens for this single-deployment intranet service:

- Store only SHA-256 hashes of access and refresh tokens. Show or transmit raw tokens only at issuance.
- Access tokens: 5-15 minute lifetime, bound to `client_id`, user/service principal, `resource`, workspace, optional folder root, scopes, and grant/consent ID. Resolve them on every MCP request so revocation is immediate.
- Refresh tokens: optional for clients that request long-lived access; use rotation and reuse detection. Store a token family, parent/replaced token, expiry, and revoked timestamp. On reuse of a rotated token, revoke the entire family. Do not add `offline_access` to the MCP resource metadata or `WWW-Authenticate` scopes; it is a client/AS policy choice, not an MCP resource permission.
- `POST /oauth/revoke` must accept access or refresh tokens and be idempotent. Revocation must invalidate the grant/family and therefore all newly resolved access tokens. Users should have a page to revoke individual Agent grants; admin/workspace admins can revoke service credentials and all grants scoped to their workspace.
- Revoke OAuth grants when the user is disabled/banned, when the workspace membership is removed, when a folder scope is deleted, or when an administrator explicitly revokes the Agent. Password change should invalidate interactive sessions according to Better Auth policy; it should not be the only way to revoke an Agent grant.
- Avoid logging raw authorization codes, access tokens, refresh tokens, client secrets, PKCE verifiers, or full authorization URLs. Log opaque IDs, client ID, user ID, workspace ID, scope set, result, and reason.

Recommended persistent records (names are illustrative):

- `oauth_client`: client ID, optional hashed secret, name, URI, application type, exact redirect URI list, auth method, allowed grant types, timestamps, disabled timestamp.
- `oauth_consent`/`oauth_grant`: user/service principal, client, workspace, folder root, granted scopes, resource, created/last-used/expiry/revoked timestamps.
- `oauth_authorization_code`: one-time code hash, client, redirect URI, resource, scope, user/grant, PKCE challenge/method, expiry, used timestamp.
- `oauth_access_token`: token hash, grant, resource, scope, expiry, revoked timestamp, last-used timestamp.
- `oauth_refresh_token`: rotated token hash/family, grant, expiry, replaced/revoked timestamps, reuse detection metadata.

### 7. Headless Agent/service credentials

The browser authorization link is the default for a human-operated Agent. Headless jobs need a separate administrator-issued service principal, not a copied user password and not a refresh token pasted into a script:

- An admin creates a service credential with a name, workspace, optional folder root, scopes, expiry, and optional IP/network restriction. The UI displays the secret once and stores only its hash.
- Use OAuth `client_credentials` to exchange the service credential for a short-lived access token. Do not issue a refresh token for service credentials; the job can repeat the client-credentials exchange.
- Service credentials are never tied to an individual user's interactive session. Give them an explicit service principal identity, audit trail, owner/contact, and immediate revoke/rotate controls. Workspace/entity ACL evaluation should treat the service principal as a managed actor with only its configured scope and folder root.
- Keep the existing `connector` table/API as a legacy compatibility path during migration, or migrate it into the service-principal model with a versioned credential type. New UI copy should call it `Service access` and should not encourage ordinary users to create broad keys.

### 8. Consent and user experience

The URL an Agent opens should be the standard authorization endpoint, not a custom one-time key page. The expected user path is:

1. Agent discovers the MCP resource and opens the authorization URL.
2. IMA reuses the local Better Auth browser session, otherwise displays local sign-in.
3. IMA shows a concise consent page with Agent identity, requested knowledge base/workspace, folder restriction, read/ask/write actions, and duration.
4. User approves or denies. Approval creates/updates a grant and redirects exactly once with a one-time code.
5. The Agent exchanges the code and stores tokens in its own secure storage.

Returning users can receive a pre-approved grant only when the request is an exact subset of the prior grant (same client, resource, workspace/folder, and scopes); a new write scope or broader folder must require consent again. There must be a visible `Connected Agents` page for users to revoke grants and an admin page for service credentials and workspace-level revocation.

### 9. MCP interoperability and security tests

Use the official `@modelcontextprotocol/sdk` Streamable HTTP client in automated tests, in addition to direct HTTP assertions:

1. `GET /api/mcp` without credentials returns 401, a parseable `WWW-Authenticate`, and metadata that points to the local issuer.
2. Both protected-resource well-known paths and authorization-server metadata return valid JSON with matching issuer/resource URLs.
3. DCR rejects malformed metadata, non-HTTPS/non-loopback redirects, wildcard redirects, fragments, unsupported grant/response types, and oversized redirect lists; valid native and web registrations work.
4. Authorization rejects missing/unsupported PKCE, `plain`, mismatched redirect URI, wrong client, expired/used code, wrong resource, invalid scope, and missing user consent.
5. Token exchange requires the original `code_verifier`, exact `redirect_uri`, client binding, and resource; a code can be exchanged once only.
6. Access token requests use the `Authorization` header and never query-string tokens. Wrong audience, expired, revoked, malformed, or token-from-another-issuer requests return 401.
7. `kb:read`, `kb:ask`, and `kb:write` expose only the expected tools and return 403/insufficient-scope when challenged; underlying folder ACL and entity ACL tests still pass for UI, search, RAG, download, and MCP.
8. Refresh rotation succeeds once, rejects reuse, and revokes the family on reuse. Revocation, user disable, membership removal, folder restriction changes, service rotation, and service expiry take effect on the next MCP request.
9. Service credentials can obtain client-credentials tokens but cannot use authorization-code redirect flow, receive refresh tokens, or exceed their workspace/folder/scope grant.
10. Logs, error bodies, browser history, and audit records contain no raw credential material. Production CORS and proxy headers do not weaken the token or redirect checks.

## Recommended MVP contract

Implement the following as the first standards-compliant contract:

- Local Better Auth accounts remain the only human login source; OAuth AS and MCP RS are served by the same Python backend origin after migration (the current TypeScript endpoints are the compatibility reference).
- MCP endpoint: `POST/GET /api/mcp` with Streamable HTTP and `Authorization: Bearer <oauth access token>`; keep legacy `ima_` connector keys temporarily behind an explicit compatibility switch, with a deprecation date and no new broad-key UI.
- Discovery: RFC 9728 protected-resource metadata, RFC 8414 authorization-server metadata, `WWW-Authenticate` resource metadata/scope challenge, and issuer/resource values that are stable behind Caddy.
- Human Agent connection: Authorization Code + PKCE `S256`, exact redirect URI, `state` echo, issuer validation, resource parameter in both requests, explicit local-login/consent page, one-time 60-second authorization code.
- Client registration: pre-registration plus strict RFC 7591 DCR for interoperability. Do not advertise Client ID Metadata Document support until safe SSRF/trust controls are implemented; treat CIMD as the next standards-compatibility increment rather than silently accepting arbitrary metadata URLs.
- Permissions: `kb:read`, `kb:ask`, `kb:write`; token scopes gate MCP tools, while workspace membership, folder-root limits, and `can()` ACL checks remain mandatory for every operation.
- Tokens: opaque hashed 10-minute access tokens, optional rotating refresh tokens for human Agent clients, immediate DB-backed revocation, no `offline_access` resource scope, strict resource/audience binding.
- Headless connection: admin-only service principals using `client_credentials`, one-time secret display, hashed storage, explicit workspace/folder/scope/expiry, rotation and revoke, no refresh tokens.
- Compatibility tests: official SDK handshake plus the security/interoperability matrix above; test both legacy key and OAuth paths until the key path is intentionally removed.

This contract gives an Agent a normal `Connect knowledge base` browser link while keeping the user-facing product simple: users approve an Agent's bounded access, admins manage shared model/service configuration, and no user needs to understand OAuth internals or configure a model.

## External references

- Model Context Protocol Authorization, 2026-07-28: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization
- MCP Authorization Server Discovery: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/authorization-server-discovery
- MCP Client Registration: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/client-registration
- MCP Authorization Security Considerations: https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations
- RFC 9728, OAuth 2.0 Protected Resource Metadata (April 2025): https://datatracker.ietf.org/doc/html/rfc9728
- RFC 8414, OAuth 2.0 Authorization Server Metadata: https://datatracker.ietf.org/doc/html/rfc8414
- RFC 8707, Resource Indicators for OAuth 2.0: https://datatracker.ietf.org/doc/html/rfc8707
- RFC 7009, OAuth 2.0 Token Revocation: https://datatracker.ietf.org/doc/html/rfc7009
- RFC 7591, OAuth 2.0 Dynamic Client Registration Protocol: https://datatracker.ietf.org/doc/html/rfc7591
- OAuth 2.1 draft, authorization code/PKCE/resource request guidance: https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-13
- RFC 9207, OAuth 2.0 Authorization Server Issuer Identification: https://datatracker.ietf.org/doc/html/rfc9207
- RFC 8252, OAuth 2.0 for Native Apps (loopback redirect guidance): https://datatracker.ietf.org/doc/html/rfc8252

## Related specs

- `.trellis/spec/backend/index.md` and `.trellis/spec/backend/quality-guidelines.md`: backend guidance is currently mostly template text; the implementation must add explicit security/test conventions during the migration.
- `.trellis/spec/guides/cross-layer-thinking-guide.md`: OAuth actor identity must flow consistently through HTTP routes, RAG/search/download operations, MCP tool registration, database ACLs, and the Vue client.
- `.trellis/spec/guides/code-reuse-thinking-guide.md`: reuse the existing `actorFromSession`/ACL concepts and MCP dispatch, but do not duplicate a second authorization policy in the OAuth layer.

## Caveats / Not Found

- The repository has no existing OAuth authorization-server, client-registration, authorization-code, or token tables/routes; the proposed endpoint names and table names are a design contract, not existing code.
- Better Auth is configured for local sessions, admin, and TOTP but was not verified here as a standards-compliant OAuth authorization server. Treat it as the human login/session provider and implement or select a dedicated OAuth AS component during design.
- MCP authorization specifications are versioned and the 2026-07-28 page is newer than the currently pinned SDK. Pin the target MCP specification/version in the migration design and rerun interoperability tests after upgrading the SDK.
- The MCP specification says authorization-server endpoints should be HTTPS and redirect URIs must be HTTPS or loopback. A plain HTTP intranet deployment is therefore a deployment/security exception, not the recommended contract; use Caddy TLS for real installations.
- Client ID Metadata Documents are the newer preferred registration mechanism, but safe support requires SSRF controls and trust policy. DCR remains useful for existing Agent clients and should be rate-limited and tightly validated.
- Opaque DB-backed tokens simplify immediate revocation and single-node intranet deployment. A future multi-node deployment must add shared token storage or move to signed tokens plus a revocation/introspection strategy; signed JWTs alone do not provide immediate revocation.
