<template>
  <div
    flex="~ col"
    min-h-0
    flex-1
    of-y-auto
    px-2
    py-1
  >
    <q-item
      clickable
      item-rd
      min-h="36px"
      py-0
      px-2
      :to="workspaceStore.id ? `/folder/${workspaceStore.id}` : undefined"
      :active="currentFolderId === workspaceStore.id"
    >
      <q-item-section
        avatar
        min-w-0
        pr-3
      >
        <q-icon name="sym_o_folder_open" />
      </q-item-section>
      <q-item-section>
        <q-item-label
          text-ellipsis
          whitespace-nowrap
          overflow-hidden
        >
          {{ t('All files') }}
        </q-item-label>
      </q-item-section>
    </q-item>
    <q-item
      v-for="row in visibleRows"
      :key="row.folder.id"
      clickable
      item-rd
      min-h="36px"
      py-0
      pr-2
      :style="{ paddingLeft: `${8 + row.depth * 16}px` }"
      :to="`/folder/${row.folder.id}`"
      :active="currentFolderId === row.folder.id"
    >
      <q-item-section
        side
        min-w-0
        pr-1
      >
        <q-btn
          v-if="row.hasChildren"
          flat
          dense
          round
          size="sm"
          :icon="expanded.has(row.folder.id) ? 'sym_o_expand_more' : 'sym_o_chevron_right'"
          @click.prevent.stop="toggle(row.folder.id)"
        />
        <div
          v-else
          w="28px"
        />
      </q-item-section>
      <q-item-section
        avatar
        min-w-0
        pr-2
      >
        <q-icon name="sym_o_folder" />
      </q-item-section>
      <q-item-section>
        <q-item-label
          text-ellipsis
          whitespace-nowrap
          overflow-hidden
          :title="entityName(row.folder)"
        >
          {{ entityName(row.folder) }}
        </q-item-label>
      </q-item-section>
    </q-item>
  </div>
</template>

<script setup lang="ts">
import { queries } from 'app/src-shared/queries'
import type { Row } from '@rocicorp/zero'
import { computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useQuery } from 'src/composables/zero/query'
import { useWorkspaceStore } from 'src/stores/workspace'
import { entityName } from 'src/utils/defaults'
import { isKnowledgeEntity } from 'src/utils/knowledge'
import { t } from 'src/utils/i18n'
import { useLocalEntitiesStore } from 'src/stores/local-entities'

const workspaceStore = useWorkspaceStore()
const route = useRoute()
const { data: folders } = useQuery(
  () => workspaceStore.id ? queries.workspaceFolders(workspaceStore.id) : null,
  { emptyValue: [] },
)

const knowledgeFolders = computed(() =>
  folders.value.filter(e => isKnowledgeEntity(e) && e.id !== workspaceStore.id),
)
const byParent = computed(() => {
  const map = new Map<string, Row['entity'][]>()
  for (const folder of knowledgeFolders.value) {
    const parentId = folder.parentId ?? workspaceStore.id!
    const list = map.get(parentId) ?? []
    list.push(folder)
    map.set(parentId, list)
  }
  for (const list of map.values()) {
    list.sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', undefined, { sensitivity: 'base' }))
  }
  return map
})
const folderMap = computed(() => Object.fromEntries(knowledgeFolders.value.map(f => [f.id, f])))
const localEntitiesStore = useLocalEntitiesStore()

const currentFolderId = computed(() => {
  const { type, id } = route.params
  if (typeof id !== 'string') return workspaceStore.id ?? ''
  if (type === 'folder') return id
  const entity = localEntitiesStore.entityMap[id]
  return entity?.parentId || workspaceStore.id || ''
})

const expanded = reactive(new Set<string>())

function childrenOf(parentId: string) {
  return byParent.value.get(parentId) ?? []
}

watch([currentFolderId, folderMap], () => {
  let id = currentFolderId.value
  while (id && id !== workspaceStore.id) {
    const folder = folderMap.value[id]
    const parentId = folder?.parentId
    if (!parentId) break
    expanded.add(parentId)
    id = parentId
  }
}, { immediate: true })

const visibleRows = computed(() => {
  const rows: { folder: Row['entity'], depth: number, hasChildren: boolean }[] = []
  const walk = (parentId: string, depth: number) => {
    for (const folder of childrenOf(parentId)) {
      const kids = childrenOf(folder.id)
      rows.push({ folder, depth, hasChildren: kids.length > 0 })
      if (expanded.has(folder.id)) walk(folder.id, depth + 1)
    }
  }
  if (workspaceStore.id) walk(workspaceStore.id, 0)
  return rows
})

function toggle(id: string) {
  if (expanded.has(id)) expanded.delete(id)
  else expanded.add(id)
}
</script>
