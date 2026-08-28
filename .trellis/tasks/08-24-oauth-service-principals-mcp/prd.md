# OAuth Service Principals and MCP

## Goal

Deliver a Python-owned, standards-interoperable MCP protected resource that lets
interactive desktop and browser agents access the target knowledge service through
OAuth 2.1 Authorization Code with PKCE S256 and lets workspace administrators
issue deliberately bounded credentials for unattended automation. Both paths
must call the existing target application services and dynamically enforce the
approving user's or delegated grant's current target authorization.

## Requirements

### Product boundary

- The canonical protected resource is the public HTTPS URL `<IMA_PUBLIC_ORIGIN>/mcp`.
  It is the sole audience/resource identifier for every new access token and
  metadata document. `/api/mcp` may coexist temporarily as a legacy transport
  alias, but it must advertise/use the canonical `/mcp` resource and must not
  create a second audience or new OAuth contract.
- Python/FastAPI owns OAuth, bearer validation, service-principal administration,
  rate/concurrency enforcement, audit, target-service MCP adaptation, and the
  official Python MCP SDK Streamable HTTP transport. MCP tools contain no
  direct SQL, S3, Bun KB, or duplicate ACL implementation.
- Only target-backed operations are exposed. MCP calls `WorkspaceService`,
  `KnowledgeService`, `StorageService`, and `SearchService` as applicable; it
  must never read legacy KB data or fall back to Bun, Zero, public search,
  legacy chat, or a public model provider.
- The complete supported tool surface is target parity where service contracts
  exist: workspace/directory/tree/document/tag reads, target search and Ask,
  and versioned mkdir, create/update note, bounded file upload, move, tag, and
  trash-delete mutations. File retrieval uses target metadata/content and a
  short-lived authorized download mechanism; larger uploads use the target
  upload-ticket flow. Permanent delete is excluded.

### Interactive OAuth

- Publish RFC 9728 protected-resource metadata and OAuth authorization-server
  metadata at public HTTPS well-known paths. The unauthenticated MCP response
  returns `401` with a Bearer `resource_metadata` challenge pointing to the
  canonical metadata. Metadata identifies the canonical `/mcp` resource,
  issuer, authorization/token/revocation endpoints, supported scopes, S256,
  and pre-registration-only client policy.
- Support only pre-registered clients in the MVP. Validate a registered,
  enabled client, its exact redirect URI, permitted client/authentication type,
  requested canonical resource, and supported scope. Do not implement or
  advertise dynamic client registration, implicit, password, device, or client
  ID metadata-document flows. Public desktop clients have no client secret.
- Use Authorization Code with mandatory `code_challenge_method=S256`. The
  authorization request requires client ID, exact redirect URI, state, PKCE
  challenge, resource, and valid requested scope. Codes are short-lived,
  one-time, opaque pepper-digested records bound to client, redirect URI,
  resource, user, grant, scope, workspace/folder boundary, PKCE challenge, and
  current user security state. The token endpoint requires and consumes the
  matching verifier atomically.
- Require explicit consent before a first grant or an expanded client/resource/
  workspace/folder/scope/duration request. Consent displays the exact client,
  resource, workspace, folder restriction, actions/scopes, write capability,
  expiry, and refresh behavior. A browser session alone never grants access.
  A prior grant may suppress consent only for an exact eligible subset.
- Define scopes as `mcp:workspaces:read`, `mcp:knowledge:read`,
  `mcp:knowledge:search`, `mcp:knowledge:ask`, and `mcp:knowledge:write`.
  Scope controls tool discovery and use; it never bypasses active membership,
  archived-workspace checks, folder root, dependent ACL actions, version
  concurrency, or target object lifecycle.
- Access, refresh, and authorization-code values are high-entropy opaque values
  stored only as pepper digests. Issue short-lived access tokens and rotating
  refresh tokens for approved desktop interoperability. Refresh can preserve
  or reduce, never broaden, resource, workspace, folder, or scope. Atomic
  rotation records token family/lineage and replay revokes the whole family.
  Revocation is idempotent and immediate on the next token or MCP request.

### Service principals

- Service principals are MVP constrained delegated grants, not user identities
  or first-class target ACL subjects. A workspace administrator explicitly
  approves their workspace, optional folder root, scopes, owner/purpose,
  lifecycle, mandatory finite expiry, optional validated network policy, and
  rate/concurrency policy. Their grant must be no broader than the administrator
  approval and is intersected with current target ACL policy at each call.
- Create a high-entropy, one-time-displayed credential with a nonsecret key ID
  and prefix. Store only its pepper digest, metadata, lifecycle/expiry,
  last-use, audit identity, and replacement lineage. Never store, log, audit,
  return later, or persist the raw secret in browser storage.
- Credentials exchange only for short-lived resource-bound access tokens; they
  receive neither user authorization-code flow nor refresh tokens. Rotation
  creates a replacement atomically and revokes the prior credential by default;
  any configured operational overlap is finite, explicit, auditable, and cannot
  outlive policy limits. Disable/revoke/expiry takes effect on the next request.
- Enforce network policy only from a trusted source address supplied through the
  Caddy/ASGI trusted-proxy configuration. Enforce token and MCP limits per
  principal/credential and source bucket, return `429` on policy exhaustion,
  and do not use an untrusted forwarded header.

### HTTP, error, audit, and user interface

- Caddy explicitly routes `/mcp`, optional legacy `/api/mcp`, OAuth endpoints,
  and well-known metadata to Python before generic `/api/*` handling. Public
  `/api/v1/internal/*` remains `404`; bridge routes, Docker names, database
  paths, and private credentials are never exposed.
