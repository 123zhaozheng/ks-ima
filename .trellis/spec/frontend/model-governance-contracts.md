# Model Governance Frontend Contracts

## Scope / Trigger

Apply this contract to the admin model-governance SPA, workspace capability
settings, chat/title requests, generated OpenAPI client usage, and component or
browser tests added during the central governance cutover.

## Signatures

```text
identityClient.listModelGateways|createModelGateway|updateModelGateway
identityClient.rotateModelGatewaySecret|discoverModelGateway|checkModelGatewayHealth
identityClient.listGovernedModels|createGovernedModel|updateGovernedModel
identityClient.listCapabilityProfiles|patchCapabilityProfileDraft|publishCapabilityProfile
identityClient.listCapabilityAssignments|assignCapabilityProfile|removeCapabilityProfile
identityClient.modelGovernanceImpact|workspaceCapabilities
POST /api/v1/chat/completions
POST /api/v1/chat/titles
```

All HTTP calls use the generated schema/client and the shared CSRF/session
transport. No component-local upstream client or browser model SDK is allowed.

## Contracts

- Platform administrators get complete gateway/model/profile/assignment
  lifecycle controls. Auditors get read-only safe metadata and no rendered
  mutation controls. Ordinary/workspace users get only alias, description,
  exact version, status, and non-secret reason.
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
- Workspace settings are read-only business capabilities. Chat and title flows
  send messages/tools to server workflows and never include a model selector,
  upstream URL, key, or provider object. Server responses remain progressive
  SSE; the existing bounded tool loop persists tool results, files, reasoning,
  usage, warnings, and cancellation/errors.

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
  immutable version in the assignment matrix.
- Base: a workspace member sees only business capabilities and status badges.
- Bad: a chat selector, gateway key, remote name, prompt, arbitrary provider
  option, or credential `window.prompt` appears in browser state.
- Bad: an auditor sees disabled mutation buttons, or a failed target request
  silently invokes legacy fallback.

## Tests Required

1. Vitest mounts assert real gateway/model/profile/assignment rows, lifecycle
   interactions, conflicts, disabled/health/dependency states, auditor control
   absence, write-only secret clearing, and safe workspace projection.
2. Bun tests assert opaque resolver payloads, private bridge origin, target
   denial, exact no-assignment fallback, streamed responses, tools, and secret
   absence.
3. Playwright covers platform full lifecycle, auditor read-only, ordinary
   projection, target execution, disable/revoke, `REINDEX_REQUIRED`, desktop
   and mobile widths, with zero skips and cleanup.
4. Run generated OpenAPI drift, ESLint, `vue-tsc`, and sequential front/admin/
   server builds. Tests must assert concrete behavior, not component existence.

## Wrong vs Correct

### Wrong

```typescript
const model = await browserProvider(userSelectedModel, apiKey)
```

### Correct

```typescript
await managedChat(workspaceId, messages)
// Python selects the fixed assigned workflow and owns the connection.
```
