<template>
  <div
    class="doc-preview"
    flex="~ col"
    min-h-0
    h-full
  >
    <div
      class="doc-preview-header"
      flex
      items-center
      gap-1
      px-3
      py-2
    >
      <q-btn
        flat
        dense
        round
        icon="sym_o_close"
        title="关闭"
        aria-label="关闭"
        data-testid="doc-close-button"
        @click="$emit('close')"
      />
      <q-input
        v-model="title"
        borderless
        dense
        class="doc-preview-title"
        input-class="text-subtitle1"
        :readonly="!document || readonly"
        :disable="!document"
        @update:model-value="dirty = true"
      />
      <q-space />
      <q-btn
        v-if="!readonly"
        flat
        dense
        round
        color="primary"
        icon="sym_o_save"
        title="保存"
        aria-label="保存"
        data-testid="doc-save-button"
        :loading="saving"
        :disable="!document || !dirty"
        @click="save"
      />
      <q-btn
        flat
        dense
        round
        icon="sym_o_chat"
        title="询问"
        aria-label="询问"
        :disable="!document"
        data-testid="doc-ask-button"
        @click="askAboutDocument"
      />
      <q-btn
        flat
        dense
        round
        icon="sym_o_download"
        title="下载"
        aria-label="下载"
        data-testid="doc-download-button"
        :disable="!document"
        @click="download"
      />
      <q-btn
        flat
        dense
        round
        icon="sym_o_more_vert"
        title="更多"
        aria-label="更多"
        data-testid="doc-more-button"
      >
        <q-menu
          anchor="bottom right"
          self="top right"
        >
          <q-list min-w="160px">
            <q-item
              v-if="document?.kind === 'file' && !readonly"
              clickable
              :disable="!document || query.isError.value || replacing"
              @click="replacementInput?.click()"
            >
              <q-item-section avatar>
                <q-icon name="sym_o_upload_file" />
              </q-item-section>
              <q-item-section>替换</q-item-section>
            </q-item>
            <q-item
              v-if="document?.kind === 'note' && !readonly"
              clickable
              :disable="!document"
              @click="toggleMode"
            >
              <q-item-section avatar>
                <q-icon :name="mode === 'edit' ? 'sym_o_visibility' : 'sym_o_edit'" />
              </q-item-section>
              <q-item-section>
                {{ mode === 'edit' ? '预览' : '编辑' }}
              </q-item-section>
            </q-item>
            <q-item
              clickable
              :disable="!document"
              @click="showHistory = true"
            >
              <q-item-section avatar>
                <q-icon name="sym_o_history" />
              </q-item-section>
              <q-item-section>历史</q-item-section>
            </q-item>
            <q-item
              v-if="document?.kind === 'file'"
              clickable
              :disable="!document"
              @click="reloadPreview"
            >
              <q-item-section avatar>
                <q-icon name="sym_o_refresh" />
              </q-item-section>
              <q-item-section>预览</q-item-section>
            </q-item>
            <q-item
              v-if="!readonly"
              clickable
              class="text-negative"
              :disable="!document"
              data-testid="doc-delete-button"
              @click="confirmDelete"
            >
              <q-item-section avatar>
                <q-icon name="sym_o_delete" />
              </q-item-section>
              <q-item-section>删除</q-item-section>
            </q-item>
          </q-list>
        </q-menu>
      </q-btn>
      <input
        ref="replacementInput"
        type="file"
        accept=".txt,.md,.markdown,.json,.pdf,.docx,.xlsx,.xls"
        hidden
        @change="replaceFile"
      >
    </div>
    <div
      px-3
      flex="~ col"
      gap-2
    >
      <q-banner
        v-if="query.isError.value"
        rounded
        class="bg-negative text-white"
      >
        该文档不可用，或访问权限已被撤销。
      </q-banner>
      <q-banner
        v-if="conflict"
        rounded
        class="kb-banner-warning"
      >
        该文档已在别处被修改。你的草稿仍保留在这里。
        <template #action>
          <q-btn
            flat
            dense
            label="重新加载服务器版本"
            @click="reloadServerVersion"
          />
        </template>
      </q-banner>
      <div
        v-if="document?.kind === 'file' && document.fileState === 'ready'"
        class="kb-ingest-inline"
      >
        <span class="kb-ingest-ready">
          <q-icon
            name="sym_o_task_alt"
            size="14px"
          />
          已就绪，可被检索
        </span>
        <span class="kb-ingest-version">版本 {{ document.currentContentVersion }}</span>
      </div>
      <q-banner
        v-else-if="document?.kind === 'file' && document.fileState"
        rounded
        class="kb-banner-info"
      >
        <div
          flex
          items-center
          gap-1
          flex-wrap
        >
          <span
            class="kb-ingestion-status"
            :style="{ color: bannerView.color }"
          >
            <q-icon
              :name="bannerView.icon"
              size="16px"
            />
            {{ bannerView.label }}{{ document.fileState === 'ready' ? '，可被检索' : '' }}
          </span>
          <template v-if="document.fileState !== 'ready' && ingestion">
            <span
              v-for="job in ingestion.jobs"
              :key="job.stage"
              :style="{ color: jobStatusColor(job.status) }"
            >
              {{ stageLabel(job.stage) }} · {{ jobStatusLabel(job.status) }}
            </span>
          </template>
        </div>
        <template #action>
          <q-btn
            v-if="ingestion?.jobs.some(job => ['queued', 'running', 'retryable', 'cancel_requested'].includes(job.status))"
            flat
            dense
            label="取消"
            @click="cancelIngestion"
          />
          <q-btn
            v-if="ingestion?.jobs.some(job => ['failed', 'dead_letter', 'cancelled'].includes(job.status))"
            flat
            dense
            label="重试"
            @click="retryIngestion"
          />
        </template>
      </q-banner>
    </div>
    <div
      v-if="query.isLoading.value"
      flex
      flex-1
      items-center
      justify-center
    >
      <q-spinner color="primary" />
    </div>
    <div
      v-else-if="document?.kind === 'file'"
      class="doc-preview-file"
      flex="~ col"
      gap-2
      flex-1
      min-h-0
      px-3
      pb-3
    >
      <div
        v-if="replacing"
        flex
        items-center
        gap-2
      >
        <q-linear-progress
          :value="replacementProgress"
          color="primary"
          size="8px"
          class="flex-1"
        />
        <q-btn
          flat
          dense
          round
          icon="sym_o_cancel"
          title="取消"
          @click="abortReplacement"
        />
      </div>
      <div
        v-if="document.fileState !== 'ready'"
        class="text-caption text-on-sur-var"
      >
        版本 {{ document.currentContentVersion }}
      </div>
      <iframe
        v-if="previewUrl"
        :src="previewUrl"
        class="doc-preview-iframe"
        :title="document.title"
      />
      <div
        v-else-if="officeFormat"
        class="doc-preview-office"
        flex-1
        min-h-0
        of-y-auto
      >
        <div
          v-if="officeRendering"
          flex
          items-center
          justify-center
          p-6
        >
          <q-spinner color="primary" />
        </div>
        <div
          v-if="officeHtml"
          class="md-body doc-preview-sheet"
          v-html="officeHtml"
        />
        <div
          v-show="!officeHtml"
          ref="officeContainer"
          class="doc-preview-office-host"
        />
      </div>
      <div
        v-else-if="previewFailure === 'error'"
        flex
        flex-1
        items-center
        justify-center
      >
        <pane-empty-state
          icon="sym_o_visibility_off"
          title="预览加载失败"
        >
          <template #actions>
            <q-btn
              flat
              no-caps
              class="tk-btn-secondary"
              icon="sym_o_refresh"
              label="重试"
              data-testid="doc-preview-retry"
              @click="reloadPreview"
            />
          </template>
        </pane-empty-state>
      </div>
      <div
        v-else-if="!previewLoading"
        flex
        flex-1
        items-center
        justify-center
      >
        <pane-empty-state
          icon="sym_o_visibility_off"
          title="暂不支持预览"
          description="该文件已成功处理并可被检索，但当前格式无法在浏览器中预览。"
        >
          <template #actions>
            <q-btn
              flat
              no-caps
              class="tk-btn-secondary"
              icon="sym_o_download"
              label="下载文件"
              @click="download"
            />
          </template>
        </pane-empty-state>
      </div>
    </div>
    <div
      v-else-if="document?.kind === 'note' && mode === 'edit'"
      class="doc-preview-editor"
      flex="~ col md:row"
      gap-3
      flex-1
      min-h-0
      px-3
      pb-3
    >
      <q-input
        v-model="markdown"
        type="textarea"
        outlined
        autogrow
        class="doc-preview-editor-input flex-1"
        input-class="font-mono"
        :disable="!document"
        @update:model-value="dirty = true"
      />
      <div
        class="doc-preview-editor-render md-body"
        flex-1
        of-y-auto
        p-3
        rounded
        v-html="draftHtml"
      />
    </div>
    <div
      v-else-if="document?.kind === 'note'"
      class="doc-preview-render md-body"
      of-y-auto
      flex-1
      min-h-0
      px-4
      py-3
      v-html="renderedHtml"
    />
    <q-dialog v-model="showHistory">
      <q-card min-w="320px">
        <q-card-section class="text-h6">
          历史
        </q-card-section>
        <q-list v-if="document?.kind === 'file'">
          <q-item
            v-for="version in fileVersions.data.value?.items"
            :key="version.version"
          >
            <q-item-section>
              <q-item-label>版本 {{ version.version }}</q-item-label>
              <q-item-label caption>
                {{ version.originalFilename }} · {{ version.objectState }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              {{ new Date(version.createdAt).toLocaleString() }}
            </q-item-section>
          </q-item>
        </q-list>
        <q-list v-else>
          <q-item
            v-for="version in versions.data.value"
            :key="version.version"
            clickable
            @click="restore(version.version)"
          >
            <q-item-section>版本 {{ version.version }}</q-item-section>
            <q-item-section side>
              {{ new Date(version.createdAt).toLocaleString() }}
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </q-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import DOMPurify from 'dompurify'
import { Notify, useQuasar } from 'quasar'
import PaneEmptyState from 'src/components/PaneEmptyState.vue'
import { useFileVersions, useKnowledgeDocument, useKnowledgeIngestion, useKnowledgeMutations, useKnowledgeVersions } from 'src/composables/use-knowledge'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { useAskContextStore } from 'src/stores/ask-context'
import { apiErrorMessage } from 'src/utils/api-error'
import { fileStateView, jobStatusColor, jobStatusLabel, stageLabel, terminalStatusView } from 'src/utils/ingestion-status'
import { renderMarkdown } from 'src/utils/markdown'

const props = withDefaults(defineProps<{
  documentId: string
  startInEdit?: boolean
  highlight?: string
  readonly?: boolean
}>(), { startInEdit: false, highlight: undefined, readonly: false })

const emit = defineEmits<{
  close: []
  deleted: []
}>()

const router = useRouter()
const $q = useQuasar()

const query = useKnowledgeDocument(() => props.documentId)
const ingestionQuery = useKnowledgeIngestion(() => props.documentId)
const ingestion = computed(() => ingestionQuery.data.value)
const versions = useKnowledgeVersions(() => props.documentId)
const fileVersions = useFileVersions(() => props.documentId)
const document = computed(() => query.data.value)
const statusView = computed(() => fileStateView(document.value?.fileState))
const bannerView = computed(() => terminalStatusView(
  document.value?.fileState,
  (ingestion.value?.jobs ?? []).map(job => job.status),
) ?? statusView.value)

const title = ref('')
const markdown = ref('')
const mode = ref<'read' | 'edit'>('read')
const dirty = ref(false)
const saving = ref(false)
const showHistory = ref(false)
const conflict = ref(false)
const previewUrl = ref<string>()
// Local substitute for the removed failure toast: 'unsupported' = the format
// cannot render in a browser (PREVIEW_UNAVAILABLE), 'error' = transient,
// retryable.
const previewFailure = ref<'unsupported' | 'error'>()
const previewLoading = ref(false)

// Office formats render in-page from the authorized bytes (see task
// 09-12-kb-light-file-preview); the backend preview endpoint only serves
// browser-native formats (PDF/images/text), so these never call it.
type OfficeFormat = 'docx' | 'xlsx' | 'pptx'
const OFFICE_MIMES: Record<string, OfficeFormat> = {
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.ms-excel': 'xlsx',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',
}
const officeFormat = computed<OfficeFormat | undefined>(() => {
  const mime = document.value?.mimeType
  return mime ? OFFICE_MIMES[mime] : undefined
})
const officeContainer = ref<HTMLElement>()
const officeHtml = ref<string>()
const officeRendering = ref(false)
const replacementInput = ref<HTMLInputElement>()
const replacementProgress = ref(0)
const replacing = ref(false)
let replacementAbort: AbortController | undefined
const mutations = useKnowledgeMutations()

watch(document, value => {
  if (!value || dirty.value) return
  title.value = value.title
  markdown.value = value.markdown ?? ''
}, { immediate: true })

// Opening another document resets draft state; new notes land in the editor.
watch(() => props.documentId, () => {
  abortReplacement()
  dirty.value = false
  conflict.value = false
  previewUrl.value = undefined
  previewFailure.value = undefined
  officeHtml.value = undefined
  if (officeContainer.value) officeContainer.value.innerHTML = ''
  mode.value = props.startInEdit ? 'edit' : 'read'
}, { immediate: true })

watch(document, value => {
  if (value?.kind === 'file' && !previewUrl.value) reloadPreview()
})

function reloadPreview() {
  const format = officeFormat.value
  if (format) renderOffice(format)
  else loadPreviewUrl()
}

// Fetches the authorized bytes (presigned download URL) and renders Office
// formats in-page. Renderers load lazily so the main bundle stays unchanged.
async function renderOffice(format: OfficeFormat) {
  if (!document.value) return
  officeRendering.value = true
  previewFailure.value = undefined
  try {
    const { url } = await knowledgeClient.download(document.value.id)
    const res = await fetch(url)
    if (!res.ok) throw new Error(`download failed: ${res.status}`)
    const bytes = await res.arrayBuffer()
    if (format === 'xlsx') {
      const XLSX = await import('xlsx')
      const workbook = XLSX.read(bytes, { type: 'array' })
      const firstSheet = workbook.SheetNames[0]
      if (!firstSheet) throw new Error('empty workbook')
      officeHtml.value = DOMPurify.sanitize(XLSX.utils.sheet_to_html(workbook.Sheets[firstSheet]))
      return
    }
    const container = officeContainer.value
    if (!container) return
    container.innerHTML = ''
    if (format === 'docx') {
      const { renderAsync } = await import('docx-preview')
      await renderAsync(bytes, container)
      return
    }
    const { init } = await import('pptx-preview')
    const previewer = init(container, {
      width: container.clientWidth || 960,
      height: container.clientHeight || 540,
    })
    await previewer.preview(bytes)
  } catch {
    previewFailure.value = 'error'
  } finally {
    officeRendering.value = false
  }
}

const renderedHtml = computed(() => renderMarkdown(document.value?.markdown ?? '', props.highlight))
const draftHtml = computed(() => renderMarkdown(markdown.value))

function toggleMode() {
  mode.value = mode.value === 'edit' ? 'read' : 'edit'
}

function askAboutDocument() {
  if (!document.value) return
  // Phase 3's composer reads this store to scope the question to the document.
  useAskContextStore().askAboutDocument(document.value.id, document.value.title)
  router.push('/')
}

async function replaceFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  ;(event.target as HTMLInputElement).value = ''
  if (!document.value || !file) return
  replacementAbort = new AbortController()
  replacementProgress.value = 0
  replacing.value = true
  try {
    await mutations.replaceFile.mutateAsync({
      document: document.value,
      file,
      signal: replacementAbort.signal,
      onProgress: value => { replacementProgress.value = value },
    })
    await Promise.all([query.refetch(), ingestionQuery.refetch(), fileVersions.refetch()])
    Notify.create({ type: 'positive', message: '文件替换已开始' })
  } catch (error) {
    if ((error as DOMException).name === 'AbortError') return
    conflict.value = error instanceof IMAApiError && error.problem.code === 'VERSION_CONFLICT'
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '替换失败') })
  } finally {
    replacing.value = false
    replacementAbort = undefined
  }
}

