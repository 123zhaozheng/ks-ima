<template>
  <div flex="~ col">
    <div
      flex
      items-center
      text-on-sur-var
      px-2
      of-x-auto
    >
      <q-btn
        v-if="dir?.parent"
        flat
        dense
        icon="sym_o_arrow_upward"
        text="10px"
        @click="dirId = dir.parent.id"
        h="32px"
        mr-1
      />
      <template
        v-for="(entity, index) in pathEntities"
        :key="entity.id"
      >
        <q-icon
          v-if="index !== 0"
          name="sym_o_keyboard_arrow_right"
          text="16px"
        />
        <q-btn
          flat
          dense
          no-caps
          @click="dirId = entity.id"
          :title="entityName(entity)"
          font-normal
          @drop="onDrop($event, entity.id)"
          v-on="dragHoverListeners"
          transition="background-color 250"
          no-wrap
          :class="{ 'min-w-50px of-hidden': displayLength(entityName(entity)) > 10 }"
        >
          <span
            of-hidden
            text-ellipsis
          >{{ entityName(entity) }}</span>
        </q-btn>
      </template>
      <q-space />
      <slot name="actions" />
      <entity-list-options-btn
        v-model="listOptions"
        flat
        icon="sym_o_sort"
        un-size="32px"
        size="sm"
      />
    </div>
    <div
      flex-1
      of-y-auto
      px-2
      @scroll="onScroll"
      @drop.self="onDrop($event, dirId)"
      @dragover.self.prevent
      flex="~ col"
    >
      <q-list ref="listRef">
        <entity-item
          v-for="entity of children.filter(x => !props.exclude?.includes(x.id))"
          :key="entity.id"
          :active="activeEntitiesStore.activeIds.includes(entity.id)"
          clickable
          @click.prevent="onEntityClick(entity)"
          :entity
          draggable="true"
          @dragstart="onDragstart($event, entity.id)"
          @drop="onDrop($event, entity.id)"
          v-on="dragHoverListeners"
          :selectable="selected.size > 0"
          :selected="selected.has(entity.id)"
          @contextmenu.prevent="onContextmenu(entity.id)"
        >
          <template #actions>
            <div
              flex
              items-center
              gap-1
              @click.stop
              @mousedown.stop
            >
              <template v-if="entity.type === 'item'">
                <q-btn
                  flat
                  dense
                  round
                  icon="sym_o_visibility"
                  :title="t('Preview')"
                  @click="openEntity(entity)"
                />
                <q-btn
                  v-if="entity.item?.blobId"
                  flat
                  dense
                  round
                  icon="sym_o_download"
                  :title="t('Download')"
                  @click="downloadEntity(entity)"
                />
                <q-btn
                  v-if="canReparse(entity)"
                  flat
                  dense
                  no-caps
                  icon="sym_o_sync"
                  :label="$q.screen.gt.sm ? t('Reparse') : undefined"
                  :title="t('Reparse')"
                  :loading="reparsingIds.has(entity.id)"
                  text-pri
                  @click="reparseEntity(entity)"
                />
              </template>
              <q-btn
                flat
                dense
                round
                icon="sym_o_more_vert"
                :title="t('More Actions')"
              >
                <q-menu>
                  <q-list min-w="180px">
                    <menu-item
                      v-if="entity.type === 'item'"
                      :label="t('Reparse')"
                      icon="sym_o_sync"
                      @click="reparseEntity(entity)"
                    />
                    <menu-item
                      :label="t('Rename')"
                      icon="sym_o_edit"
                      @click="renameEntity(entity)"
                    />
                    <menu-item
                      :label="t('Move')"
                      icon="sym_o_move_item"
                      @click="moveEntity(entity)"
                    />
                    <menu-item
                      v-if="entity.type === 'folder'"
                      :label="t('Permissions')"
                      icon="sym_o_lock"
                      @click="editAcl(entity)"
                    />
                    <menu-item
                      :label="t('Tags')"
                      icon="sym_o_label"
                      @click="editTags(entity)"
                    />
                    <q-separator />
                    <menu-item
                      :label="t('Move to Trash')"
                      icon="sym_o_delete"
                      @click="recycleEntity(entity)"
                      hover:text-err
                    />
                  </q-list>
                </q-menu>
              </q-btn>
            </div>
          </template>
        </entity-item>
        <q-menu context-menu>
          <q-list
            ref="menuListRef"
            v-if="selected.size"
          >
            <menu-item
              :label="t('Rename')"
              icon="sym_o_edit"
              @click="renameSelected"
            />
            <menu-item
              v-if="selectedOne"
              :label="t('Change Icon')"
              icon="sym_o_interests"
              @click="changeIcon"
            />
            <menu-item
              :label="t('Move')"
              icon="sym_o_move_item"
              @click="moveSelected"
            />
            <template v-if="selectedOne">
              <menu-item
                v-if="selectedOne.type === 'folder'"
                :label="t('Permissions')"
                icon="sym_o_lock"
                @click="editAcl(selectedOne)"
              />
              <menu-item
                :label="t('Tags')"
                icon="sym_o_label"
                @click="editTags(selectedOne)"
              />
            </template>
            <menu-item
              :label="t('Move to Trash')"
              icon="sym_o_delete"
              @click="recycleSelected"
              hover:text-err
            />
          </q-list>
        </q-menu>
      </q-list>
      <div
        v-if="!children.length"
        flex-1
        flex
        items-center
        justify-center
        min-h="240px"
      >
        <slot name="empty" />
      </div>
      <div grow />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { FullEntity } from 'app/src-shared/queries'
