# Central Model Governance

## Goal

Make Python the sole model-configuration authority for the intranet assistant.
Platform administrators must be able to configure safe intranet gateways,
encrypted credentials, capability-specific models, immutable business profile
versions, health, and workspace assignments without exposing infrastructure to
ordinary users. Existing RAG/model consumers must continue through a narrow
server-side compatibility bridge while user/workspace provider configuration,
browser inference, per-chat model choice, price/plan logic, and replaced code are
removed.

## Background

- Python already owns identity, platform roles, workspaces, authorization, audit,
  and the private Bun bridge. `platform_admin` may manage infrastructure but has
  no implicit workspace-content permission.
- Current model authority is fragmented across public Bun admin models,
  workspace provider entities, Zero workspace settings, plaintext provider JSON,
  environment fallbacks, browser AI SDK construction, and Bun RAG gateway calls.
- CodeGraph shows `gatewayForModel` feeds Bun Ask, embedding, and rerank;
  `toSdkModel` feeds browser streaming/title generation; `ModelSelect` consumes
  workspace/public Zero rows. All are affected by this cutover.
- The parent migration contract removes commercial plans, price/quota behavior,
  per-user/provider configuration, and model selection. It retains centralized
  business workflows and server-side inference.
- Durable document/vector reindex execution depends on the later ingestion
  child. This task must implement impact detection and refuse unsafe embedding
  switches; it must not claim an unimplemented reindex succeeded.

## Requirements

### R1. Platform Authority And Visibility

- Only active `super_admin` or `platform_admin` users may create, mutate,
  validate, rotate, publish, assign, disable, or delete model configuration.
  `security_auditor` may read safe gateway/model/profile/health/assignment audit
  metadata but cannot mutate or view secrets, prompts, remote headers, or raw
  low-level configuration.
- Workspace administrators and ordinary members receive only assigned business
  workflow alias, description, version, and `available|degraded|unavailable`
  state. They cannot read gateway URLs, gateway/model IDs, remote model names,
  secrets/fingerprints, prompts, temperatures, token limits, top K, thresholds,
  vector weights, chunk parameters, headers, proxy, or TLS details.
- Platform roles still do not imply knowledge-content access. Model
  administration and content authorization remain separate application services
  and audit capabilities.
- No public API, OpenAPI document, frontend state, log, audit, metric label, MCP
  output, or error contains a raw/ciphertext credential or decrypted provider
  configuration.

### R2. Gateway And Secret Lifecycle

- Support one target gateway protocol: OpenAI-compatible chat/embeddings plus a
  typed `/rerank` extension. Ollama is supported through its OpenAI-compatible
  endpoint; arbitrary browser provider plugins or provider-specific option JSON
  are not target features.
- Gateway configuration includes name, normalized base URL, enabled state,
  allowed capabilities, bounded connect/read/write/pool timeouts, TLS policy,
  optional administrator-managed custom CA reference, and health state. It does
  not accept credentials embedded in URLs, query/fragment values, arbitrary
  request headers, redirects, or an arbitrary proxy URL.
- Production HTTPS is required. HTTP is accepted only for explicitly allowlisted
  private/test destinations under an administrator-visible insecure flag. The
  deployment allowlist constrains exact hosts and/or CIDRs. DNS is revalidated
  before calls; any public, loopback, link-local, multicast, unspecified, or
  otherwise non-allowlisted resolution is rejected unless that literal target
  is explicitly configured for the environment.
- Gateway calls set `trust_env=false`, reject redirects, enforce response/body
  limits, use known capability paths only, and never fall back to a public model
  endpoint or a global API key.
- Credentials use AES-GCM envelope encryption with per-record nonce/AAD and a
  versioned deployment key ring. Create/rotate accepts the raw secret once;
  persistence keeps ciphertext plus safe HMAC fingerprint. APIs return only
  `secretPresent` and a short stable fingerprint. Master-key rotation supports
  decrypt-old/re-encrypt-current through an idempotent CLI with verification.
- Gateway create, edit, validate, enable/disable, credential rotate, master-key
  re-encrypt, and dependency-checked delete are complete, audited, versioned,
  and protected by CSRF/recent authentication where sensitive.

### R3. Model Registry And Health

- A model belongs to one gateway and one capability: `chat`, `embedding`, or
  `rerank`. The unique key is gateway + remote name + capability. Models have a
  business label, enabled state, version, safe limits, and capability-specific
  validated metadata; no input/output price, free/public flag, plan, or quota.
- Chat models validate context/output limits and a bounded non-stream probe.
  Embedding models require a positive immutable dimension confirmed by a probe.
  Rerank models validate a bounded document/query probe and result shape.
- Gateway discovery may import `/models` names into disabled draft model rows;
  discovery never enables a model or infers capability. Administrators explicitly
  choose capability and validate before enablement/profile publication.
