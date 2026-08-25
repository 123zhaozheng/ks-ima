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
        unelevated
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
        <q-list>
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
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useKnowledgeDocument, useKnowledgeMutations, useKnowledgeVersions } from 'src/composables/use-knowledge'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { t } from 'src/utils/i18n'
import { Notify } from 'quasar'

const route = useRoute()
const documentId = computed(() => String(route.params.documentId))
const query = useKnowledgeDocument(() => documentId.value)
const versions = useKnowledgeVersions(() => documentId.value)
const document = computed(() => query.data.value)
const title = ref('')
const markdown = ref('')
const dirty = ref(false)
const saving = ref(false)
const showHistory = ref(false)
const conflict = ref(false)
const mutations = useKnowledgeMutations()

watch(document, value => {
  if (!value || dirty.value) return
  title.value = value.title
  markdown.value = value.markdown ?? ''
}, { immediate: true })

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