function abortReplacement() {
  replacementAbort?.abort()
  replacing.value = false
  replacementAbort = undefined
}

onBeforeUnmount(abortReplacement)

async function download() {
  if (!document.value) return
  try {
    window.location.assign((await knowledgeClient.download(document.value.id)).url)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '下载失败') })
  }
}

async function loadPreviewUrl() {
  if (!document.value) return
  previewLoading.value = true
  previewFailure.value = undefined
  try {
    previewUrl.value = (await knowledgeClient.preview(document.value.id)).url
  } catch (error) {
    previewUrl.value = undefined
    previewFailure.value = error instanceof IMAApiError && error.problem?.code === 'PREVIEW_UNAVAILABLE' ? 'unsupported' : 'error'
  } finally {
    previewLoading.value = false
  }
}

async function retryIngestion() {
  if (!document.value) return
  await mutations.retryIngestion.mutateAsync(document.value.id)
}

async function cancelIngestion() {
  if (!document.value) return
  await mutations.cancelIngestion.mutateAsync(document.value.id)
}

async function save() {
  if (!document.value) return
  saving.value = true
  try {
    await mutations.updateDocument.mutateAsync({
      documentId: document.value.id,
      input: {
        title: title.value,
        markdown: markdown.value,
        expectedVersion: document.value.version,
        expectedContentVersion: document.value.currentContentVersion,
      },
    })
    dirty.value = false
    conflict.value = false
  } catch (error) {
    conflict.value = error instanceof IMAApiError && error.problem.code === 'VERSION_CONFLICT'
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '保存失败') })
  } finally {
    saving.value = false
  }
}

