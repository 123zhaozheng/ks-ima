# Central Model Governance Design

## 1. Authority And Architecture

Python is the only mutable model-governance authority. The admin SPA uses
generated REST contracts. Workspace/user UI receives only safe business
capability projections. Bun is a temporary inference consumer over a private
resolver and cannot read/decrypt target tables directly.

```text
Admin SPA -> /api/v1/admin/model-governance/* -> Python ModelGovernanceService
                                                   |
                                                   +-> typed tables + audit
                                                   +-> encrypted secret store
                                                   +-> guarded httpx probes

Workspace SPA -> /api/v1/workspaces/{id}/capabilities -> safe projection only

Bun Ask/embed/rerank -> /api/v1/internal/model-governance/resolve
  target assignment -> exact published version + server-only gateway material
  target unavailable -> fail closed
  no migrated assignment -> named legacy read fallback during rollback window
```

Inference execution for migrated Python flows uses the same resolver directly.
No browser receives a remote URL, model name, raw prompt policy, or credential.

## 2. Module Boundaries

```text
backend/src/ima/domain/model_governance.py
backend/src/ima/application/model_governance.py
backend/src/ima/application/legacy_model_governance.py
backend/src/ima/infrastructure/model_gateway/client.py
backend/src/ima/infrastructure/model_gateway/egress.py
backend/src/ima/infrastructure/model_gateway/secrets.py
backend/src/ima/api/v1/model_governance.py
backend/src/ima/api/v1/model_governance_contracts.py
backend/src/ima/api/internal/model_governance_bridge.py
```

Domain/application modules do not import FastAPI or frontend DTOs. The
infrastructure client owns DNS/egress, TLS, size, redirect, and timeout controls.
API adapters own CSRF/recent-auth and Problem Details mapping. Legacy migration
uses the established CLI/checkpoint pattern and never becomes runtime policy.

## 3. Data Model

All tables are in `ima`, use UTC timestamps, explicit checks/FKs/indexes, and
monotonic versions.

- `model_gateway_secrets`: UUID, key version, AES-GCM nonce+ciphertext, HMAC
  fingerprint, timestamps/rotator. Separate from gateway metadata and never
  selected by list/detail DTOs.
- `model_gateways`: UUID, name/normalized base URL, enabled, TLS mode/custom CA
  ref, insecure-private flag, allowed capabilities, timeout fields, secret ref,
  version, lifecycle/audit timestamps.
- `model_gateway_health`: gateway, capability, state, stable reason, latency,
  checked/next-eligible times, consecutive failures. No body/error string.
- `governed_models`: UUID, gateway, remote name, capability, business label,
  enabled/validated state, chat/context/output limits or embedding dimension or
  rerank limits, version/timestamps. Unique by gateway/name/capability.
- `capability_profiles`: UUID, workflow, business alias/description, lifecycle,
  current version counter, version/timestamps.
- `capability_profile_versions`: profile+version primary key, state
  (`draft|published|disabled`), typed JSON configuration validated by workflow,
  immutable publish metadata and safe config digest.
- `workspace_profile_assignments`: workspace+workflow primary key, profile ID,
  exact profile version, version, assigned actor/time, availability snapshot.
- `model_dependency_index`: typed external dependencies discovered before later
  domain tables exist: target/legacy index, active job, answer/version reference,
  source ID, model/profile identity, dimension. It is updated by owning children
  and migration verification, not treated as a second source of business data.
- `legacy_model_governance_migration`: source kind/id, fingerprint, mapped target,
  status/attempt/error/timestamps.

Published profile versions and historical assignment references use restrictive
FKs. Deletes are application-level and refuse dependencies; disabling preserves
history. JSON profile configuration is schema-validated and canonicalized, not
an arbitrary extension bag.

## 4. Secret Envelope And Key Ring

Configuration supplies a key ring and current version, for example a secret
JSON mapping `{"v1":"...","v2":"..."}` plus `v2`. Each secret record stores:

