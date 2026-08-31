<template>
  <q-dialog
    v-model="show"
    persistent
  >
    <q-card min-w="440px">
      <q-card-section
        flex
        items-center
      >
        <div class="text-h6">
          上传文件
        </div>
        <q-space />
        <q-btn
          flat
          dense
          round
          icon="sym_o_close"
          title="关闭"
          :disable="busy"
          @click="show = false"
        />
      </q-card-section>
      <q-card-section>
        <file-input-area
          :accept="accept"
          multiple
          data-testid="upload-dropzone"
          @input="addFile"
        />
        <q-list
          v-if="tasks.length"
          mt-3
        >
          <q-item
            v-for="task in tasks"
            :key="task.id"
            dense
          >
            <q-item-section
              avatar
              min-w-0
            >
              <q-icon :name="statusIcon(task.status)" />
            </q-item-section>
            <q-item-section>
              <q-item-label
                text-ellipsis
                whitespace-nowrap
                overflow-hidden
              >
                {{ task.file.name }}
              </q-item-label>
              <q-linear-progress
                v-if="task.status === 'uploading'"
                :value="task.progress"
                color="primary"
                size="4px"
                mt-1
              />
              <q-item-label
                v-else-if="task.status === 'error'"
                caption
                text-err
              >
                {{ task.error }}
              </q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-if="busy"
          flat
          label="停止"
          @click="stop"
        />
        <q-btn
          v-close-popup
          flat
          color="primary"
          label="关闭"
          :disable="busy"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Notify } from 'quasar'
import FileInputArea from 'src/components/FileInputArea.vue'
import { useKnowledgeMutations } from 'src/composables/use-knowledge'
import { apiErrorMessage } from 'src/utils/api-error'

const props = defineProps<{
  modelValue: boolean
  folderId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
}>()

// Keep in sync with the digest allow-list in use-knowledge.ts.
const accept = '.txt,.md,.markdown,.json,.pdf,.docx,.xlsx,.xls'

const show = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

type TaskStatus = 'queued' | 'uploading' | 'done' | 'error'
interface UploadTask {
  id: number
  file: File
  progress: number
  status: TaskStatus
  error?: string
}

const tasks = ref<UploadTask[]>([])
const busy = ref(false)
let nextId = 1
let processing = false
let abort: AbortController | undefined
const mutations = useKnowledgeMutations()

watch(show, value => {
  if (!value && !busy.value) tasks.value = []
})

function statusIcon(status: TaskStatus) {
  if (status === 'done') return 'sym_o_check_circle'
  if (status === 'error') return 'sym_o_error'
  return 'sym_o_upload_file'
}

function addFile(file: File) {
  tasks.value.push({ id: nextId++, file, progress: 0, status: 'queued' })
  processQueue().catch(() => undefined)
}

async function processQueue() {
  if (processing) return
  processing = true
  busy.value = true
  try {
    for (const task of tasks.value) {
      if (task.status !== 'queued') continue
      if (abort?.signal.aborted) break
      task.status = 'uploading'
      abort = new AbortController()
      try {
        await mutations.uploadFile.mutateAsync({
          folderId: props.folderId,
          file: task.file,
          title: task.file.name,
          signal: abort.signal,
          onProgress: value => { task.progress = value },
        })
        task.status = 'done'
        task.progress = 1
      } catch (error) {
        if ((error as DOMException).name === 'AbortError') {
          task.status = 'queued'
          break
        }
        task.status = 'error'
        task.error = apiErrorMessage(error, '上传失败')
      }
    }
    if (tasks.value.some(task => task.status === 'done') && !abort?.signal.aborted) {
      Notify.create({ type: 'positive', message: '上传完成' })
    }
  } finally {
    processing = false
    busy.value = tasks.value.some(task => task.status === 'queued' || task.status === 'uploading')
    abort = undefined
  }
}

function stop() {
  abort?.abort()
  tasks.value = tasks.value.filter(task => task.status === 'done' || task.status === 'error')
}

onBeforeUnmount(() => abort?.abort())
</script>
