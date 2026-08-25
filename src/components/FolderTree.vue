<template>
  <div
    flex="~ col"
    min-h-0
    flex-1
    of-y-auto
    px-2
    py-1
    role="tree"
  >
    <q-item
      clickable
      item-rd
      role="treeitem"
      tabindex="0"
      min-h="36px"
      py-0
      px-2
      :to="workspaceStore.id ? `/folder/${workspaceStore.id}` : undefined"
      :active="currentFolderId === workspaceStore.id"
      @keydown.enter.prevent="activate(workspaceStore.id!)"
      @keydown.space.prevent="activate(workspaceStore.id!)"
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
      role="treeitem"
      tabindex="0"
      min-h="36px"
      py-0
      pr-2
      :style="{ paddingLeft: `${8 + row.depth * 16}px` }"
      :to="`/folder/${row.folder.id}`"
      :active="currentFolderId === row.folder.id"
      :aria-expanded="row.hasChildren ? expanded.has(row.folder.id) : undefined"
      @keydown.enter.prevent="activate(row.folder.id)"
      @keydown.space.prevent="activate(row.folder.id)"
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
          :title="row.folder.title"
        >
          {{ row.folder.title }}
        </q-item-label>
      </q-item-section>
    </q-item>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { knowledgeClient } from 'src/api/knowledge-client'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'

type Folder = { id: string, title: string, kind: 'folder', version: number }

const workspaceStore = useWorkspaceStore()
const route = useRoute()
const router = useRouter()
const byParent = ref(new Map<string, Folder[]>())
const folderMap = computed(() => Object.fromEntries([...byParent.value.values()].flat().map(folder => [folder.id, folder])))

const currentFolderId = computed(() => {
  const { type, id } = route.params
  if (typeof id !== 'string') return workspaceStore.id ?? ''
  if (type === 'folder') return id
  return id || workspaceStore.id || ''
})

const expanded = reactive(new Set<string>())

function childrenOf(parentId: string) {
  return byParent.value.get(parentId) ?? []
}

watch([currentFolderId, folderMap], () => {
  let id = currentFolderId.value
  while (id && id !== workspaceStore.id) {
    const folder = folderMap.value[id]
    const parentId = [...byParent.value.entries()].find(([, folders]) => folders.some(item => item.id === folder?.id))?.[0]
    if (!parentId || parentId === workspaceStore.id) break
    expanded.add(parentId)
    id = parentId
  }
}, { immediate: true })

const visibleRows = computed(() => {
  const rows: { folder: Folder, depth: number, hasChildren: boolean }[] = []
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
  loadChildren(id).catch(() => undefined)
}

function activate(id: string) {
  const folder = folderMap.value[id]
  if (folder) {
    toggle(id)
  }
  router.push(`/folder/${id}`)
}

async function loadChildren(parentId: string) {
  try {
    const page = await knowledgeClient.contents(parentId, { kind: 'folder', limit: 100 })
    byParent.value.set(parentId, page.items.filter(item => item.kind === 'folder').map(item => ({
      id: item.id,
      title: item.title,
      kind: 'folder',
      version: item.version,
    })))
  } catch {
    byParent.value.set(parentId, [])
  }
}

watch(() => workspaceStore.id, id => {
  byParent.value = new Map()
  expanded.clear()
  if (id) loadChildren(id).catch(() => undefined)
}, { immediate: true })
</script>