```text
nonce || AESGCM(key[v]).encrypt(raw, aad="model-gateway:<gateway-id>:<secret-id>")
fingerprint = HMAC(fingerprint_key, raw)[:12]
```

Creation/rotation decrypts nothing outside the service call. Previous secret
records are retained only as bounded rotation audit metadata without reusable
plaintext. The CLI scans current records, decrypts with their version,
re-encrypts with current version transactionally per record, verifies roundtrip,
and supports repeat/report. Missing key versions fail closed.

`SecretStr`, redaction, response DTO exclusion, OpenAPI scans, and recursive log
tests enforce non-disclosure. Fingerprints support operator comparison but are
not password hashes or authentication credentials.

## 5. Egress And Gateway Client

At save time and before every network call:

1. parse with a structured URL parser;
2. allow only `https`, or explicitly marked `http` under the configured private
   allowlist/test policy;
3. reject userinfo, query, fragment, unknown ports, and non-root base paths that
   would escape known capability URL construction;
4. resolve every A/AAAA answer and require each IP/host to match the deployment
   host/CIDR allowlist; reject rebinding/public/mixed answers;
5. construct known `/models`, `/chat/completions`, `/embeddings`, `/rerank`
   targets without string-concatenating untrusted paths;
6. call one `httpx.AsyncClient(trust_env=False, follow_redirects=False)` with
   validated CA/TLS, bounded pool/connect/read/write timeout and response size;
7. revalidate the connected target where transport hooks permit and reject all
   redirects regardless of destination.

The fake-upstream suite supplies valid/malformed/slow/oversized/redirecting
responses. Gateway exceptions are mapped to stable safe codes; response bodies,
keys, and URLs with sensitive material are not logged.

## 6. Models And Probes

`/models` discovery yields names only. An administrator creates a disabled draft
model with explicit capability and metadata, then runs its capability probe:

- chat: fixed harmless prompt, bounded output, valid response/usage shape;
- embedding: fixed input, nonempty numeric finite vector, exact configured
  dimension, bounded batch/result;
- rerank: fixed query/two documents, valid indices/scores, bounded result.

Probe success stores validation digest/time and safe health. Any material remote
name/capability/dimension/gateway change invalidates validation. Enabled models
can be published only while gateway and capability probe are acceptable.
Scheduled health uses the durable task runner with rate limits and backoff; the
admin API can enqueue/perform one bounded manual check without detached tasks.

## 7. Profile Schemas And Publication

Use Pydantic discriminated workflow contracts and canonical JSON:

- `grounded_ask`: chat model, optional embedding/rerank, prompt, retrieval mode,
  top K, vector weight, score threshold, context/output/generation/timeouts;
- `title_generation`: chat model, bounded prompt/output/timeout;
- `summarization`: chat model, bounded prompt/context/output/timeout;
- `embedding`: embedding model, batch/token/timeouts and immutable dimension;
- `reranking`: rerank model, candidate/result limits and timeout.

Draft editing increments the draft version row's optimistic version but not the
semantic profile version. Publish locks profile/models/gateways, validates every
reference and bound, assigns the next semantic version once, stores a digest,
and makes the row immutable. Clone copies safe configuration to the next draft;
it never copies secrets. Diff operates on canonical typed fields.

## 8. Assignment, Resolution, And Impact

Assignment locks workspace, profile version, current assignment, health, and
dependency rows. It requires a published/active compatible workflow. A profile
version is never resolved through “latest”; the exact version is stored.

Availability is derived at read/resolve time from assignment + profile + models
+ gateways + health + embedding migration state. Member DTO:

```json
{
  "workflow": "grounded_ask",
  "alias": "Internal knowledge Q&A",
  "description": "Answers from approved workspace sources",
  "version": 3,
  "status": "available",
  "reason": null
}
```

The impact query joins target assignments/dependency index and performs a
read-only scan of known legacy chunk/model settings during coexistence. A new
embedding model/dimension with affected indexed data returns 409
`REINDEX_REQUIRED`, including safe affected counts/IDs for platform admins only.
The later ingestion service records a completed compatible index generation,
after which reassignment is permitted.

## 9. APIs And Authorization

