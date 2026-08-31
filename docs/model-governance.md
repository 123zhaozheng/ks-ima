# Central Model Governance Operations

Python is the only writer and executor for model gateways, credentials,
governed models, capability profiles, health and per-knowledge-base
assignments. Gateway material stays server-side; the browser never receives it.
The private Bun bridge that existed during coexistence was removed with the
legacy deletion release.

## Key Ring

Generate a deployment key ring and fingerprint key in the secret manager, then
set `IMA_MODEL_KEY_RING`, `IMA_MODEL_CURRENT_KEY_VERSION`, and
`IMA_MODEL_FINGERPRINT_KEY` on the Python API, worker, and migration container.

Preview and perform envelope rotation:

```text
ima rotate-model-secrets plan
ima rotate-model-secrets apply
ima rotate-model-secrets verify
```

Rotation is idempotent and fails closed when an old key version is unavailable.
The commands never print plaintext or ciphertext.

## Egress

Gateways use one OpenAI-compatible protocol: `/models`, `/chat/completions`,
`/embeddings`, and `/rerank`. Configure exact `IMA_MODEL_ALLOWED_HOSTS` and/or
`IMA_MODEL_ALLOWED_CIDRS`. HTTPS is required in production. Private HTTP needs
both an administrator-created `insecurePrivate` gateway and
`IMA_MODEL_ALLOW_INSECURE_PRIVATE=true`.

The client disables environment proxies, follows no redirects, rejects URL
credentials/query/fragment/path escapes, resolves DNS before every call, and
limits timeout and response size. Do not add arbitrary headers or proxy URLs.

## Lifecycle

1. Create a disabled gateway and enter its credential once.
2. Discover names, create disabled models with explicit capability and (for
   embeddings) dimension, validate, then enable.
3. Create typed workflow Profile drafts, publish immutable versions, and assign
   exact versions to active knowledge bases
   (`PUT /api/v1/admin/knowledge-bases/{kbId}/profile-assignments/{workflow}`).
   A knowledge base without an assignment fails terminally (`NO_ASSIGNMENT`,
   409) — there is no legacy adapter fallback.
4. Review health and impact before embedding changes. `REINDEX_REQUIRED` is a
   hard conflict until the later ingestion child records a compatible index.
5. Disable immediately for an incident; delete only after dependency checks pass.

## Legacy Import And Rollback

> Historical: the `ima migrate-legacy-model-governance` importer was removed
> and the compatibility `public.*` tables were dropped with the legacy deletion
> release (Alembic migration `20260829_0011_legacy_schema_removal`). The text
> below documents how import and rollback-window behavior worked before the
> cutover; it is closure evidence, not live operations.

```text
ima migrate-legacy-model-governance plan
ima migrate-legacy-model-governance apply
ima migrate-legacy-model-governance verify
ima migrate-legacy-model-governance report
```

For legacy models whose capability or embedding dimension cannot be proven from
the source row, provide an operator-owned mapping file through
`IMA_MODEL_GOVERNANCE_MAPPING` (for example `{ "model-id": { "capability":
"embedding", "dimension": 1536 } }`). Missing or invalid mappings remain
`review` checkpoints; the importer never guesses.

Malformed or ambiguous provider settings become disabled review checkpoints.
Compatible credentials are encrypted immediately. Legacy rows are read-only;
they are never reverse-written from target ciphertext. During the rollback
window only a knowledge base with no target assignment may use the named
legacy adapter. A target denial is terminal.

The old `public.provider`, `public.model`, `public.globalSettings`,
`public.plan`, `public.planPrice`, `public.order`, and usage/quota columns remain
in the compatibility schema only because the knowledge-tree and final
legacy-cleanup children still own their data migration. No current model route,
seed, job, or mutator writes provider/model/price/plan/quota state. The final
cleanup child must remove these tables and generated relations after the
rollback window and verify migration checkpoints before dropping them.

Before final cutover preserve the database snapshot, encrypted target export,
mapping/equivalence report, and previous Bun/frontend artifacts. Rollback routes
to the previous artifact and snapshot without exporting decrypted credentials.
