# Doc preview: fix probabilistic load failure and remove the PDF grey canvas

## Problems (reported by the product owner)

1. **"Opening a knowledge base previews the first document, but sometimes it just
   doesn't load."** — intermittent blank/failed preview.
2. **"What is that grey border around the file, can we get rid of it?"** — a thick dark
   grey frame surrounds the white page in the preview pane (screenshot confirms
   `#808080`), which looks broken next to the app's light design tokens
   (`--tk-bg: #f7f8fa`, `--tk-surface: #f1f3f5`, `--tk-border: #e6e8ec` in
   `src/styles/tokens.css:10-18`).

## Root causes (already investigated — do not re-investigate from scratch)

### A. Probabilistic preview failure

`src/components/DocPreview.vue`:

- **Missing `immediate` on the preview watcher** (`~529-549`). The document-title watcher
  has `{ immediate: true }`, but the watcher that starts the preview does not:
  ```ts
  watch(document, value => {
    if (value?.kind === 'file' && !previewUrl.value) reloadPreview()
  })
  ```
  Vue Query `staleTime` is 30s (`src/boot/vue-query.ts:7`). On a **cache hit**, `document`
  already has a value before the watcher registers, so the callback never fires and
  `preview()` is never requested. PDF/text then falls through to "preview unavailable";
  Office falls through to an empty container. This is the main source of the
  "sometimes" behaviour — cold cache works, warm cache fails.
- **No request-race protection** (`~536-555`, `~654-665`). `loadPreviewUrl()` never passes
  the `AbortSignal` that `knowledgeClient.preview()` already accepts
  (`src/api/knowledge-client.ts:36-37`), and never checks whether the response still
  belongs to the current `props.documentId`. A late response from document A can
  overwrite (or blank out) the preview of document B. `renderOffice()` (`~559-595`) has
  the same flaw.
- **Default selection does not check previewability** (`src/pages/KnowledgeBase.vue:509-516`)
  — it only skips folders (`items.find(item => item.kind !== 'folder')`), so an
  unverified/unsupported first item deterministically fails to preview.
  Backend truth: `backend/src/ima/application/storage.py:291-294` returns `FILE_NOT_READY`
  for non-verified objects and `PREVIEW_UNAVAILABLE` for non-inline MIME;
  inline types are text/PDF/images only (`storage.py:36-46`).

### B. The grey frame is Chrome's built-in PDF viewer

PDFs are handed to a bare `<iframe :src="previewUrl">` (`DocPreview.vue:291-296`) with an
inline-disposition presigned URL (`backend/src/ima/infrastructure/storage.py:76-93`), so
Chrome's native PDF viewer renders it and paints its own `#808080` canvas **inside** the
iframe. Parent CSS cannot cross that boundary — `.doc-preview-iframe`
(`DocPreview.vue:801-808`) only contributes a 1px `--tk-border`.

`pdfjs-dist` is already a dependency (`package.json:40`) and
`public/pdf.worker.min.mjs` already ships, so rendering PDFs in-app is the supported fix.

## Goal

Preview loads deterministically on first open (cold or warm cache), never shows a stale
document's content, and PDFs render on the app's own light surface with no grey canvas.

## Requirements

1. Make the preview start reliably: single source of truth for "current document →
   load preview", with `{ immediate: true }`.
2. Add race protection: `AbortController` + request-identity check (document id and/or
   monotonic request id) for both `loadPreviewUrl()` and `renderOffice()`; abort on
   document switch and on unmount.
3. Render PDFs with `pdfjs-dist` into an app-controlled container (reuse
   `public/pdf.worker.min.mjs`) instead of a bare iframe, so the surface uses design
   tokens. Keep a sensible fit-to-width rendering and support multi-page scrolling.
4. Default-selection in `KnowledgeBase.vue` should prefer a genuinely previewable
   document; when the chosen document is not previewable, show the explicit
   "preview unavailable" state rather than an indefinite/blank load.
5. Add a real loading state while the presigned URL / PDF is being fetched, and a
   retry affordance on failure (`query.refetch()` for metadata errors).
6. Fix the shadowed Office error branch: `v-else-if="officeFormat"` (`~297-323`) precedes
   the failure branch (`~325-347`), so Office render failures never show the error state.
   Gate it on `officeFormat && !previewFailure`.

## Non-goals

- Rewriting the Office (docx/xlsx) rendering pipeline.
- Changing the backend preview/presign contract.
- A full PDF toolbar (zoom controls, search, print) — out of scope for this pass;
  fit-to-width + scroll is enough.

## Acceptance criteria

- Vitest covers: warm-cache open still requests the preview; a late response for a
  previous document does not overwrite the current one; Office failure surfaces the
  error state.
- Manually verifiable: opening a knowledge base with a PDF as the first document shows
  the PDF on a light surface with **no** `#808080` frame.
- `bun lint`, `bun type-check`, `bun vitest run` pass.

## Key files

- `src/components/DocPreview.vue` (main)
- possibly new `src/components/PdfPreview.vue`
- `src/pages/KnowledgeBase.vue` (default selection)
- `src/api/knowledge-client.ts` (pass through the signal)
- `src/styles/tokens.css` (surface tokens; do not invent new greys)
- `tests/components/DocPreviewHeader.vitest.ts` (extend)
