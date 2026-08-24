<template>
  <div
    view-styles
    flex="~ col"
  >
    <common-toolbar>
      <q-toolbar-title text-lg>
        {{ folderTitle }}
      </q-toolbar-title>
      <q-btn
        unelevated
        no-caps
        icon="sym_o_create_new_folder"
        :label="t('New folder')"
        @click="createFolder"
        bg-pri-c
        text-on-pri-c
      />
      <q-btn
        flat
        no-caps
        icon="sym_o_upload_file"
        :label="t('Upload files')"
        @click="selectFile(files => uploadKnowledge(currentId, files.map(file => ({ file, relativePath: file.name }))), { multiple: true })"
      />
      <q-btn
        flat
        no-caps
        icon="sym_o_drive_folder_upload"
        :label="t('Upload folder')"
        @click="selectFolder(files => uploadKnowledge(currentId, files))"
      />
      <q-btn
        flat
        no-caps
        icon="sym_o_chat"
        :label="t('Ask')"
        @click="askKnowledge"
      />
    </common-toolbar>
    <div
      flex-1
      min-h-0
      relative
      @dragenter.prevent="dragging = true"
      @dragover.prevent="dragging = true"
      @dragleave="onDragLeave"
      @drop.prevent="onDrop"
    >
      <entity-list
        v-model="currentId"
        flex-1
        min-h-0
        h-full
        @entity-click="onFileClick"
      >
        <template #empty>
          <div
            flex="~ col"
            items-center
            justify-center
            text-on-sur-var
            h-full
            px-6
            py-12
            text-center
          >
            <q-icon
              name="sym_o_folder_open"
              size="64px"
              mb-4
            />
            <div
              text-h6
              text-on-sur
            >
              {{ t('Drop files or folders here') }}
            </div>
            <div
              mt-2
              max-w="420px"
            >
              {{ t('Create a folder, then upload documents. Files are parsed automatically and can be asked about.') }}
            </div>
            <div
              flex
              gap-2
              mt-6
            >
              <q-btn
                unelevated
                no-caps
                icon="sym_o_create_new_folder"
                :label="t('New folder')"
                @click="createFolder"
                bg-pri-c
                text-on-pri-c
              />
              <q-btn
                outline
                no-caps
                icon="sym_o_upload_file"
                :label="t('Upload files')"
                @click="selectFile(files => uploadKnowledge(currentId, files.map(file => ({ file, relativePath: file.name }))), { multiple: true })"
              />
            </div>
          </div>
        </template>
      </entity-list>
      <div
        v-if="dragging"
        pointer-events-none
        abs-full
        flex
        items-center
        justify-center
        bg="pri/12"
        border="2 dashed pri"
      >
        <div text-h6>
          {{ t('Drop to upload and parse') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { useThisEntityConf } from 'src/composables/entity-conf'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { entityName } from 'src/utils/defaults'
import { useWorkspaceStore } from 'src/stores/workspace'
import CommonToolbar from 'src/components/CommonToolbar.vue'
import EntityList from 'src/components/EntityList.vue'
import { createEntity } from 'src/utils/create-entity'
import { selectFile } from 'src/utils/select-file'
import { filesFromDrop, selectFolder, uploadKnowledge } from 'src/utils/knowledge-upload'
import type { FullEntity } from 'app/src-shared/queries'
import { entityRoute } from 'src/utils/functions'
import { useAskKnowledge } from 'src/composables/ask-knowledge'

const props = defineProps<{
  id: string
}>()

const router = useRouter()
const currentId = ref(props.id)
watch(() => props.id, id => {
  currentId.value = id
})
watch(currentId, id => {
  if (id && id !== props.id) router.replace(`/folder/${id}`)
})

const { entity } = useThisEntityConf()
const dragging = ref(false)

const workspaceStore = useWorkspaceStore()
watch(() => entity.value?.rootId, rootId => {
  if (rootId && workspaceStore.id !== rootId) workspaceStore.id = rootId
})
const askKnowledge = useAskKnowledge()
const folderTitle = computed(() => {
  if (!entity.value) return ''
  if (entity.value.id === workspaceStore.id || entity.value.name === '/') return t('All files')
  return entityName(entity.value)
})

function createFolder() {
  createEntity(currentId.value, 'folder')
}

function onFileClick(entity: FullEntity) {
  const link = entityRoute(entity.type, entity.id)
  link && router.push(link)
}

function onDragLeave(ev: DragEvent) {
  const related = ev.relatedTarget as Node | null
  if (related && (ev.currentTarget as HTMLElement).contains(related)) return
  dragging.value = false
}

async function onDrop(ev: DragEvent) {
  dragging.value = false
  if (!ev.dataTransfer) return
  const dropped = await filesFromDrop(ev.dataTransfer)
  await uploadKnowledge(currentId.value, dropped)
}
</script>