import { queries } from 'app/src-shared/queries'
import { useQuery } from 'src/composables/zero/query'
import { mutate } from 'src/utils/zero-session'
import type { SpliceListOptions } from 'src/utils/functions'
import { arrayToMap, displayLength, expandAncestors, getItemUrl, spliceList } from 'src/utils/functions'
import { computed, onUnmounted, reactive, ref, useTemplateRef, watch } from 'vue'
import EntityItem from './EntityItem.vue'
import { t } from 'src/utils/i18n'
import { exportFile, QList, QMenu, useQuasar } from 'quasar'
import MenuItem from './MenuItem.vue'
import { mutators } from 'app/src-shared/mutators'
import { useWorkspaceStore } from 'src/stores/workspace'
import { entityAvatar, entityName } from 'src/utils/defaults'
import { useActiveEntitiesStore } from 'src/stores/active-entities'
import type { Avatar, EntityListOptions, EntityStart } from 'app/src-shared/utils/validators'
import EntityListOptionsBtn from './EntityListOptionsBtn.vue'
import SelectDirDialog from './SelectDirDialog.vue'
import PickAvatarDialog from './PickAvatarDialog.vue'
import { isKnowledgeEntity, itemParseStatus } from 'src/utils/knowledge'
import { filesFromDrop, uploadKnowledge } from 'src/utils/knowledge-upload'
import { useEntityAcl } from 'src/composables/acl'
import FolderAclDialog from './FolderAclDialog.vue'
import { client } from 'src/utils/hc'
import { getCached } from 'src/utils/blob-cache'

const emit = defineEmits<{
  entityClick: [entity: FullEntity]
}>()

const props = defineProps<{
  rootId?: string
  exclude?: string[]
  selected?: Set<string>
  listOptionsOverride?: Partial<EntityListOptions>
}>()

const selected = reactive(props.selected ?? new Set<string>())

const dirId = defineModel<string>({ required: true })
const workspaceStore = useWorkspaceStore()
const { filterVisible } = useEntityAcl()
const listOptions = ref<EntityListOptions>({
  type: null,
  hidden: false,
  orderBy: ['id', 'desc'],
  ...props.listOptionsOverride,
})
const { data: dir } = useQuery(() => queries.entity({
  id: dirId.value,
  parent: { depth: 5 },
  children: { depth: 1, limit: 40, ...listOptions.value },
}), {
  onNotFound() {
    dirId.value = workspaceStore.id!
  },
})
const children = reactive<FullEntity[]>([])
const childrenMap = computed(() => arrayToMap(children, x => x.id))

watch([dirId, listOptions], () => {
  start.value = null
  children.splice(0)
})