async function reloadServerVersion() {
  await query.refetch()
  dirty.value = false
  conflict.value = false
}

async function restore(version: number) {
  if (!document.value) return
  try {
    const restored = await knowledgeClient.restoreVersion(document.value.id, version, document.value.version)
    title.value = restored.title
    markdown.value = restored.markdown ?? ''
    dirty.value = false
    showHistory.value = false
    await query.refetch()
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '恢复失败') })
  }
}

function confirmDelete() {
  if (!document.value) return
  $q.dialog({
    title: '删除',
    message: `确定要删除“${document.value.title}”吗？此操作无法撤销。`,
    cancel: true,
    ok: {
      label: '删除',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    if (!document.value) return
    try {
      await mutations.deleteDocument.mutateAsync({
        documentId: document.value.id,
        folderId: document.value.folderId,
      })
      Notify.create({ type: 'positive', message: '已删除' })
      emit('deleted')
    } catch (error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, '删除失败') })
    }
  })
}
</script>

<style scoped>
.doc-preview {
  background-color: var(--tk-bg);
}

.doc-preview-header {
  border-bottom: 1px solid var(--tk-border);
}

.doc-preview-title {
  min-width: 0;
}

.kb-banner-warning {
  background-color: rgba(255, 136, 0, 0.12);
  color: var(--tk-text);
}