```text
GET/POST/PATCH/DELETE /api/v1/admin/model-gateways/*
POST /api/v1/admin/model-gateways/{id}/validate|rotate-secret|health
GET/POST/PATCH/DELETE /api/v1/admin/governed-models/*
POST /api/v1/admin/governed-models/{id}/validate|enable|disable
GET/POST /api/v1/admin/capability-profiles/*
PATCH /api/v1/admin/capability-profiles/{id}/draft
POST /api/v1/admin/capability-profiles/{id}/clone|publish|disable
GET /api/v1/admin/capability-profiles/{id}/versions|diff
GET/PUT/DELETE /api/v1/admin/workspaces/{id}/profile-assignments/{workflow}
GET /api/v1/admin/model-governance/impact
GET /api/v1/workspaces/{id}/capabilities

POST /api/v1/internal/model-governance/resolve  # private, server material
```

Public admin contracts return safe metadata only. Sensitive mutations require
active session, exact Origin/CSRF, recent auth, optimistic version, and platform
capability. Auditors use distinct read-only metadata endpoints/response
projections. Workspace capability list uses active membership but not folder
content permission and contains no infrastructure identity.

## 10. Frontend Information Architecture

Platform administration uses dense tabs/pages:

- Gateways: lifecycle, safe endpoint metadata, secret presence/fingerprint,
  validation/health, rotate, dependency-aware delete;
- Models: capability, limits/dimension, validation/health, enable/disable;
- Profiles: workflow list, typed draft editor, validation, publish, version
  history/diff, dependencies;
- Assignments: workspace/workflow matrix, availability, impact/reindex-required;
- Audit links and stable errors/loading/empty/retry/conflict states.

Workspace settings replaces editable Models/RAG content with a read-only
Capabilities section. Chat/assistant views show workflow availability and clear
unavailable errors, not a model select. No credential, remote name, prompt, or
parameter is rendered.

## 11. Bun Compatibility And Deletion

The Bun helper batches/caches only within one request and sends workspace +
workflow + operation to the private resolver. The response contains gateway
material only inside Bun, never via a browser route. Timeout/token/malformed/
unavailable target results fail closed. A response explicitly indicates
`target`, `legacy`, or `denied`; target denial cannot fall through.

After cutover, delete or disable all provider/model/RAG writes in Zero/Bun.
Remove browser SDK inference and model selectors immediately after existing user
chat routes resolve the server workflow. Read-only legacy gateway resolution is
retained only for workspaces without target assignments until Ask/ingestion
migration; it has metrics/equivalence tests and final cutover deletion ownership.

## 12. Migration And Rollback

`ima migrate-legacy-model-governance` inventories first and requires an operator
mapping file for ambiguous capability/profile translations. Apply commits one
source record/checkpoint, encrypts secrets immediately, creates disabled drafts,
and records mappings. Repeat apply is idempotent; verify proves exact mapping,
relationships, decryptability, review state, assignments, and redaction.

Rollout:

1. additive schema/key ring/allowlist and target admin APIs;
2. import disabled drafts, validate/publish/assign via admin workflow;
3. deploy private resolver and target-first Bun server consumers;
4. deploy user/admin UI cutover and block legacy writes;
5. remove replaced browser/workspace/admin code and monitor fallback counts;
6. keep legacy tables/read adapter for later Ask/ingestion rollback window.

Rollback before final content cutover restores previous frontend/Bun artifact
and pre-cutover DB snapshot. Secrets are never reverse-written from target
ciphertext into legacy JSON. Additive migration downgrade refuses target rows
without an explicit verified snapshot.

## 13. Trade-offs

- A single compatible protocol is less flexible than arbitrary provider plugins,
  but it makes egress, secrets, health, and validation reviewable.
- Immutable published versions create more rows but make jobs/answers auditable.
- Refusing embedding switches before real reindex is less convenient than a fake
  button; it preserves vector correctness and ownership boundaries.
- A bounded Bun resolver is temporary complexity required by the migration
  order. Target-first semantics prevent it becoming a second authority.