function spliceChildren(val: FullEntity[], options: SpliceListOptions) {
  const cleaned = filterVisible(val).filter(isKnowledgeEntity)
  spliceList(children, cleaned, [['sortPriority', 'desc'], listOptions.value.orderBy, ['id', 'asc']], options)
}
watch(() => dir.value?.children, val => {
  val && spliceChildren(val, { noMore: val.length < 40 })
}, { deep: 1, immediate: true })
const start = ref<EntityStart | null>(null)
const {
  data: dirWithMoreChildren,
} = useQuery(
  () => start.value
    ? queries.entity({
      id: dirId.value,
      children: { depth: 1, limit: 80, ...listOptions.value, start: start.value },
    })
    : null,
)
let noMore = false
watch(() => dirWithMoreChildren.value?.children, val => {
  if (!val) return
  noMore = val.length < 80
  spliceChildren(val, { start: start.value, noMore })
}, { deep: 1 })
function loadMore() {
  start.value = children.at(-1)!
}
function onScroll(ev: Event) {
  const container = ev.target as HTMLElement
  if (container.scrollHeight - container.scrollTop - container.clientHeight < 200 && !noMore) {
    loadMore()
  }
}

const pathEntities = computed(() => dir.value ? expandAncestors(dir.value, props.rootId) : [])

const $q = useQuasar()

const dragHoverListeners = {
  dragover(event: DragEvent) {
    event.preventDefault()
  },
  dragenter({ currentTarget }: { currentTarget: HTMLElement }) {
    currentTarget.classList.add('bg-sur-dim')
  },
  dragleave({ currentTarget, relatedTarget }: { currentTarget: HTMLElement, relatedTarget: Node | null }) {
    if (relatedTarget && currentTarget.contains(relatedTarget)) return
    currentTarget.classList.remove('bg-sur-dim')
  },
  drop({ currentTarget }: { currentTarget: HTMLElement }) {
    currentTarget.classList.remove('bg-sur-dim')
  },
}

function onDragstart({ dataTransfer }: DragEvent, id: string) {
  if (!dataTransfer) return
  dataTransfer.setData('application/x-entity-id', id)
  dataTransfer.effectAllowed = 'move'
}
async function onDrop({ dataTransfer }: DragEvent, id: string) {
  if (!dataTransfer) return
  const sourceId = dataTransfer.getData('application/x-entity-id')
  if (sourceId) {
    if (!selected.has(sourceId)) {
      if (sourceId === id) return
      mutate(mutators.moveEntities({
        ids: [sourceId],
        to: id,
      }))
    } else {
      if (selected.has(id)) return
      mutate(mutators.moveEntities({
        ids: Array.from(selected),
        to: id,
      }))
    }
    exitSelectMode()
    return
  }
  const dropped = await filesFromDrop(dataTransfer)
  if (dropped.length) await uploadKnowledge(id, dropped)
}

const activeEntitiesStore = useActiveEntitiesStore()

function onEntityClick(entity: FullEntity) {
  if (selected.size) {
    selected.has(entity.id) ? selected.delete(entity.id) : selected.add(entity.id)
  } else if (entity.type === 'folder') {
    dirId.value = entity.id
  } else {
    emit('entityClick', entity)
  }
}
function openEntity(entity: FullEntity) {
  emit('entityClick', entity)
}

function canReparse(entity: FullEntity) {
  if (entity.type !== 'item') return false
  const status = itemParseStatus(entity.item, entity.conf)
  return status === 'failed' || status === 'unparsed'
}

const reparsingIds = reactive(new Set<string>())
async function reparseEntity(entity: FullEntity) {
  if (!workspaceStore.id || entity.type !== 'item' || reparsingIds.has(entity.id)) return
  reparsingIds.add(entity.id)
  try {
    const response = await client.api.kb.reparse.$post({
      json: { workspaceId: workspaceStore.id, id: entity.id },
    })
    if (!response.ok) {
      const text = await response.text()
      let message = text
      try {
        const body = JSON.parse(text) as { error?: string }
        message = body.error || text
      } catch {
        // Some infrastructure errors are returned as plain text.
      }
      throw new Error(message || `HTTP ${response.status}`)
    }
    $q.notify(t('Parsing…'))
  } catch (err) {
    $q.notify({
      message: t('Reparse failed: {0}', err instanceof Error ? err.message : String(err)),
      color: 'negative',
    })
  } finally {
    reparsingIds.delete(entity.id)
  }
}

