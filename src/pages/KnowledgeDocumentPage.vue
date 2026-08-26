<template>
  <q-page
    flex="~ col"
    p-4
  >
    <div
      flex
      items-center
      gap-2
      mb-3
    >
      <q-btn
        flat
        dense
        round
        icon="sym_o_arrow_back"
        :title="t('Back')"
        @click="$router.back()"
      />
      <q-input
        v-model="title"
        borderless
        dense
        class="text-lg"
        :readonly="!document"
      />
      <q-space />
      <q-btn
        flat
        icon="sym_o_history"
        :label="t('History')"
        :disable="!document"
        @click="showHistory = true"
      />
      <q-btn
        v-if="document?.kind === 'file'"
        flat
        icon="sym_o_upload_file"
        :label="t('Replace')"
        :loading="replacing"
        :disable="!document || query.isError.value"
        @click="replacementInput?.click()"
      />
      <input
        ref="replacementInput"
        type="file"
        accept=".txt,.md,.markdown,.json,.pdf,.docx,.xlsx,.xls"
        @change="replaceFile"
      />
      <q-btn
        :label="t('Download')"
        @click="download"
      />
      <q-btn
        v-if="document?.kind === 'file'"
        flat
        icon="sym_o_preview"
        :label="t('Preview')"
        @click="preview"
      />
      <q-btn
        v-if="document?.kind === 'file' && ingestion?.jobs.some(job => ['queued', 'running', 'retryable', 'cancel_requested'].includes(job.status))"
        flat
        icon="sym_o_cancel"
        :label="t('Cancel')"
        @click="cancelIngestion"
      />
      <q-btn
        v-if="document?.kind === 'file' && ingestion?.jobs.some(job => ['failed', 'dead_letter', 'cancelled'].includes(job.status))"
        flat
        icon="sym_o_refresh"
        :label="t('Retry')"
        @click="retryIngestion"
      />
      <q-btn
        color="primary"
        icon="sym_o_save"
        :label="t('Save')"
        :loading="saving"
        :disable="!document || !dirty"
        @click="save"
      />
    </div>
    <q-banner
      v-if="query.isError.value"
      rounded
      class="bg-negative text-white"
    >
      {{ t('This document is unavailable or access was revoked.') }}
    </q-banner>
    <q-banner
      v-if="conflict"
      rounded
      class="bg-warning text-black"
    >
      {{ t('This document changed elsewhere. Your draft is still here.') }}
      <q-btn
        flat
        :label="t('Reload server version')"
        @click="reloadServerVersion"
      />
    </q-banner>
    <q-banner
      v-if="document?.kind === 'file' && ingestion"
      class="bg-sur-c-low mb-3"
    >
      {{ ingestion.jobs.map(job => `${job.stage}: ${job.status}`).join(' · ') }}
    </q-banner>
    <div
      v-if="document?.kind === 'file'"
      flex="~ col"
      gap-3
      flex-1
    >
      <q-linear-progress
        v-if="replacing"
        :value="replacementProgress"
        color="primary"
        size="8px"
      />
      <q-btn
        v-if="replacing"
        flat
        dense
        round
        icon="sym_o_cancel"
        :title="t('Cancel')"
        @click="abortReplacement"
      />
      <div class="text-body1">{{ document.title }}</div>
      <div class="text-caption text-on-sur-var">
        {{ t('Version {0}', document.currentContentVersion) }}
      </div>
      <iframe v-if="previewUrl" :src="previewUrl" class="w-full flex-1 min-h-0 border-0" :title="document.title" />
    </div>
    <div
      v-else
      flex="~ col md:row"
      gap-3
      flex-1
      min-h-0
    >
      <q-input
        v-model="markdown"
        type="textarea"
        outlined
        autogrow
        class="flex-1"
        input-class="font-mono"
        :disable="!document"
        @update:model-value="dirty = true"
      />
      <div
        flex-1
        of-y-auto
        p-3
        rounded
        bg-sur-c-low
      >
        <pre whitespace-pre-wrap>{{ markdown }}</pre>
      </div>
    </div>
    <q-dialog v-model="showHistory">
      <q-card min-w="320px">
        <q-card-section class="text-h6">
          {{ t('History') }}
        </q-card-section>
        <q-list v-if="document?.kind === 'file'">
          <q-item
            v-for="version in fileVersions.data.value?.items"
            :key="version.version"
          >
            <q-item-section>
              <q-item-label>{{ t('Version {0}', version.version) }}</q-item-label>
              <q-item-label caption>{{ version.originalFilename }} · {{ version.objectState }}</q-item-label>
            </q-item-section>
            <q-item-section side>{{ new Date(version.createdAt).toLocaleString() }}</q-item-section>
          </q-item>
        </q-list>
        <q-list v-else>
          <q-item
            v-for="version in versions.data.value"
            :key="version.version"
            clickable
            @click="restore(version.version)"
          >
            <q-item-section>{{ t('Version {0}', version.version) }}</q-item-section>
            <q-item-section side>
              {{ new Date(version.createdAt).toLocaleString() }}
            </q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useFileVersions, useKnowledgeDocument, useKnowledgeIngestion, useKnowledgeMutations, useKnowledgeVersions } from 'src/composables/use-knowledge'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { t } from 'src/utils/i18n'
import { Notify } from 'quasar'

const route = useRoute()
const documentId = computed(() => String(route.params.documentId))
const query = useKnowledgeDocument(() => documentId.value)
const ingestionQuery = useKnowledgeIngestion(() => documentId.value)
const ingestion = computed(() => ingestionQuery.data.value)
const versions = useKnowledgeVersions(() => documentId.value)
const fileVersions = useFileVersions(() => documentId.value)
const document = computed(() => query.data.value)
const title = ref('')
const markdown = ref('')
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

watch(documentId, () => abortReplacement())
onBeforeUnmount(abortReplacement)

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
    Notify.create({ type: 'positive', message: t('File replacement started') })
  } catch (error) {
    if ((error as DOMException).name === 'AbortError') return
    conflict.value = error instanceof IMAApiError && error.problem.code === 'VERSION_CONFLICT'
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Replacement failed') })
  } finally {
    replacing.value = false
    replacementAbort = undefined
  }
}

function abortReplacement() {
  replacementAbort?.abort()
}

async function download() {
  if (!document.value) return
  try {
    window.location.assign((await knowledgeClient.download(document.value.id)).url)
  } catch (error) {
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Download failed') })
  }
}

async function preview() {
  if (!document.value) return
  try {
    previewUrl.value = (await knowledgeClient.preview(document.value.id)).url
  } catch (error) {
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Preview unavailable') })
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
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Save failed') })
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
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Restore failed') })
  }
}
</script>
