<template>
  <div
    ref="container"
    class="pdf-preview"
    role="document"
    :aria-label="title"
    :aria-busy="loading"
    data-testid="pdf-preview"
  >
    <div
      v-if="loading"
      class="pdf-preview-status"
      role="status"
    >
      <q-spinner color="primary" />
      <span>正在加载 PDF 预览…</span>
    </div>
    <div
      v-if="error"
      class="pdf-preview-status pdf-preview-error"
      role="alert"
    >
      PDF 加载失败
    </div>
    <div
      ref="pages"
      class="pdf-preview-pages"
    />
  </div>
</template>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getDocument, GlobalWorkerOptions, type PDFDocumentProxy, type RenderTask } from 'pdfjs-dist/legacy/build/pdf.mjs'

// pdfjs-dist 4.2.67 includes the Promise.withResolvers feature test/polyfill;
// Chrome 109 intentionally takes its compatibility branch.
GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'

const props = defineProps<{
  src: string
  title?: string
}>()

const emit = defineEmits<{
  error: [error: unknown]
}>()

const container = ref<HTMLElement>()
const pages = ref<HTMLElement>()
const loading = ref(false)
const error = ref(false)

let renderId = 0
let loadingTask: ReturnType<typeof getDocument> | undefined
let pdfDocument: PDFDocumentProxy | undefined
let renderTask: RenderTask | undefined

function clearPages() {
  if (pages.value) pages.value.replaceChildren()
}

function isCurrent(id: number) {
  return id === renderId
}

function cancelRender() {
  renderId += 1
  const task = loadingTask
  const documentToDestroy = pdfDocument
  const taskToCancel = renderTask
  loadingTask = undefined
  pdfDocument = undefined
  renderTask = undefined
  if (taskToCancel) taskToCancel.cancel()
  if (task) task.destroy().catch(() => undefined)
  if (documentToDestroy) documentToDestroy.destroy().catch(() => undefined)
  clearPages()
}

async function renderPdf(src: string) {
  cancelRender()
  const id = renderId
  loading.value = true
  error.value = false
  clearPages()
  await nextTick()
  if (!src || !isCurrent(id)) {
    if (isCurrent(id)) loading.value = false
    return
  }

  const task = getDocument({
    url: src,
    isEvalSupported: false,
  })
  loadingTask = task
  try {
    const loaded = await task.promise
    if (!isCurrent(id)) return
    pdfDocument = loaded

    for (let pageNumber = 1; pageNumber <= loaded.numPages; pageNumber += 1) {
      if (!isCurrent(id)) return
      const page = await loaded.getPage(pageNumber)
      if (!isCurrent(id) || !pages.value) return

      const baseViewport = page.getViewport({ scale: 1 })
      const availableWidth = Math.max(pages.value.clientWidth - 32, 320)
      const scale = availableWidth / baseViewport.width
      const viewport = page.getViewport({ scale })
      const pixelRatio = window.devicePixelRatio || 1
      const pageElement = document.createElement('div')
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Canvas is unavailable')

      pageElement.className = 'pdf-preview-page'
      canvas.width = Math.ceil(viewport.width * pixelRatio)
      canvas.height = Math.ceil(viewport.height * pixelRatio)
      canvas.style.width = `${Math.ceil(viewport.width)}px`
      canvas.style.height = `${Math.ceil(viewport.height)}px`
      pageElement.append(canvas)
      pages.value.append(pageElement)

      const currentRenderTask = page.render({
        canvasContext: context,
        viewport: page.getViewport({ scale: scale * pixelRatio }),
      })
      renderTask = currentRenderTask
      await currentRenderTask.promise
      if (renderTask === currentRenderTask) renderTask = undefined
    }
  } catch (reason) {
    if (!isCurrent(id)) return
    await task.destroy().catch(() => undefined)
    if (!isCurrent(id)) return
    error.value = true
    emit('error', reason)
  } finally {
    if (isCurrent(id)) {
      loading.value = false
      loadingTask = undefined
      renderTask = undefined
    }
  }
}

watch(() => props.src, src => {
  renderPdf(src)
}, { immediate: true })

onBeforeUnmount(cancelRender)
</script>

<style>
.pdf-preview {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  background-color: var(--tk-surface);
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
}

.pdf-preview-pages {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--tk-space-4);
  min-width: 100%;
  padding: var(--tk-space-4);
  box-sizing: border-box;
}

.pdf-preview-page {
  flex: 0 0 auto;
  background-color: var(--tk-surface-white);
  box-shadow: var(--tk-shadow-sm);
}

.pdf-preview-page canvas {
  display: block;
}

.pdf-preview-status {
  position: absolute;
  z-index: 1;
  top: var(--tk-space-4);
  left: 50%;
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  padding: var(--tk-space-2) var(--tk-space-3);
  color: var(--tk-text-secondary);
  background-color: var(--tk-surface-white);
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  transform: translateX(-50%);
}

.pdf-preview-error {
  color: var(--tk-danger);
}
</style>
