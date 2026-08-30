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
      v-if="items.length"
      of-y-auto
      flex-1
    >
      <q-item
        v-for="item in items"
        :key="item.id"
        clickable
        class="kb-row"
        :class="{ 'kb-row-active': isSelected(item) }"
        :to="item.kind === 'folder'
          ? { path: '/kb', query: { folderId: item.id } }
          : { path: '/kb', query: { folderId: props.folderId, doc: item.id } }"
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
          v-if="item.kind === 'file' && item.fileState === 'pending'"
          side
        >
          <q-icon
            name="sym_o_lock"
            :title="t('File actions are unavailable until storage migration is complete')"
          />
        </q-item-section>
        <q-item-section
          v-else-if="item.kind !== 'folder'"
          side
        >
          <q-btn
            flat
            dense
            round
            icon="sym_o_more_vert"
            :aria-label="t('More')"
            class="kb-row-menu"
            @click.prevent.stop
          >
            <q-menu>
              <q-list dense>
                <q-item
                  v-close-popup
                  clickable
                  data-testid="row-trash-action"
                  @click="confirmTrash(item)"
                >
                  <q-item-section
                    avatar
                    min-w-0
                  >
                    <q-icon name="sym_o_delete" />
                  </q-item-section>
                  <q-item-section>{{ t('Move to trash') }}</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </q-btn>
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
import type { components } from 'src/api/generated/schema'
import { Notify, useQuasar } from 'quasar'
import { computed, ref, watch } from 'vue'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { useFolderContents, useKnowledgeMutations } from 'src/composables/use-knowledge'
import { apiErrorMessage } from 'src/utils/api-error'
import { t } from 'src/utils/i18n'

type ContentRow = components['schemas']['ContentRow']

const props = defineProps<{
  folderId: string
  selectedId?: string | null
  tagId?: string | null
}>()

const $q = useQuasar()
const cursor = ref<string>()
const query = useFolderContents(() => props.folderId, () => ({ tagId: props.tagId ?? undefined }))
const extraItems = ref<ContentRow[]>([])
const items = computed(() => [...(query.data.value?.items ?? []), ...extraItems.value])
const nextCursor = ref<string>()
const mutations = useKnowledgeMutations()

watch(() => query.data.value?.nextCursor, value => {
  nextCursor.value = value ?? undefined
  extraItems.value = []
}, { immediate: true })

function isSelected(item: ContentRow) {
  if (item.kind === 'folder') return false
  return props.selectedId === item.id
}

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

function confirmTrash(item: ContentRow) {
  $q.dialog({
    title: t('Move to trash'),
    message: t('Are you sure you want to move "{0}" to trash?', item.title),
    cancel: true,
    ok: {
      label: t('Move to trash'),
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    try {
      await mutations.trashDocument.mutateAsync({
        documentId: item.id,
        expectedVersion: item.version,
        folderId: props.folderId,
      })
      Notify.create({ type: 'positive', message: t('Moved to trash') })
    } catch (error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Trash failed') })
    }
  })
}
</script>

<style scoped>
.kb-row {
  min-height: 38px;
  border-radius: var(--tk-radius);
}

.kb-row-active {
  background-color: var(--tk-accent-soft);
}

.kb-row-menu {
  opacity: 0;
}

.kb-row:hover .kb-row-menu {
  opacity: 1;
}
</style>