- Manual and scheduled health checks persist safe timestamps, latency,
  `healthy|degraded|unavailable|unknown`, and stable error codes. They do not
  store response bodies, prompts, vectors, rankings, authorization material, or
  upstream exception strings. Repeated probes are bounded and rate-limited.
- Disabling a gateway/model immediately makes dependent workflow resolution
  unavailable. Destructive edits/deletes are rejected while any published
  profile version, assignment, index, job, or answer dependency exists.

### R4. Capability Profiles

- Implement stable capability profiles with immutable numbered versions and
  workflows `grounded_ask`, `title_generation`, `summarization`, `embedding`,
  and `reranking`. Stable records contain business alias/description/lifecycle;
  versions contain selected models and typed workflow configuration.
- Draft versions are editable and cannot be assigned. Publishing validates
  gateway/model health, required capabilities, dimensions, prompt/parameter
  bounds, and dependency rules in one transaction. Published versions are
  immutable; changes clone a new draft version. A published version may be
  disabled but not silently rewritten or reused under another semantic meaning.
- `grounded_ask` owns chat model, optional embedding/rerank models, system prompt,
  retrieval mode/top K/vector weight/threshold, context and output limits,
  timeouts, and safe generation settings. The other workflows expose only the
  smaller typed subset they need. Arbitrary prompt/provider JSON is forbidden.
- Profiles and versions support create, clone, edit draft, validate, publish,
  disable/restore where safe, dependency-checked delete, version history, safe
  diff, and audited lifecycle. Secret values are never copied into a profile.

### R5. Workspace Assignment And Availability

- Platform administrators assign one published profile version per workspace +
  workflow. Workspace administrators cannot assign or request a lower-level
  model. Assignment mutations are versioned, audited, and validate active
  workspace/profile/dependencies atomically.
- A canonical resolver returns the exact published version and safe availability
  for a workspace/workflow. Jobs, answers, and compatibility calls bind the
  resolved version so later profile publication does not rewrite history.
- Public member responses expose business alias/description/version and safe
  availability/reason only. Missing assignment, disabled gateway/model/profile,
  unhealthy required capability, or pending embedding migration yields a clear
  non-secret unavailable/degraded state.
- Before changing an embedding model/dimension, an impact API reports affected
  workspace assignments and existing target/legacy indexes. If indexed data is
  present, assignment is rejected with a typed `REINDEX_REQUIRED` conflict. The
  durable-ingestion child owns the real reindex job and will consume this
  contract; this task provides no fake button/success path.
- Admin views include assignments, availability, affected workspaces/indexes,
  dependency reasons, and the next safe action. Workspace settings show assigned
  business workflows read-only.

### R6. Server-Side Consumption And Coexistence

- Add one private, constant-time bridge for Bun to resolve an effective
  workspace/workflow into server-only gateway material. It is absent from Caddy
  and OpenAPI, validates the existing bridge credential, applies a short
  deadline, returns no value for inactive/unavailable assignments, and never
  exposes secrets to the browser.
- Switch current Bun Ask, embedding, rerank, and any temporary server chat/title
  consumers to target-first profile resolution. An existing target assignment,
  including unavailable/denied state, is authoritative. Only a workspace without
  a migrated target assignment may use a named read-only legacy fallback during
  the rollback window.
- All new gateway/model/profile/assignment writes use Python. Legacy provider,
  model, global setting, and workspace tuning rows become read-only migration
  inputs; old Bun/Zero mutation routes fail closed after cutover.
- Remove ordinary-user and workspace-admin provider/model pages, gateway secret
  inputs, RAG tuning, reindex controls without an implementation owner, per-chat
  and assistant model selectors, and browser AI SDK/provider construction.
  Existing user workflows resolve an administrator-assigned profile server-side.
- Remove public/free model proxy behavior, price/cost/plan/quota decisions, global
  public API key fallbacks, arbitrary provider options/tools/headers, and unused
  dependencies/localization. Every retained legacy model field/table has a live
  read-only migration/rollback consumer and final deletion milestone.

### R7. Legacy Migration, Audit, And Operations

- Implement `ima migrate-legacy-model-governance plan|apply|verify|report` with
  per-record fingerprints/checkpoints, safe resumability, idempotency, and no
  secret output. It inventories public/workspace providers, models, global
  defaults, workspace model/RAG settings, and malformed/conflicting rows.
- Imported gateways/models/profiles are disabled drafts pending administrator
  validation. Compatible secrets are encrypted immediately; URLs, capabilities,
  dimensions, prompts, or settings are never guessed. Equivalent records may be
  deduplicated only by normalized non-secret fields plus safe credential
  fingerprint, with source-to-target mapping recorded.
