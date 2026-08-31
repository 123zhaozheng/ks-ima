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
        flat
        dense
        icon="sym_o_chat"
        label="询问这篇文档"
        :disable="!document"
        data-testid="doc-ask-button"
        @click="askAboutDocument"
      />
      <q-btn
        flat
        dense
        icon="sym_o_history"
        title="历史"
        :disable="!document"
        @click="showHistory = true"
      />
      <q-btn
        v-if="document?.kind === 'note' && !readonly"
        flat
        dense
        :icon="mode === 'edit' ? 'sym_o_visibility' : 'sym_o_edit'"
        :label="mode === 'edit' ? '预览' : '编辑'"
        @click="toggleMode"
      />
      <q-btn
        v-if="document?.kind === 'file' && !readonly"
        flat
        dense
        icon="sym_o_upload_file"
        label="替换"
        :loading="replacing"
        :disable="!document || query.isError.value"
        @click="replacementInput?.click()"
      />
      <input
        ref="replacementInput"
        type="file"
        accept=".txt,.md,.markdown,.json,.pdf,.docx,.xlsx,.xls"
        hidden
        @change="replaceFile"
      >
      <q-btn
        flat
        dense
        icon="sym_o_download"
        title="下载"
        :disable="!document"
        @click="download"
      />
      <q-btn
        v-if="document?.kind === 'file'"
        flat
        dense
        icon="sym_o_refresh"
        title="预览"
        :disable="!document"
        @click="loadPreviewUrl"
      />
      <q-btn
        v-if="!readonly"
        flat
        dense
        round
        icon="sym_o_delete"
        title="删除"
        :disable="!document"
        data-testid="doc-delete-button"
        @click="confirmDelete"
      />
      <q-btn
        v-if="!readonly"
        color="primary"
        dense
        icon="sym_o_save"
        label="保存"
        :loading="saving"
        :disable="!document || !dirty"
        @click="save"
      />
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
      <q-banner
        v-if="document?.kind === 'file' && ingestion"
        rounded
        class="kb-banner-info"
      >
        {{ ingestion.jobs.map(job => `${job.stage}: ${job.status}`).join(' · ') }}
        <template #action>
          <q-btn
            v-if="ingestion.jobs.some(job => ['queued', 'running', 'retryable', 'cancel_requested'].includes(job.status))"
            flat
            dense
            label="取消"
            @click="cancelIngestion"
          />
          <q-btn
            v-if="ingestion.jobs.some(job => ['failed', 'dead_letter', 'cancelled'].includes(job.status))"
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
      <div class="text-caption text-on-sur-var">
        版本 {{ document.currentContentVersion }}
      </div>
      <iframe
        v-if="previewUrl"
        :src="previewUrl"
        class="doc-preview-iframe"
        :title="document.title"
      />
      <div
        v-else-if="!query.isLoading.value"
        flex
        flex-1
        items-center
        justify-center
        text-on-sur-var
      >
        无法预览
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
import { Notify, useQuasar } from 'quasar'
import { useFileVersions, useKnowledgeDocument, useKnowledgeIngestion, useKnowledgeMutations, useKnowledgeVersions } from 'src/composables/use-knowledge'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { useAskContextStore } from 'src/stores/ask-context'
import { apiErrorMessage } from 'src/utils/api-error'
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

const title = ref('')
const markdown = ref('')
const mode = ref<'read' | 'edit'>('read')
const dirty = ref(false)
const saving = ref(false)
const showHistory = ref(false)
const conflict = ref(false)
const previewUrl = ref<string>()
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
  mode.value = props.startInEdit ? 'edit' : 'read'
}, { immediate: true })

watch(document, value => {
  if (value?.kind === 'file' && !previewUrl.value) loadPreviewUrl()
})

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
  try {
    previewUrl.value = (await knowledgeClient.preview(document.value.id)).url
  } catch (error) {
    previewUrl.value = undefined
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '无法预览') })
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
  background-color: var(--tk-surface);
  color: var(--tk-text-secondary);
}

.doc-preview-iframe {
  width: 100%;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface);
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
