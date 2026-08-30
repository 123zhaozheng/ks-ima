<template>
  <div
    class="folder-picker"
    role="listbox"
    data-testid="folder-picker"
  >
    <q-item
      clickable
      class="folder-picker-item"
      :class="{ 'folder-picker-item-active': selectedId === null }"
      role="option"
      :aria-selected="selectedId === null"
      min-h="36px"
      dense
      @click="emit('select', null)"
    >
      <q-item-section
        avatar
        min-w-0
      >
        <q-icon name="sym_o_folder_open" />
      </q-item-section>
      <q-item-section>
        <q-item-label
          text-ellipsis
          whitespace-nowrap
          overflow-hidden
        >
          {{ t('Whole workspace') }}
        </q-item-label>
      </q-item-section>
      <q-item-section
        v-if="selectedId === null"
        side
      >
        <q-icon
          name="sym_o_check"
          color="primary"
        />
      </q-item-section>
    </q-item>
    <q-item
      v-for="row in visibleRows"
      :key="row.folder.id"
      clickable
      class="folder-picker-item"
      :class="{ 'folder-picker-item-active': selectedId === row.folder.id }"
      role="option"
      :aria-selected="selectedId === row.folder.id"
      min-h="36px"
      dense
      :style="{ paddingLeft: `${8 + row.depth * 16}px` }"
      @click="emit('select', row.folder)"
    >
      <q-item-section
        side
        min-w-0
      >
        <q-btn
          v-if="row.hasChildren || !loaded.has(row.folder.id)"
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
      <q-item-section
        v-if="selectedId === row.folder.id"
        side
      >
        <q-icon
          name="sym_o_check"
          color="primary"
        />
      </q-item-section>
    </q-item>
    <div
      v-if="failed"
      class="folder-picker-empty"
    >
      {{ t('Folders could not be loaded') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { knowledgeClient } from 'src/api/knowledge-client'
import type { PickedFolder } from 'src/components/folder-picker-list'
import { t } from 'src/utils/i18n'

const props = defineProps<{
  workspaceId: string
  selectedId?: string | null
}>()

const emit = defineEmits<{
  select: [folder: PickedFolder | null]
}>()

const byParent = ref(new Map<string, PickedFolder[]>())
const expanded = reactive(new Set<string>())
const loaded = reactive(new Set<string>())
const failed = ref(false)

const visibleRows = computed(() => {
  const rows: { folder: PickedFolder, depth: number, hasChildren: boolean }[] = []
  const walk = (parentId: string, depth: number) => {
    for (const folder of byParent.value.get(parentId) ?? []) {
      rows.push({ folder, depth, hasChildren: loaded.has(folder.id) ? (byParent.value.get(folder.id)?.length ?? 0) > 0 : true })
      if (expanded.has(folder.id)) walk(folder.id, depth + 1)
    }
  }
  if (props.workspaceId) walk(props.workspaceId, 0)
  return rows
})

async function loadChildren(parentId: string) {
  try {
    const page = await knowledgeClient.contents(parentId, { kind: 'folder', limit: 100 })
    byParent.value.set(parentId, page.items
      .filter(item => item.kind === 'folder')
      .map(item => ({ id: item.id, title: item.title })))
    loaded.add(parentId)
    failed.value = false
  } catch {
    byParent.value.set(parentId, [])
    if (parentId === props.workspaceId) failed.value = true
  }
}

function toggle(id: string) {
  if (expanded.has(id)) expanded.delete(id)
  else expanded.add(id)
  if (!loaded.has(id)) loadChildren(id)
}

watch(() => props.workspaceId, id => {
  byParent.value = new Map()
  expanded.clear()
  loaded.clear()
  failed.value = false
  if (id) loadChildren(id)
}, { immediate: true })
</script>

<style scoped>
.folder-picker {
  min-width: 240px;
  max-width: 320px;
  max-height: 320px;
  overflow-y: auto;
  padding: var(--tk-space-1);
}

.folder-picker-item {
  border-radius: var(--tk-radius);
  color: var(--tk-text);
}

.folder-picker-item:hover {
  background-color: var(--tk-surface-deep);
}

.folder-picker-item-active {
  background-color: var(--tk-accent-soft);
  color: var(--tk-accent);
}

.folder-picker-empty {
  padding: var(--tk-space-3);
  font-size: 13px;
  color: var(--tk-text-tertiary);
  text-align: center;
}
</style>
