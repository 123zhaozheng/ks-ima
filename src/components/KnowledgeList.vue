<template>
  <div
    flex="~ col"
    min-h-0
    h-full
  >
    <q-linear-progress
      v-if="query.isFetching.value"
      indeterminate
      color="primary"
    />
    <q-list
      v-if="query.data.value?.items.length"
      of-y-auto
      flex-1
    >
      <q-item
        v-for="item in items"
        :key="item.id"
        clickable
        :to="item.kind === 'folder' ? { path: '/', query: { folderId: item.id } } : `/knowledge/${item.id}`"
        :aria-label="item.title"
      >
        <q-item-section avatar>
          <q-icon :name="item.kind === 'folder' ? 'sym_o_folder' : item.kind === 'note' ? 'sym_o_description' : 'sym_o_insert_drive_file'" />
        </q-item-section>
        <q-item-section>
          <q-item-label>{{ item.title }}</q-item-label>
          <q-item-label
            v-if="item.kind === 'file'"
            caption
          >
            {{ item.fileState === 'pending' ? t('Storage migration pending') : item.fileState }}
          </q-item-label>
        </q-item-section>
        <q-item-section
          v-if="item.kind === 'file'"
          side
        >
          <q-icon
            name="sym_o_lock"
            :title="t('File actions are unavailable until storage migration is complete')"
          />
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
      v-else-if="query.isError.value"
      flex
      flex-1
      items-center
      justify-center
      p-6
    >
      <q-btn
        flat
        icon="sym_o_refresh"
        :label="t('Retry')"
        @click="query.refetch()"
      />
    </div>
    <div
      v-else
      flex
      flex-1
      items-center
      justify-center
      text-on-sur-var
    >
      <slot name="empty">
        {{ t('No items') }}
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { components } from 'src/api/generated/schema'
import { useFolderContents } from 'src/composables/use-knowledge'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { t } from 'src/utils/i18n'

const props = defineProps<{ folderId: string }>()
const cursor = ref<string>()
const query = useFolderContents(() => props.folderId)
const extraItems = ref<components['schemas']['ContentRow'][]>([])
const items = computed(() => [...(query.data.value?.items ?? []), ...extraItems.value])
const nextCursor = ref<string>()

watch(() => query.data.value?.nextCursor, value => {
  nextCursor.value = value ?? undefined
  extraItems.value = []
}, { immediate: true })

async function loadMore() {
  const next = nextCursor.value
  if (!next) return
  cursor.value = next
  try {
    const page = await knowledgeClient.contents(props.folderId, { cursor: next })
    extraItems.value.push(...page.items)
    nextCursor.value = page.nextCursor ?? undefined
  } catch (error) {
    if (error instanceof IMAApiError && error.problem.code === 'LISTING_CHANGED') {
      // A cursor is bound to the folder's children revision.  Never append a
      // page from the old ordering; restart from the authoritative first page.
      extraItems.value = []
      cursor.value = undefined
      nextCursor.value = undefined
      await query.refetch()
      return
    }
    throw error
  }
}
</script>