- OAuth endpoints return standards-compatible OAuth errors without raw secrets.
  MCP bearer failure returns `401`; authenticated insufficient-scope or policy
  denial returns the required Bearer challenge/error, while hidden target
  content retains target-safe non-disclosure behavior. API errors otherwise use
  RFC 9457 Problem Details with stable safe codes and correlation IDs.
- Audit safe grant/consent/code/token/refresh/revoke, principal/credential
  lifecycle, policy/rate/network denials, legacy deprecation, and every MCP
  tool allow/deny. Logs, audit, metrics, error bodies, browser history, and UI
  state exclude codes, tokens, verifiers, client secrets, authorization headers,
  service secrets, search/Ask text, and protected content.
- Provide a Python-session-protected Vue consent route/page and connected-agent
  revoke view. Provide distinct workspace administration for interactive
  connection guidance and service-principal creation/list/detail/rotate/revoke.
  Use generated OpenAPI DTOs and the central cookie/CSRF client; no bearer,
  refresh, code, or service secret persists in browser storage. Handle loading,
  expired-session, access-revoked, validation, conflict, one-time-secret,
  rotation, rate/network, and error states.

### Migration and operations

- Add target-owned OAuth and service-principal tables only in `ima`; do not
  change, write, silently transform, or treat `public.connector` as authority.
  The legacy connector endpoint may remain only through an announced temporary
  coexistence period with its existing semantics. New principals/clients do not
  create legacy connector rows.
- Publish the OAuth `/mcp` endpoint as preferred. Inventory legacy connector
  consumers, configuration UI/copy, tests, and copied client configurations;
  emit safe deprecation telemetry/audit. Before sunset, explicitly migrate by
  issuing a new approved credential or revoke/report each old key. Never infer
  a service principal from legacy creator impersonation or recover a raw key.
- Pin the official Python MCP SDK version after confirming FastAPI-compatible
  Streamable HTTP and stateless behavior. Pin a tested MCP/OAuth specification
  revision and rerun interoperability tests whenever either protocol dependency
  changes.
- Maintain an operational rollback path during coexistence: retain legacy
  routing/service and a database/deployment snapshot until post-cutover
  acceptance. After credential sunset/deletion, rollback requires the approved
  snapshot and prior deployment, not a mixed credential conversion.

## Observable Acceptance Criteria

- [ ] A direct unauthenticated request to `/mcp` returns `401` with a parseable
      Bearer `resource_metadata` challenge. Both metadata documents expose only
      canonical public HTTPS issuer/resource values; the resource is `/mcp`,
      S256 is advertised, and no DCR/implicit/password/client-metadata flow is
      advertised.
- [ ] A pre-registered public desktop client completes local login, explicit
      consent, exact redirect with state/issuer, authorization-code exchange
      using PKCE S256, and official-SDK MCP initialization without a manually
      copied bearer secret. Missing/plain/wrong PKCE, wrong client/redirect/
      resource, expired/reused code, invalid scope, and inactive browser state
      are rejected safely.
- [ ] Consent and re-consent display and record the exact client, canonical
      resource, workspace, folder root, scopes, write indication, duration, and
      refresh behavior. A first or expanded request prompts; only an eligible
      subset avoids a prompt; denial returns an OAuth-safe error.
- [ ] Access tokens are opaque pepper-digested, canonical-resource-bound, and
      short-lived. Refresh tokens rotate atomically, allow only equal-or-narrower
      grants, and revoke their family on reuse. Token/grant/client/user disable,
      workspace archive, membership removal, ACL change, or explicit revoke
      blocks the next MCP call.
- [ ] Service-principal issuance requires finite expiry and explicit workspace,
      scopes, and delegated folder policy. The secret is visible exactly once,
      is pepper-digested at rest, exchanges only for a short-lived token, never
      obtains refresh/user flows, and rotation/revoke/disable/expiry/network/
      rate policy deny use immediately or at the documented finite boundary.
- [ ] Tools/list and calls expose only the scopes allowed by an interactive grant
      or principal. Every read/search/Ask/write call exercises target services
      and current target ACLs, respects folder roots and version fields, and has
      no legacy/public fallback. A current ACL or lifecycle denial does not leak
      hidden content.
- [ ] Caddy sends only intended public MCP/OAuth/discovery routes to Python,
      preserves generic legacy routing only while declared, and returns public
      `404` for `/api/v1/internal/*`. Trusted-proxy tests prove spoofed
      forwarded addresses cannot bypass network policy.
- [ ] Vue consent and administration journeys use generated contracts, never
      retain secret material, and cover browser/session expiry, denial,
      validation/conflict, one-time credential display, rotate/revoke, and
      access-revoked states at desktop and mobile widths.
- [ ] Migration tests prove new tables are isolated to `ima`, legacy connector
      behavior remains unchanged during coexistence, and the sunset runbook
      reports every legacy credential as explicitly reissued or revoked. The
      rollback drill restores the documented old route/deployment before sunset.
- [ ] The exact backend, PostgreSQL, Caddy, Vue, protocol, SDK interoperability,
      privacy/redaction, concurrency/revocation-race, legacy coexistence, and
      rollback tests named in `implement.md` pass with no skipped security gate.

## Out of Scope

- Dynamic client registration, client ID metadata documents, implicit/password/
  device grants, JWT/JWKS issuance, token introspection for external consumers,
  and public OAuth identity federation.
- First-class service-principal ACL subjects, service-principal-created ACL
  entries, unmanaged/perpetual credentials, public Internet MCP exposure, MCP
  client/marketplace features, and permanent deletion by MCP.
- Replacing or deleting the legacy connector implementation before the named
  migration/sunset acceptance gate.
