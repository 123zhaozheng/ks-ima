# Central Model Governance Implementation

## 1. Preflight And Security Fixtures

- Refresh CodeGraph; record every provider/model/global setting/workspace tuning,
  browser SDK, Bun gateway, price/quota, and selector caller with deletion owner.
- Add representative legacy fixtures: public/workspace providers, duplicate and
  malformed URLs/keys/models, global defaults, all RAG settings, price fields,
  missing models, mixed dimensions, and indexed chunks.
- Build a local fake OpenAI-compatible gateway for `/models`, chat, embeddings,
  and rerank plus timeout, redirect, oversized, invalid JSON/shape, auth failure,
  DNS/IP, and TLS cases. It is test infrastructure, not a production mock path.
- Add exhaustive role/secret/egress/profile/assignment/error matrices before
  implementation and update the forced PostgreSQL exact collection gate.

## 2. Additive Schema, Config, And Cryptography

- Add gateway secret/metadata/health, governed model, profile/version,
  assignment, dependency index, and migration checkpoint tables with restrictive
  FKs, versions, checks, indexes, and downgrade guard.
- Add validated key-ring/current-key, fingerprint key, host/CIDR allowlist,
  timeout/body/health policy, custom CA reference policy, and production config.
- Implement model-secret envelope service with per-record AAD, decrypt/rotate,
  safe fingerprint, recursive redaction, and `ima rotate-model-secrets
  plan|apply|verify|report`.
- Test fresh/repeat Alembic, constraints, missing/old keys, tamper/AAD failure,
  rotation idempotency, no response/OpenAPI/log/audit/coredump secret residue.

## 3. Egress Client And Health

- Implement structured base URL validation, canonical capability paths, DNS/IP
  allowlist/revalidation, HTTPS/private HTTP rules, CA/TLS, no redirects,
  `trust_env=false`, bounded pools/timeouts/body, and stable safe errors.
- Implement discovery and typed chat/embedding/rerank probes; require explicit
  capability and dimension, reject NaN/Inf/shape/size/count mismatches.
- Implement persisted manual/scheduled health with rate/backoff and no detached
  tasks. Add fake-gateway and network-security tests for every branch.

## 4. Gateway And Model Services/APIs

- Implement platform capability/auditor projections plus gateway CRUD,
  validate/health, secret set/rotate, enable/disable, optimistic conflicts,
  dependencies, audit, and safe delete.
- Implement model discovery-to-disabled-draft, CRUD, typed capability metadata,
  probe validation, enable/disable, dependency checks, and safe health state.
- Export stable OpenAPI operations/Problem Details and regenerate the one
  TypeScript schema/client. Prove workspace/ordinary requests cannot enumerate
  infrastructure and secret fields are schema-absent.

## 5. Profiles, Assignments, And Impact

- Implement five Pydantic workflow schemas, canonical serialization/digest,
  stable profile + draft, edit, clone, validate, publish, immutable history,
  diff, disable/restore, dependency-aware delete, and concurrency tests.
- Implement exact-version workspace assignment, removal, safe availability,
  admin dependency view, member business projection, and immediate lifecycle
  invalidation.
- Implement target dependency index plus read-only legacy chunk/model impact;
  reject unsafe embedding/dimension changes with `REINDEX_REQUIRED`. Document
  the later ingestion handshake and provide no reindex execution endpoint.

## 6. Admin And Workspace Vue

- Replace Bun/Zero model admin with generated Python gateway/model/profile/
  assignment/health/impact pages. Implement secret-once input/rotation,
  validation, versions/diff, dependency/reindex-required, audit links, and all
  loading/empty/error/retry/stale/disabled/unavailable states.
- Replace workspace Models/RAG editor with read-only business capabilities.
  Remove provider creation/routes/views and low-level settings.
- Remove model selects from chat/assistant/title flows; display only workflow
  availability and actionable non-secret errors. No browser model object or
  upstream URL/key exists after this step.
- Add concrete Vitest mounts and Playwright platform/auditor/workspace/ordinary
  journeys at desktop/mobile widths.