.kb-banner-info {
  border-radius: var(--tk-radius);
  border: 1px solid var(--tk-border);
  background-color: var(--tk-accent-soft);
  color: var(--tk-text-secondary);
}

.kb-ingestion-status {
  display: inline-flex;
  align-items: center;
  gap: var(--tk-space-1);
  font-weight: var(--tk-weight-semibold);
}

/* Ready files replace the banner with a quiet inline status + version. */
.kb-ingest-inline {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
}

.kb-ingest-ready {
  display: inline-flex;
  align-items: center;
  gap: var(--tk-space-1);
  font-size: 13px;
  font-weight: var(--tk-weight-medium);
  color: var(--tk-success);
}

.kb-ingest-version {
  font-size: var(--tk-font-size-xs);
  color: var(--tk-text-tertiary);
}

.doc-preview-iframe {
  width: 100%;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface);
}

.doc-preview-office {
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface-white);
}

.doc-preview-office-host {
  min-height: 100%;
}

.doc-preview-sheet {
  padding: var(--tk-space-3);
}

.doc-preview-editor-input {
  min-width: 0;
}

.doc-preview-editor-render {
  background-color: var(--tk-surface);
  min-width: 0;
}
</style>

<style>
/* Rendered markdown (unscoped: content comes from v-html). Flat selectors only — Chrome 109 policy. */
.md-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--tk-text);
  word-break: break-word;
}

