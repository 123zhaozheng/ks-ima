# Model Governance Contracts

## Scope / Trigger

Apply this contract to Python gateway/model/profile/assignment APIs, encrypted
model credentials, outbound probes and execution, the private Bun resolver,
the read-only legacy rollback adapter, durable health jobs, and model
governance migration. Python owns every model connection. Legacy provider and
model rows are migration inputs only.

## Signatures

```text
GET/POST/PATCH/DELETE /api/v1/admin/model-gateways/*
POST /api/v1/admin/model-gateways/{id}/discover|health|rotate-secret|enable|disable
GET/POST/PATCH/DELETE /api/v1/admin/governed-models/*
POST /api/v1/admin/governed-models/{id}/validate|enable|disable
GET/POST/PATCH/DELETE /api/v1/admin/capability-profiles/*
PUT/DELETE /api/v1/admin/workspaces/{id}/profile-assignments/{workflow}
GET /api/v1/workspaces/{id}/capabilities
POST /api/v1/internal/model-governance/resolve
POST /api/v1/internal/model-governance/execute/{chat,embedding,rerank}
POST /api/v1/internal/model-governance/execute/legacy/{chat,embedding,rerank}
ima rotate-model-secrets plan|apply|verify|report
ima migrate-legacy-model-governance plan|apply|verify|report
```

Internal routes are private, constant-time token protected, excluded from
OpenAPI and Caddy, and never return gateway URL, remote model name, or secret
to the browser.

## Contracts

- Only `super_admin` and `platform_admin` mutate governance. Auditors read a
  projection without base URL, gateway/model IDs, remote name, fingerprint,
  prompt, config, CA reference, or secret-bearing infrastructure detail. They
  may read safe health state, stable reason code, latency, and timestamps.
  Workspace members receive business alias, description, exact version, and
  safe availability only.
- Gateway URLs allow only known root paths. Every save and every call uses the
  persisted gateway allowlist, timeout, body limit, TLS/CA policy, and the
  deployment allowlist. DNS answers are checked before the call; httpx uses
  `trust_env=False` and `follow_redirects=False`. Redirects, public/mixed,
  rebinding, malformed, oversized, timeout, and proxy paths fail closed.
- Credentials are AES-GCM envelopes with per-record AAD, versioned key ring,
  and HMAC fingerprint. Rotation is transactional and idempotent. Plaintext,
  ciphertext, authorization headers, URLs with secrets, and upstream bodies
  are absent from DTOs, logs, audit metadata, and generated artifacts.
- Workflows are exactly `grounded_ask`, `title_generation`, `summarization`,
  `embedding`, and `reranking`. Typed Pydantic configs are canonicalized;
  published profile versions are immutable and assignments store exact versions.
  Model capability and embedding dimension must match before publish/assignment.
  Embedding vectors and rerank scores must contain only finite numbers.
- Availability is derived at resolve time from assignment, profile, model,
  gateway, health, and dependency state. Disabling/revoking any dependency is
  effective on the next call. Embedding changes with target or legacy index
  dependencies return `409 REINDEX_REQUIRED`; no fake reindex success exists.
- Target denial is terminal. Only the verified absence of a
  `workspace_profile_assignments` row produces `NO_ASSIGNMENT` and invokes the
  named, read-only legacy adapter. An existing assignment whose profile, model,
  gateway, or health join is missing/invalid produces `UNAVAILABLE`; a failed
  execution join must never collapse into `NO_ASSIGNMENT`. The legacy adapter
  reads legacy rows in Python and uses the same guarded client; Bun never reads
  legacy credentials or calls an upstream URL directly. Chat streams yield
  chunks progressively and close the client on cancellation; tool calls,
  reasoning, usage, warnings, file results, and bounded multi-step loops remain
  persisted by the existing chat flow.
- Governance GET reports, including embedding impact, require read capability
  but not mutation CSRF or recent authentication. Every mutation still requires
  manage capability, recent authentication, and CSRF.
- Health is durable Procrastinate work with retry/backoff and persisted next
  eligibility; manual checks are rate-limited. Migration checkpoints commit per
  source record, skip an unchanged completed fingerprint, retry failures, and
  leave ambiguous/malformed/provider/model/profile/assignment mappings in
  review without guessing.

## Validation & Error Matrix

| Condition | Required result |
|---|---|
| Public/mixed DNS, redirect, proxy, oversized/invalid upstream | Stable denied code; no target fallback |
| NaN or positive/negative infinity vector/rerank value | Stable invalid-response code; no persistence |
| Missing bridge token, private-origin violation, timeout, malformed response | 404/503; no target material |
| Existing assignment with a missing model/profile/gateway join | `UNAVAILABLE`; never `NO_ASSIGNMENT` or legacy fallback |
| Unhealthy/disabled gateway or model | Immediate unavailable safe projection and execution failure |
| Stale optimistic version | 409 with no partial mutation |
| Published profile rewrite | PostgreSQL trigger rejects it |
| Wrong model capability or embedding dimension | Validation/publish/assignment rejection |
| Embedding dependency/dimension conflict | 409 `REINDEX_REQUIRED`; no fake job |
| Secret key version missing or AAD/fingerprint mismatch | Fail closed; rotation verify reports safe record ID only |
| Ambiguous legacy mapping or changed source fingerprint | `review` checkpoint; never guessed |
| Stream cancellation or body limit | Upstream response closes and bounded error is returned |

## Good / Base / Bad Cases

- Good: Python resolves an exact assigned version and executes it through the
  per-gateway guarded client, returning only model output/stream to Bun.
- Base: a workspace without a target assignment uses the Python legacy adapter
  during the rollback window; target unavailable never falls back.
- Bad: Bun receives a gateway secret, follows a redirect, uses an environment
  proxy, buffers an entire SSE response, or calls a legacy URL directly.
- Bad: a published profile is rewritten, a model capability is guessed, or an
  embedding switch claims reindex success before the ingestion owner runs it.

## Tests Required

1. Unit tests cover envelope/AAD/redaction, per-gateway policy, private CIDR,
   malformed content length, finite embedding/rerank values, progressive stream
   cancellation, profile model capability/dimension, read-vs-mutation auth, safe
   auditor health projection, and JSON dependency checks.
2. Fake-upstream tests execute discovery/chat/embedding/rerank through guarded
   httpx and cover DNS, rebinding, redirects, timeout, JSON/SSE limits, TLS/CA,
   `trust_env=False`, malformed/NaN/auth responses, and no public fallback.
3. PostgreSQL tests cover fresh/repeat migration, composite FKs, immutable
   versions, exact assignments, true concurrent version/disable changes,
   health rate limiting, dependencies, roles, and `REINDEX_REQUIRED`.
4. Migration tests cover provider/model/global/workspace/profile/assignment
   fixtures, malformed/ambiguous/mixed dimensions, repeat apply/verify,
   checkpoints/retries, encrypted secrets, and redacted reports.
5. Bun tests cover private-origin validation, opaque binding, target terminal
   denial, exact no-assignment fallback, an existing assignment with a broken
   dependency join, streamed/tool responses, and secret non-disclosure. Full
   Playwright and generated OpenAPI drift are required.

## Wrong vs Correct

### Wrong

```text
Bun resolver -> URL + decrypted key -> Bun fetch -> upstream
```

### Correct

```text
Bun -> private Python resolver/execute bridge -> guarded Python client -> upstream
Python -> opaque result or bounded stream -> Bun -> existing tool/file persistence
```
