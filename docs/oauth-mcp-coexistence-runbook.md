# OAuth MCP Coexistence, Sunset, and Rollback

## Current Routing

- Publish `https://<public-origin>/mcp` as the only preferred resource and token audience.
- During coexistence, `/api/mcp` keeps routing to the retained Bun handler with existing legacy connector semantics. It is not an OAuth resource or token audience.
- The disabled-by-default Python `/api/mcp` compatibility alias is reserved for an explicitly approved post-legacy routing change. Do not enable or route it while legacy keys remain active.
- OAuth, well-known metadata, `/api/v1/oauth/*` grant administration, and `/mcp` route to Python before generic `/api/*` handling.
- `/api/v1/internal/*` remains public `404`.

## Inventory and Classification

Run the read-only report:

```powershell
cd backend
uv run ima inventory-legacy-mcp report
```

The deterministic JSON output contains connector ID, mode, folder-scope presence, and classification. It omits workspace names/IDs, connector names, last-use timestamps, key hashes, and raw keys. Create an operator-reviewed JSON file whose unique keys are connector IDs and whose values are only `reissued` or `revoked`:

```json
{
  "connector-id": "reissued"
}
```

`reissued` means an administrator separately approved and issued a finite Python service principal. It does not mean the legacy creator or key was converted. `revoked` means the old connector is already revoked/expired or the operator explicitly chose retirement.

```powershell
uv run ima inventory-legacy-mcp apply --mapping-file .\approved-mcp-decisions.json --operator-id <super-admin-user-id>
uv run ima inventory-legacy-mcp verify --mapping-file .\approved-mcp-decisions.json
```

Verification emits the report and exits with code `4` when any row remains pending. Invalid input exits `2`; an unauthorized apply exits `3`. `apply` requires an existing `super_admin`, writes only safe count telemetry attributed to that user in the same database transaction, and never mutates `public.connector`. Read-only report/verify still assumes authorized operating-system and database access; do not publish their output.

## Pre-Sunset Rollback

Before a deployment rollback, exercise the repository's real root `Caddyfile`
against the pinned official Caddy image:

```powershell
bun run test:caddy-routing
```

The command creates only uniquely named ephemeral containers, random host-port
mappings, local marker upstreams, and a temporary configuration directory. It
first validates the current config on both public listeners, then uses official
`caddy adapt` output to derive a separate temporary pre-sunset rollback JSON
where canonical `/mcp` is withdrawn with a local `404`, and finally restores and
revalidates the unmodified root `Caddyfile`. Cleanup runs after success, failure,
or cancellation and targets only the containers created by that invocation.

Retain the deterministic JSON output with the release evidence. It records the
resolved `caddy:2.10.2-alpine` repository digest, root Caddyfile SHA-256, route
status, and marker destination. This is safe configuration metadata; it contains
no connector key, OAuth token, upstream credential, database identifier, or
protected content. The drill proves only local routing shape and reversible
pre-sunset configuration behavior. It does not deploy a rollback, modify the
production Caddyfile, exercise legacy connector authorization semantics, prove
external client interoperability, or authorize post-sunset recovery.

Perform these steps in order:

1. Record and verify the retained Bun image digest, Caddy/configuration checksum, database snapshot identifier and checksum, PostgreSQL recovery point, and secret-version identifiers without recording secret values.
2. Confirm `/api/mcp` still reaches the retained Bun handler and that only clients already holding an active legacy key/configuration are eligible to use it. Never derive or reconstruct a legacy key for a new OAuth client.
3. Route those eligible clients back to the retained `/api/mcp` behavior.
4. Disable or withdraw the canonical Python `/mcp` route in the deployment/Caddy configuration.
5. Verify legacy initialize, `tools/list`, read/write mode, expiry, root denial, and revocation semantics.
6. Leave all additive `ima.mcp_*` schema and audit rows intact. Never reconstruct, convert, or copy a raw credential.

## Sunset Gate

- Inventory verification has no pending connector.
- Every active consumer has a newly approved service credential or an explicit revocation record.
- Canonical OAuth discovery and official Python SDK interoperability evidence is accepted.
- A fresh database snapshot and exact previous deployment image/configuration are recorded.
- Sunset approval explicitly authorizes removing the compatibility route. This child task does not perform that removal.

## Post-Sunset Recovery

After compatibility credentials or code are deleted, do not attempt a mixed rollback. Stop public traffic, restore the identified pre-cutover database snapshot to its recorded recovery point, deploy the matching image and configuration checksums, validate the legacy route privately, and only then reopen traffic. A prior deployment against a post-sunset database is not supported.

## Evidence Not Claimed Here

This runbook and inventory do not claim Cursor, Claude Desktop, or other external-client acceptance. Record those results only after executing the real client matrix against the deployed public origin.
The local Caddy routing drill likewise does not replace that deployed public-origin
matrix, retained Bun image verification, database snapshot/PITR evidence, or the
operator-approved inventory and sunset gates above.