## 7. Bun Resolver And Server Cutover

- Add private Python resolve endpoint with constant-time bridge token, exact
  profile version, health/availability, and server-only gateway material.
- Add one Bun target-first resolver with deadline, no redirects, response
  validation, per-request batching, fail-closed target state, and named legacy
  fallback only when target assignment is absent.
- Switch Bun Ask, embedding, rerank, and any surviving server chat/title flow to
  the resolver. Remove `OPENAI_*` fallback and plaintext provider reads from
  routed calls. Block all legacy provider/model/tuning writes.
- Add target/legacy/denied, disabled/rotated/timeout/malformed/partial response,
  secret non-disclosure, and action-equivalence tests. Keep internal endpoint out
  of OpenAPI/Caddy.

## 8. Legacy Migration And Deletion

- Implement `ima migrate-legacy-model-governance plan|apply|verify|report` with
  safe fingerprints, source mappings, per-record checkpoints, retries,
  idempotency, disabled review drafts, encrypted secrets, strict validation, and
  ambiguous mapping input.
- Run disposable source fixtures for valid/malformed/conflicting/mixed-dimension/
  priced/public/workspace rows and repeat apply/verify. Prove no secret output.
- Delete replaced admin/workspace/provider/model/RAG/chat selector/browser SDK/
  price/quota routes, components, utilities, schemas, mutators, queries, preloads,
  localization, env keys, and dependencies. Regenerate Zero only if live legacy
  relations changed; classify every retained DB/read symbol and deletion owner.
- Update Caddy/Compose/config/operator docs and rehearse snapshot/routing rollback
  without reverse-writing decrypted secrets.

## 9. Full Security And Cross-Layer Review

- Trace create -> encrypt -> validate -> publish -> assign -> member projection ->
  Bun resolve -> upstream call -> health/audit. Verify types/errors/versions at
  every boundary and no content authorization bypass.
- Scan source, generated artifacts, built output, logs/audit/test reports/browser
  storage/history for raw/ciphertext secrets, API keys, model endpoints/names,
  prompt policy, arbitrary provider JSON, old selectors, prices/plans/quotas,
  TODO/placeholders/mocks/skips, and unowned compatibility.
- Exercise rotate/disable/revoke/assignment changes concurrently with resolution
  and prove next-call effect with transactionally consistent old-or-new versions.

## 10. Validation Commands

```text
cd backend
uv sync --frozen
uv run ruff format --check .
uv run ruff check .
uv run mypy src/ima
uv run pytest
IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest
uv run python scripts/export_openapi.py --check

cd ..
bun run generate:api
bun run lint
bunx vue-tsc --noEmit
bun test src src-server src-shared
bun run test:unit
bun run build:front
bun run build:admin
bun run build:server
bun run test:e2e
codegraph affected <model-governance source files>
```

Additional gates:

- fake upstream and DNS/redirect/proxy/TLS/body/timeout security suite;
- fresh/repeat migration, secret rotation, legacy migration repeat/verify;
- forced PostgreSQL and full Playwright collect exact required counts, zero skip;
- OpenAPI/generated/Zero drift and secret/built-output/dependency residue scans;
- isolated container/server/port/network/volume cleanup.

## 11. Executable Spec And Commit Gate

- Run `trellis-check` full-scope and fix every verified finding.
- Add backend and frontend model-governance specs with signatures, exact schemas,
  egress/secret/profile/assignment contracts, error matrices, tests, and
  wrong/correct examples.
- Re-run every affected gate after the final fix, commit implementation and specs
  separately, archive this child, record journal, then start knowledge-tree.

## 12. Rollback Point

- Preserve pre-cutover DB/deployment snapshot, encrypted target export, safe
  mapping/equivalence report, and old frontend/Bun artifact.
- Before Ask/ingestion closes the resolver fallback, rollback routes to the old
  artifact and restores the snapshot. Never export decrypted target credentials
  into legacy provider JSON.
- Legacy rows remain read-only and are removed only after fallback metrics reach
  zero, later consumers migrate, acceptance passes, and backup is verified.
