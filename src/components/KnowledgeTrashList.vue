<template>
  <q-list
    v-if="items.length"
    of-y-auto
    p-2
  >
    <q-item
      v-for="item in items"
      :key="item.id"
    >
      <q-item-section avatar>
        <q-icon name="sym_o_delete" />
      </q-item-section>
      <q-item-section>
        <q-item-label>{{ item.title }}</q-item-label>
        <q-item-label caption>
          {{ item.kind }}
        </q-item-label>
      </q-item-section>
      <q-item-section side>
        <div
          flex
          gap-1
        >
          <q-btn
            flat
            dense
            round
            icon="sym_o_restore_page"
            :title="t('Restore')"
            @click="restore(item.id, item.version)"
          />
          <q-btn
            flat
            dense
            round
            color="negative"
            icon="sym_o_delete_forever"
            :title="t('Delete permanently')"
            @click="remove(item.id)"
          />
        </div>
      </q-item-section>
    </q-item>
    <q-item
      v-if="nextCursor"
      clickable
      @click="loadMore"
    >
      <q-item-section>{{ t('Load more') }}</q-item-section>
    </q-item>
  </q-list>
  <div
    v-else-if="query.isLoading.value"
    flex
    flex-1
    items-center
    justify-center
  >
    <q-spinner color="primary" />
  </div>
  <div
    v-else
    flex
    flex-1
    items-center
    justify-center
    text-on-sur-var
  >
    {{ t('Trash is empty') }}
  </div>
</template>

<script setup lang="ts">
import { useKnowledgeTrash } from 'src/composables/use-knowledge'
import { knowledgeClient } from 'src/api/knowledge-client'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'
import { Notify } from 'quasar'

import { computed, ref, watch } from 'vue'
import type { components } from 'src/api/generated/schema'
import { IMAApiError } from 'src/api/ima-client'

const props = defineProps<{ workspaceId: string }>()
const query = useKnowledgeTrash(() => props.workspaceId)
const extraItems = ref<components['schemas']['ContentRow'][]>([])
const items = computed(() => [...(query.data.value?.items ?? []), ...extraItems.value])
const nextCursor = ref<string>()

watch(() => query.data.value?.nextCursor, value => {
  nextCursor.value = value ?? undefined
  extraItems.value = []
}, { immediate: true })

async function restore(documentId: string, version: number) {
  try {
    const item = items.value.find(row => row.id === documentId)
    if (item?.kind === 'folder') {
      const result = await identityClient.restoreWorkspaceFolder(props.workspaceId, documentId, { expectedVersion: version })
      if (result.error) throw new Error(result.error.message)
    } else {
      await knowledgeClient.restoreDocument(documentId, version)
    }
    await query.refetch()
  } catch (error) {
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Restore failed') })
  }
}

async function remove(documentId: string) {
  try {
    const item = items.value.find(row => row.id === documentId)
    if (item?.kind === 'folder') {
      const result = await identityClient.deleteWorkspaceFolder(props.workspaceId, documentId, versionFor(documentId))
      if (result.error) throw new Error(result.error.message)
    } else {
      await knowledgeClient.deleteDocument(documentId)
    }
    await query.refetch()
  } catch (error) {
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Delete failed') })
  }
}

function versionFor(documentId: string) {
  return items.value.find(row => row.id === documentId)?.version ?? 1
}

async function loadMore() {
  const cursor = nextCursor.value
  if (!cursor) return
  try {
    const page = await knowledgeClient.trash(props.workspaceId, { cursor })
    extraItems.value.push(...page.items)
    nextCursor.value = page.nextCursor ?? undefined
  } catch (error) {
    if (error instanceof IMAApiError && error.problem.code === 'LISTING_CHANGED') {
      extraItems.value = []
      nextCursor.value = undefined
      await query.refetch()
      return
    }
    throw error
  }
}
</script>
