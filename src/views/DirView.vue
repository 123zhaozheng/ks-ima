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
        icon="sym_o_note_add"
        :label="t('New note')"
        @click="createNote"
      />
      <q-btn
        flat
        no-caps
        icon="sym_o_upload_file"
        :label="t('Upload files')"
        :disable="!storageAvailable"
        :title="storageAvailable ? t('Upload files') : t('File storage is unavailable')"
        @click="fileInput?.click()"
      />
      <input ref="fileInput" type="file" multiple hidden @change="uploadFiles">
      <q-btn
        flat
        no-caps
        icon="sym_o_drive_folder_upload"
        :label="t('Upload folder')"
        disable
        :title="t('File storage migration is pending')"
      />
    </common-toolbar>
    <div
      flex-1
      min-h-0
      relative
      @dragenter.prevent
      @dragover.prevent
    >
      <knowledge-list
        :folder-id="currentId"
        flex-1
        min-h-0
        h-full
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
              {{ t('No items in this folder') }}
            </div>
            <div
              mt-2
              max-w="420px"
            >
              {{ t('Create a folder or note. File storage will become available after migration.') }}
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
                icon="sym_o_note_add"
                :label="t('New note')"
                @click="createNote"
              />
            </div>
          </div>
        </template>
      </knowledge-list>
    </div>
  </div>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useWorkspaceStore } from 'src/stores/workspace'
import CommonToolbar from 'src/components/CommonToolbar.vue'
import KnowledgeList from 'src/components/KnowledgeList.vue'
import { identityClient } from 'src/utils/identity-client'
import { knowledgeClient } from 'src/api/knowledge-client'
import { Notify, useQuasar } from 'quasar'
import { useKnowledgeCapabilities, useKnowledgeMutations } from 'src/composables/use-knowledge'
import { createTask, tasks } from 'src/utils/tasks'

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

const workspaceStore = useWorkspaceStore()
const folderTitle = computed(() => currentId.value === workspaceStore.id ? t('All files') : t('Knowledge'))
const $q = useQuasar()
const capabilities = useKnowledgeCapabilities(() => workspaceStore.id)
const storageAvailable = computed(() => capabilities.data.value?.upload.status === 'available')
const fileInput = ref<HTMLInputElement>()
const mutations = useKnowledgeMutations()
const uploadPrefix = ref('')

watch(() => workspaceStore.id, workspaceId => {
  for (const task of tasks) {
    if (uploadPrefix.value && task.id.startsWith(uploadPrefix.value) && task.status === 'running') task.abort()
  }
  uploadPrefix.value = workspaceId ? `upload:${workspaceId}:` : ''
})

function createFolder() {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('New folder'), prompt: { model: '', type: 'text' }, cancel: true }).onOk(async (name: string) => {
    const result = await identityClient.createWorkspaceFolder(workspaceStore.id!, { parentId: currentId.value, name })
    if (result.error) Notify.create({ type: 'negative', message: result.error.message })
  })
}

function uploadFiles(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files ?? [])
  for (const file of files) {
    const task = createTask({ id: `${uploadPrefix.value}${file.name}:${Date.now()}`, title: file.name }, async ({ abortSignal, updateProgress }) => {
      await mutations.uploadFile.mutateAsync({ folderId: currentId.value, file, title: file.name, signal: abortSignal, onProgress: value => updateProgress({ progress: value, progressText: `${Math.round(value * 100)}%` }) })
    })
    task.promise.catch(error => Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Upload failed') }))
  }
  ;(event.target as HTMLInputElement).value = ''
}

function createNote() {
  $q.dialog({ title: t('New note'), prompt: { model: '', type: 'text', label: t('Title') }, cancel: true }).onOk(async (title: string) => {
    const result = await knowledgeClient.createNote(currentId.value, { title, markdown: '' })
    router.push(`/knowledge/${result.id}`)
  }).onCancel(() => undefined)
}
</script>