- Verify source/target counts, mapping, encryption/decryption under the current
  key, disabled-review state, model capability metadata, profile translation,
  workspace assignment, and absence of secret values in report/log/audit.
- Audit all gateway/model/profile/assignment/health/secret/migration events with
  safe IDs, versions, result/reason, latency buckets, and affected counts only.
  Operator docs cover key-ring generation/rotation, allowlist, custom CA,
  validation, health, migration, dependency conflicts, rollback, and emergency
  disablement without manual SQL.

### R8. Completeness And Quality

- Add unit, forced-PostgreSQL, network-security, fake-gateway, migration,
  concurrency, OpenAPI/generated-client, component, Bun bridge, and full
  Playwright tests. Required PostgreSQL/browser tests may not skip.
- Use a local fake upstream to prove URL parsing, DNS/IP allowlist, no redirects,
  `trust_env=false`, timeout/body limits, secret/header redaction, discovery,
  capability probes, health transitions, and no public fallback.
- Test platform/admin/auditor/workspace-admin/ordinary role boundaries;
  gateway/model/profile/version/assignment lifecycle; secret/master-key rotation;
  dependencies; immediate disablement; impact conflicts; migration repeat and
  verify; target-first Bun consumption; user UI removal and read-only aliases.
- No accepted feature is complete with a TODO, placeholder, mock-only production
  path, skipped required test, hard-coded success, undocumented manual SQL,
  plaintext secret, duplicate mutable authority, or unowned compatibility code.

## Acceptance Criteria

- [ ] AC1 (`R1`): Platform admins can fully govern model infrastructure while
      auditors see safe metadata and workspace/ordinary users cannot discover
      gateway, model, secret, prompt, or low-level settings through API/UI/logs.
- [ ] AC2 (`R2`): Gateway URL/egress/TLS/timeout/redirect controls block public or
      non-allowlisted destinations and never use environment proxy/public
      fallback; fake-upstream security tests prove every branch.
- [ ] AC3 (`R2`): Gateway credentials and master-key rotation are encrypted,
      versioned, once-displayed/input-only, fingerprinted safely, immediately
      effective, auditable, and absent from every public/diagnostic surface.
- [ ] AC4 (`R3`): Chat/embedding/rerank discovery, explicit capability metadata,
      probes, health transitions, disablement, and dependency-checked deletion
      work end to end without prices/plans/quotas.
- [ ] AC5 (`R4`): All five workflows have typed draft/publish/clone/history/diff/
      disable/delete behavior; published versions are immutable and invalid or
      unhealthy configurations cannot publish.
- [ ] AC6 (`R5`): Versioned workspace assignments and canonical availability
      resolve only published active configurations; members see business aliases
      and safe status only, while assignment/history keep exact version identity.
- [ ] AC7 (`R5`): Embedding model/dimension impact identifies target and legacy
      indexes and refuses unsafe assignment with `REINDEX_REQUIRED`; no fake
      reindex success exists before the ingestion owner implements execution.
- [ ] AC8 (`R6`): Bun Ask/embed/rerank/server inference uses the private
      target-first resolver, target unavailability fails closed, and only truly
      unmigrated workspaces use the tested read-only legacy fallback.
- [ ] AC9 (`R6`): Workspace/user provider and tuning surfaces, per-chat/assistant
      model choice, browser AI SDK execution, plaintext keys, public/free model
      and price/cost/quota logic, and replaced mutations/dependencies are removed
      or retained solely as classified read-only migration data.
- [ ] AC10 (`R7`): Legacy model governance plan/apply/repeat/verify/report is
      resumable and idempotent, imports safe disabled drafts/mappings, reports
      malformed data without guessing, and never emits secret material.
- [ ] AC11 (`R7`): Admin gateway/model/profile/health/assignment/impact views and
      workspace read-only capability view cover loading, empty, validation,
      health, conflict, dependency, unavailable, retry, and audit states.
- [ ] AC12 (`R8`): Ruff, mypy, full/forced PostgreSQL, OpenAPI generation/drift,
      ESLint, `vue-tsc`, Bun/Vitest, front/admin/server builds, full Playwright,
      secret/residue scans, and isolated test resource cleanup all pass.

## Out Of Scope

- Actual durable document upload/parsing/chunking/vector reindex jobs; the
  object-storage/durable-ingestion child implements them against this task's
  impact and version contracts.
- Final Python search/RAG/conversation/SSE implementation; this task keeps the
  existing Bun server consumer operational through a bounded private resolver.
- User-selectable models, provider credentials, prompt/RAG tuning, public model
  marketplace/fallback, cost/billing/quota, arbitrary provider plugins/headers,
  public-network gateways, or per-workspace infrastructure ownership.
- GPU scheduling, local model process management, fine-tuning, prompt A/B tests,
  automatic model benchmarking, multi-region failover, or dynamic public egress.
