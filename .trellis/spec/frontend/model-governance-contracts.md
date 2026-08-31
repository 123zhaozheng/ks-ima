# Model Governance Frontend Contracts

## Scope / Trigger

Apply this contract to the admin model-governance SPA, knowledge base
capability projections, per-knowledge-base assignment management, generated
OpenAPI client usage, and component or browser tests added during the central
governance cutover.

## Signatures

```text
identityClient.listModelGateways|createModelGateway|updateModelGateway
identityClient.rotateModelGatewaySecret|discoverModelGateway|checkModelGatewayHealth
identityClient.listGovernedModels|createGovernedModel|updateGovernedModel
identityClient.listCapabilityProfiles|patchCapabilityProfileDraft|publishCapabilityProfile
identityClient.listCapabilityAssignments(kbId)|assignCapabilityProfile(kbId,...)|removeCapabilityProfile(kbId,...)
identityClient.modelGovernanceImpact|kbModelCapabilities(kbId)

GET    /api/v1/knowledge-bases/{kbId}/capabilities                          # read-only business projection for members
GET    /api/v1/admin/knowledge-bases/{kbId}/profile-assignments
PUT    /api/v1/admin/knowledge-bases/{kbId}/profile-assignments/{workflow}
DELETE /api/v1/admin/knowledge-bases/{kbId}/profile-assignments/{workflow}
```

All HTTP calls use the generated schema/client and the shared CSRF/session
transport. No component-local upstream client or browser model SDK is allowed.

## Contracts

- Platform administrators get complete gateway/model/profile/assignment
  lifecycle controls. Auditors get read-only safe metadata and no rendered
  mutation controls. Ordinary knowledge base members get only alias,
  description, exact version, status, and non-secret reason.
- Gateway base URL, remote model name, gateway/model IDs, prompt, low-level
  parameters, fingerprints, credentials, health detail, and arbitrary provider
  JSON are absent from auditor/member projections. A write-only credential input
  is cleared on success, cancel, error, and route change; it is never stored in
  local/session storage or `window.prompt`.
- Admin views have loading, empty, stale/conflict, disabled, unavailable,
  validation, dependency, retry, and `REINDEX_REQUIRED` states. Every mutation
  refreshes the authoritative row and reports the safe server error.
- Profiles expose the five fixed workflows, typed configuration validation,
  draft version conflict, publish/history/diff/clone/disable/restore/delete;
  published versions are never edited in place. Assignments use exact version.
- Knowledge base capability projections
  (`identityClient.kbModelCapabilities`) are read-only business views: alias,
  workflow, exact version, status, non-secret reason — no gateway/model IDs or
  parameters. Python executes every workflow itself (grounded ask, title
  generation, summarization, embedding, reranking); there are no browser chat
  completion or title endpoints, no model selector, upstream URL, key, or
  provider object anywhere in the app. Grounded Ask responses remain
  progressive SSE through the shared bounded parser; missing per-knowledge-base
  assignment is terminal (`NO_ASSIGNMENT` 409) with no fallback.

## Validation & Error Matrix

| Condition | Required UI/result |
|---|---|
| Initial/loading/empty/unavailable health | Stable state and retry action |
| Stale gateway/model/profile/assignment version | Conflict state and reload |
| Credential create/rotation | Input-only, clear after completion, never redisplay |
| Auditor session | Safe metadata only; no mutation controls |
| `REINDEX_REQUIRED` | Affected count and next action; never fake completion |
| Target execution failure | Non-secret workflow error; no legacy fallback |
| Stream cancellation | Reader aborts and message enters a terminal error state |

## Good / Base / Bad Cases

- Good: an admin edits a typed draft, validates/publishes it, and sees the exact
  immutable version in the per-knowledge-base assignment matrix.
- Base: a knowledge base member sees only business capabilities and status badges.
- Bad: a chat selector, gateway key, remote name, prompt, arbitrary provider
  option, or credential `window.prompt` appears in browser state.
- Bad: an auditor sees disabled mutation buttons, or a failed target request
  silently invokes any provider fallback.

## Tests Required

1. Vitest mounts assert real gateway/model/profile/assignment rows, lifecycle
   interactions, conflicts, disabled/health/dependency states, auditor control
   absence, write-only secret clearing, and the safe knowledge base capability
   projection.
2. No bridge/resolver client remains: tests fail if any browser model SDK or
   component-local upstream client reappears; terminal `NO_ASSIGNMENT` and
   target-denial errors render without any fallback.
3. Playwright covers platform full lifecycle, auditor read-only, ordinary
   projection, target execution, disable/revoke, `REINDEX_REQUIRED`, desktop
   and mobile widths, with zero skips and cleanup.
4. Run generated OpenAPI drift, ESLint, `vue-tsc`, and sequential front/admin
   builds. Tests must assert concrete behavior, not component existence.

## Wrong vs Correct

### Wrong

```typescript
const model = await browserProvider(userSelectedModel, apiKey)
```

### Correct

```typescript
await groundedClient.ask(kbId, request, signal, onEvent)
// Python selects the knowledge base's assigned workflow versions and owns the connection.
```
