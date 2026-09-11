<template>
  <div
    flex="~ col"
    min-h-0
    h-full
  >
    <q-linear-progress
      v-if="query.isLoading.value"
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
          <q-icon
            :name="item.kind === 'folder' ? 'sym_o_folder' : item.kind === 'note' ? 'sym_o_description' : 'sym_o_insert_drive_file'"
            size="18px"
          />
        </q-item-section>
        <q-item-section min-w-0>
          <q-item-label
            class="kb-row-title"
            text-ellipsis
            whitespace-nowrap
            overflow-hidden
          >
            {{ item.title }}
          </q-item-label>
          <q-item-label
            v-if="item.kind === 'file'"
            caption
            class="kb-file-status"
          >
            <status-badge
              :tone="statusTone(item)"
              :label="statusOf(item).label"
              :dot="statusOf(item).tone === 'ready'"
              :icon="statusOf(item).icon"
            />
          </q-item-label>
        </q-item-section>
        <q-item-section
          v-if="item.kind !== 'folder' && !readonly"
          side
        >
          <q-btn
            flat
            dense
            round
            icon="sym_o_more_vert"
            aria-label="更多"
            class="kb-row-menu"
            @click.prevent.stop
          >
            <q-menu>
              <q-list dense>
                <q-item
                  v-close-popup
                  clickable
                  data-testid="row-delete-action"
                  @click="confirmDelete(item)"
                >
                  <q-item-section
                    avatar
                    min-w-0
                  >
                    <q-icon name="sym_o_delete" />
                  </q-item-section>
                  <q-item-section>删除</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </q-btn>
        </q-item-section>
      </q-item>
      <q-item
        v-if="nextCursor"
        clickable
        class="kb-load-more"
        @click="loadMore"
      >
        <q-item-section>加载更多</q-item-section>
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
        label="重试"
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
        没有项目
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { Notify, useQuasar } from 'quasar'
import { computed, ref, watch } from 'vue'
import StatusBadge from 'src/components/StatusBadge.vue'
import { knowledgeClient } from 'src/api/knowledge-client'
import { IMAApiError } from 'src/api/ima-client'
import { useFolderContents, useKnowledgeMutations } from 'src/composables/use-knowledge'
import { apiErrorMessage } from 'src/utils/api-error'
import { fileStateView } from 'src/utils/ingestion-status'

type ContentRow = components['schemas']['ContentRow']

const props = withDefaults(defineProps<{
  folderId: string
  selectedId?: string | null
  readonly?: boolean
}>(), { selectedId: null, readonly: false })

const $q = useQuasar()
const cursor = ref<string>()
const query = useFolderContents(() => props.folderId)
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

function statusOf(item: ContentRow) {
  return fileStateView(item.fileState)
}

// StatusBadge tone per fileStateView tone; ready calms down to the dot.
const STATUS_TONES = { pending: 'warning', ready: 'success', failed: 'danger', unknown: 'muted' } as const

function statusTone(item: ContentRow) {
  return STATUS_TONES[statusOf(item).tone]
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

function confirmDelete(item: ContentRow) {
  $q.dialog({
    title: '删除',
    message: `确定要删除“${item.title}”吗？此操作无法撤销。`,
    cancel: true,
    ok: {
      label: '删除',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    try {
      await mutations.deleteDocument.mutateAsync({
        documentId: item.id,
        folderId: props.folderId,
      })
      Notify.create({ type: 'positive', message: '已删除' })
    } catch (error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, '删除失败') })
    }
  })
}
</script>

<style scoped>
.kb-row {
  min-height: 48px;
  border-radius: var(--tk-radius);
}

.kb-row-title {
  font-size: var(--tk-font-size-sm);
  font-weight: var(--tk-weight-medium);
}

.kb-row:hover {
  background-color: var(--tk-bg);
}

/* After the hover rule so a hovered selected row keeps the soft fill. */
.kb-row.kb-row-active {
  background-color: var(--tk-accent-soft);
  box-shadow: inset 0 0 0 1px var(--tk-accent-soft-stronger);
}

.kb-load-more {
  justify-content: center;
  min-height: 40px;
  font-size: 13px;
  color: var(--tk-text-tertiary);
}

.kb-load-more .q-item__section {
  align-items: center;
}

.kb-file-status {
  display: flex;
  align-items: center;
  gap: var(--tk-space-1);
}

.kb-row-menu {
  opacity: 0;
}

.kb-row:hover .kb-row-menu {
  opacity: 1;
}
</style>