async function downloadEntity(entity: FullEntity) {
  if (entity.type !== 'item' || !entity.item) return
  const cached = await getCached(entity.item.id)
  if (cached) exportFile(entityName(entity), cached)
  else window.open(getItemUrl(entity.item.id), '_blank')
}

function renameEntity(entity: FullEntity) {
  $q.dialog({
    title: t('Rename'),
    prompt: {
      model: entity.name ?? '',
      label: t('Name'),
    },
    cancel: true,
    ok: t('Rename'),
  }).onOk(name => {
    mutate(mutators.updateEntity({ id: entity.id, name }))
  })
}

function moveEntity(entity: FullEntity) {
  $q.dialog({
    component: SelectDirDialog,
    componentProps: {
      title: t('Move to'),
      exclude: [entity.id],
    },
  }).onOk((to: string) => {
    mutate(mutators.moveEntities({ ids: [entity.id], to }))
  })
}

function recycleEntity(entity: FullEntity) {
  $q.dialog({
    title: t('Move to Trash'),
    message: t('Are you sure you want to move "{0}" to trash?', entityName(entity)),
    cancel: true,
    ok: {
      label: t('Move to Trash'),
      color: 'negative',
      flat: true,
    },
  }).onOk(() => {
    mutate(mutators.recycleEntities({
      workspaceId: workspaceStore.id!,
      ids: [entity.id],
    }))
  })
}
const listRef = useTemplateRef('listRef')
const menuListRef = useTemplateRef('menuListRef')
function onContextmenu(id: string) {
  document.addEventListener('click', clickListener)
  selected.add(id)
}
const clickListener = (ev: MouseEvent) => {
  if (listRef.value?.$el?.contains(ev.target) || menuListRef.value?.$el?.contains(ev.target)) return
  exitSelectMode()
}
function exitSelectMode() {
  selected.clear()
  document.removeEventListener('click', clickListener)
}
onUnmounted(exitSelectMode)

const selectedOne = computed(() => selected.size === 1 ? childrenMap.value[selected.values().next().value!] : null)

function recycleSelected() {
  mutate(mutators.recycleEntities({
    workspaceId: workspaceStore.id!,
    ids: Array.from(selected),
  }))
  exitSelectMode()
}
function renameSelected() {
  const _selected = Array.from(selected)
  $q.dialog({
    title: t('Rename'),
    prompt: {
      model: selectedOne.value?.name ?? '',
      label: t('Name'),
    },
    cancel: true,
    ok: t('Rename'),
  }).onOk(name => {
    _selected.forEach(id => {
      mutate(mutators.updateEntity({
        id,
        name,
      }))
    })
  })
}
function moveSelected() {
  const _selected = Array.from(selected)
  $q.dialog({
    component: SelectDirDialog,
    componentProps: {
      title: t('Move to'),
      exclude: _selected,
    },
  }).onOk((dirId: string) => {
    mutate(mutators.moveEntities({
      ids: _selected,
      to: dirId,
    }))
  })
}
function editAcl(entity: FullEntity) {
  $q.dialog({
    component: FolderAclDialog,
    componentProps: { entity },
  })
}
function editTags(entity: FullEntity) {
  const current = (entity.conf?.tags ?? []).join(', ')
  $q.dialog({
    title: t('Tags'),
    prompt: {
      model: current,
      label: t('Comma-separated tags'),
    },
    cancel: true,
    ok: t('Save'),
  }).onOk((value: string) => {
    const tags = value.split(',').map(s => s.trim()).filter(Boolean)
    mutate(mutators.updateEntityConf({
      id: entity.id,
      updates: { tags },
    }))
  })
}
function changeIcon() {
  const entity = selectedOne.value!
  $q.dialog({
    component: PickAvatarDialog,
    componentProps: {
      defaultTab: 'icon',
      model: entityAvatar(entity),
      parentId: entity.id,
    },
  }).onOk((avatar: Avatar) => {
    mutate(mutators.updateEntity({
      id: entity.id,
      avatar,
    }))
  })
}
</script>
