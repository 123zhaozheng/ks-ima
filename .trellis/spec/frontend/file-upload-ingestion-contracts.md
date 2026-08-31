# File Upload And Ingestion Frontend Contracts

## Scope / Trigger

Apply this contract to knowledge file upload, immutable replacement, download, preview, ingestion status, retry/cancel, knowledge base switching, generated OpenAPI clients, Vue Query state, and desktop/mobile browser tests.

## Signatures

```text
src/api/knowledge-client.ts
src/composables/use-knowledge.ts
src/components/DocPreview.vue
src/components/UploadDialog.vue
src/pages/KnowledgeBase.vue
frontend/generated/openapi.json
src/api/generated/schema.ts
```

## Contracts

- Runtime DTOs come from generated OpenAPI types and all requests use the shared IMA session/CSRF transport. Components do not create local fetch clients or duplicate ticket/job/file-version types.
- Upload is enabled only from the server capability response. The flow is local SHA-256 -> upload ticket -> direct S3 PUT with `Content-Type` and Base64 `x-amz-checksum-sha256` -> Python completion -> authoritative document/ingestion refresh.
- Progress, speed-independent percentage, abort, completion, parse/chunk/embed state, retry, cancellation, unsupported, error, ready, download, and preview states are visible without claiming frontend authorization.
- Knowledge base/document changes abort active XHR and cancel scoped queries. Old knowledge base progress/history/drafts never appear in the new knowledge base.
- File replacement sends expected document version and current file version. Failed, aborted, incomplete, or `VERSION_CONFLICT` replacement preserves the current file UI/history and offers authoritative reload. Successful completion invalidates document, ingestion, and immutable history queries.
- File-version history renders only safe server fields: version, original filename, object state, and timestamp. Object keys, tickets, checksum internals, credentials, and raw errors are never rendered or persisted.
- Download and preview URLs are fetched fresh after authorization and are not written to Pinia/localStorage. Preview is shown only when the server reports it available; unsupported binary preview remains unavailable while download may still be permitted.
- Pointer, keyboard, and touch access exist for upload, replace, cancel, retry, download, preview, and history. Controls remain usable at mobile widths without overlap or horizontal page overflow.

## Validation Matrix

| Condition | Required UI/result |
|---|---|
| Storage unavailable | Upload/replace disabled with server reason; no legacy handler |
| Unsupported file before ticket | Local bounded error; no request |
| Direct PUT fails/aborts | Current version remains visible; completion not called |
| Completion/version conflict | Draft replacement retained only for recovery; authoritative reload path |
| Worker retry/cancel/failure | Safe stage status and available action; no fake ready |
| Access revoked/document deleted during upload/status | Abort/clear and unavailable state; no stale byte action |
| Knowledge base switch | Active transfer aborts; old queries/progress/history cleared |
| Preview unsupported | Safe unavailable state; download follows independent capability |

## Tests Required

1. Client/Vitest tests assert ticket parameters, Base64 checksum header, completion ordering, abort behavior, retry/cancel, query invalidation, conflict preservation, and file-version history.
2. OpenAPI generation, ESLint, `vue-tsc --noEmit`, Vitest, and sequential Quasar builds pass.
3. Desktop Chromium and mobile Chromium Playwright exercise initial upload, progress, completion, ingestion state, retry/cancel, preview/download, failed/incomplete replacement preservation, successful replacement, history advance, knowledge base switch, and no overlap/overflow.
4. Browser route fixtures are acceptable for deterministic UI behavior, but a real private S3 integration proof must separately exercise upload/checksum/HEAD/GET/delete.

## Wrong vs Correct

### Wrong

```typescript
await fetch('/api/s3/items/' + id, { method: 'PUT', body: file })
showSuccess()
```

### Correct

```text
calculate SHA-256
-> generated Python ticket request
-> signed direct PUT with required checksum header and progress/abort
-> generated completion request
-> invalidate document/ingestion/history only after verified completion
```
