# Model Governance Contracts

## Scope / Trigger

Apply this contract to Python gateway/model/profile/scene-default APIs,
encrypted model credentials, outbound probes and execution, durable health
jobs, and knowledge base workflow capabilities. Python owns every model
connection and executes every governed workflow (grounded Ask, title
generation, summarization, embedding, reranking) itself; the retired private
bridge and legacy rollback adapter have no replacement routes. Knowledge-base
profile assignments were removed: every workflow resolves exclusively from the
platform scene defaults.

## Signatures

```text
GET/POST/PATCH/DELETE /api/v1/admin/model-gateways/*
POST /api/v1/admin/model-gateways/{id}/discover|health|rotate-secret|enable|disable
GET/POST/PATCH/DELETE /api/v1/admin/governed-models/*
POST /api/v1/admin/governed-models/{id}/validate|enable|disable
GET/POST/PATCH/DELETE /api/v1/admin/capability-profiles/*
GET /api/v1/admin/scene-defaults
PUT /api/v1/admin/scene-defaults/{workflow}
GET /api/v1/knowledge-bases/{id}/capabilities
ima rotate-model-secrets plan|apply|verify|report
```

`/api/v1/internal/*` is intentionally unmounted; the edge answers a terminal
public 404. Governance routes never return gateway URL, remote model name, or
secret to the browser.

## Contracts

- Only `super_admin` and `platform_admin` mutate governance. Auditors read a
  projection without base URL, gateway/model IDs, remote name, fingerprint,
  prompt, config, CA reference, or secret-bearing infrastructure detail. They
  may read safe health state, stable reason code, latency, and timestamps.
  Knowledge base members receive business alias, description, exact version,
  and safe availability only.
- Gateway URLs accept an optional API path prefix (for example `/v1`); only
  `..` segments, credentials, queries, and fragments are rejected. Every save
  and every call uses the persisted gateway allowlist, timeout, body limit,
  TLS/CA policy, and the deployment allowlist. Without any operator allowlist,
  public addresses are reachable by default and non-global addresses fail
  closed; once hosts or CIDRs are configured, strict allowlist mode applies.
  DNS answers are checked before the call; httpx uses `trust_env=False` and
  `follow_redirects=False`. Redirects, mixed DNS, rebinding, malformed,
  oversized, timeout, and proxy paths fail closed.
- Credentials are AES-GCM envelopes with per-record AAD, versioned key ring,
  and HMAC fingerprint. Rotation is transactional and idempotent. Plaintext,
  ciphertext, authorization headers, URLs with secrets, and upstream bodies
  are absent from DTOs, logs, audit metadata, and generated artifacts.
- Workflows are exactly `grounded_ask`, `title_generation`, `summarization`,
  `embedding`, and `reranking`. Typed Pydantic configs are canonicalized;
  published profile versions are immutable and scene defaults point at the
  current published version. Model capability and embedding dimension must
  match before publish/scene-default save. Embedding vectors and rerank scores
  must contain only finite numbers.
- Availability is derived at resolve time from the scene default, profile,
  model, gateway, health, and dependency state. Disabling/revoking any
  dependency is effective on the next call. Embedding changes with target or
  legacy index dependencies return `409 REINDEX_REQUIRED`; no fake reindex
  success exists.
- Denial is terminal. Only the verified absence of a `scene_defaults` pointer
  for the workflow produces `NO_ASSIGNMENT` (409, no model call). A configured
  scene default whose profile, model, gateway, or health join is
  missing/invalid produces `UNAVAILABLE`; a failed execution join must never
  collapse into `NO_ASSIGNMENT` and must never fall back to an ungoverned call.
  Governed chat streams yield chunks progressively and close the client on
  cancellation; tool calls, reasoning, usage, warnings, file results, and
  bounded multi-step loops remain persisted by the existing chat flow.
- Governance GET reports, including embedding impact, require read capability
  but not mutation CSRF or recent authentication. Every mutation still requires
  manage capability and CSRF. Recent authentication is required for every
  mutation except the scene-default save (`PUT /admin/scene-defaults/{workflow}`),
  which is routine configuration and intentionally omits the recent-auth step.
- Health is durable Procrastinate work with retry/backoff and persisted next
  eligibility; manual checks are rate-limited.

## Validation & Error Matrix

| Condition | Required result |
|---|---|
| Public/mixed DNS, redirect, proxy, oversized/invalid upstream | Stable denied code; no target fallback |
| NaN or positive/negative infinity vector/rerank value | Stable invalid-response code; no persistence |
| Timeout or malformed upstream response | Fail closed with stable code; no target material |
| Configured scene default with a missing model/profile/gateway join | `UNAVAILABLE`; never `NO_ASSIGNMENT` or fallback |
| Unhealthy/disabled gateway or model | Immediate unavailable safe projection and execution failure |
| Stale optimistic version | 409 with no partial mutation |
| Published profile rewrite | PostgreSQL trigger rejects it |
| Wrong model capability or embedding dimension | Validation/publish/scene-default rejection |
| Embedding dependency/dimension conflict | 409 `REINDEX_REQUIRED`; no fake job |
| Secret key version missing or AAD/fingerprint mismatch | Fail closed; rotation verify reports safe record ID only |
| Stream cancellation or body limit | Upstream response closes and bounded error is returned |

## Good / Base / Bad Cases

- Good: Python resolves the workflow's exact scene-default profile version and
  executes it through the per-gateway guarded client, returning only model
  output/stream to callers.
- Base: a knowledge base whose workflow has no scene default receives a
  terminal `NO_ASSIGNMENT`; target unavailability never falls back.
- Bad: any caller receives a gateway secret, follows a redirect, uses an
  environment proxy, buffers an entire SSE response, or calls an upstream URL
  outside the guarded client.
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
3. PostgreSQL tests cover fresh/repeat migration (including the dropped
   assignment table), composite FKs, immutable versions, scene-default
   resolution, true concurrent version/disable changes, health rate limiting,
   dependencies, roles, and `REINDEX_REQUIRED`.
4. Scene-default resolution tests cover every workflow fixture, malformed or
   missing joins (`UNAVAILABLE`), absent pointers (`NO_ASSIGNMENT`), encrypted
   secrets, and redacted reports.
5. ASGI tests cover terminal denial, exact no-assignment behavior, a configured
   scene default with a broken dependency join, streamed/tool responses, and
   secret non-disclosure. Full Playwright and generated OpenAPI drift are
   required.

## Wrong vs Correct

### Wrong

```text
caller -> URL + decrypted key -> direct fetch -> upstream
```

### Correct

```text
caller -> Python model governance -> guarded Python client -> upstream
Python -> opaque result or bounded stream -> existing tool/file persistence
```