.md-body > *:first-child {
  margin-top: 0;
}

.md-body h1,
.md-body h2,
.md-body h3,
.md-body h4,
.md-body h5,
.md-body h6 {
  margin: 16px 0 8px;
  font-weight: 600;
  line-height: 1.4;
}

.md-body h1 {
  font-size: 22px;
}

.md-body h2 {
  font-size: 18px;
}

.md-body h3 {
  font-size: 16px;
}

.md-body p {
  margin: 8px 0;
}

.md-body ul,
.md-body ol {
  margin: 8px 0;
  padding-left: 24px;
}

.md-body blockquote {
  margin: 8px 0;
  padding: 4px 12px;
  border-left: 3px solid var(--tk-border-strong);
  color: var(--tk-text-secondary);
}

.md-body code {
  padding: 1px 4px;
  border-radius: var(--tk-radius-sm);
  background-color: var(--tk-surface-deep);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}

.md-body pre {
  margin: 8px 0;
  padding: 12px;
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface-deep);
  overflow-x: auto;
}

.md-body pre code {
  padding: 0;
  background-color: transparent;
}

.md-body a {
  color: var(--tk-accent);
  text-decoration: none;
}

.md-body img {
  max-width: 100%;
}

.md-body table {
  border-collapse: collapse;
  margin: 8px 0;
}

.md-body th,
.md-body td {
  padding: 4px 10px;
  border: 1px solid var(--tk-border);
}

.md-body hr {
  margin: 16px 0;
  border: none;
  border-top: 1px solid var(--tk-border);
}
</style>
