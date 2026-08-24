<template>
  <div
    view-styles
    flex="~ col"
  >
    <common-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_arrow_back"
        :title="t('Back')"
        @click="goBack"
      />
      <q-toolbar-title>
        <div text-lg>
          {{ entityName(entity) }}
        </div>
        <div
          v-if="parseLabel"
          text-sm
          :class="parseClass"
        >
          {{ parseLabel }}
        </div>
      </q-toolbar-title>
      <q-btn
        icon="sym_o_more_vert"
        text-on-sur-var
        flat
        dense
        round
        ml-a
      >
        <q-menu>
          <q-list>
            <menu-item
              :label="t('Download')"
              icon="sym_o_download"
              @click="download"
            />
            <menu-item
              :label="t('Download link')"
              icon="sym_o_link"
              @click="copyDownloadLink"
            />
            <menu-item
              :label="t('Reparse')"
              icon="sym_o_sync"
              @click="reparse"
            />
          </q-list>
        </q-menu>
      </q-btn>
    </common-toolbar>

    <q-tabs
      v-model="tab"
      active-color="primary"
      align="left"
      no-caps
      :breakpoint="0"
      dense
    >
      <q-tab
        v-if="previewMode"
        name="preview"
        :label="t('Preview')"
      />
      <q-tab
        v-if="item.text != null"
        name="text"
        :label="t('Text')"
      />
      <q-tab
        v-if="item.blobId"
        name="file"
        :label="t('File')"
      />
    </q-tabs>
    <div
      of-y-auto
      grow
    >
      <div
        v-if="tab === 'preview'"
        p-3
        h-full
      >
        <img
          v-if="previewMode === 'image' && fileUrl"
          :src="fileUrl"
          max-w-full
          max-h-full
        >
        <img
          v-else-if="previewMode === 'svg'"
          :src="`data:image/svg+xml,${encodeURIComponent(item.text!)}`"
          max-w-full
          max-h-full
        >
        <file-preview
          v-else-if="(previewMode === 'pdf' || previewMode === 'docx' || previewMode === 'xlsx') && item.id"
          :item-id="item.id"
          :kind="previewMode"
        />
        <video
          v-else-if="previewMode === 'video' && fileUrl"
          :src="fileUrl"
          controls
          max-w-full
        />
        <audio
          v-else-if="previewMode === 'audio' && fileUrl"
          :src="fileUrl"
          controls
        />
        <md-preview
          v-else-if="previewMode === 'markdown'"
          :model-value="item.text!"
          v-bind="mdPreviewProps"
          bg-sur
        />
        <pre
          v-else-if="previewMode === 'text'"
          whitespace-pre-wrap
          font-sans
        >{{ item.text }}</pre>
      </div>
      <div
        v-if="tab === 'text'"
        p-2
        flex="~ col"
        h="full"
      >
        <code-editor
          :model-value="itemProxy.text ?? ''"
          :language="item.language ?? undefined"
          @update:model-value="updateItemProxy({ text: $event })"
          grow
          of-y-auto
        />
        <div
          flex
          mt-2
        >
          <a-input
            :label="t('Language')"
            :model-value="item.language"
            @change="updateItem({ language: $event })"
            outlined
            dense
            class="ml-a"
          />
        </div>
      </div>
      <q-list
        v-else-if="tab === 'file'"
        py-2
      >
        <common-item :label="t('MIME Type')">
          <a-input
            :model-value="item.mimeType"
            @change="updateItem({ mimeType: $event })"
            filled
            dense
            class="min-w-120px max-w-250px"
            field-sizing-content
          />
        </common-item>
        <common-item
          v-if="item.blob"
          :label="t('Size')"
        >
          {{ formatBytes(item.blob.size) }}
        </common-item>
        <common-item
          v-if="item.blob"
          label="SHA-256"
        >
          <div
            flex
            items-center
          >
            <span>{{ textBeginning(base64ToHex(item.blob.sha256), 12) }}</span>
            <copy-btn
              :value="base64ToHex(item.blob!.sha256)"
              flat
              round
              size="sm"
            />
          </div>
        </common-item>
        <common-item :label="t('Created At')">
          {{ idDateString(item.id) }}
        </common-item>
      </q-list>
      <div
        v-else-if="tab === 'empty'"
        flex
        items-center
        justify-center
        h-full
      >
        <span mx-4>{{ t('No content currently. This may be because the upload has not been completed or the upload was interrupted.') }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { mutators } from 'app/src-shared/mutators'
import type { FullItem } from 'app/src-shared/queries'
import { base64ToHex } from 'app/src-shared/utils/functions'
import { idDateString } from 'app/src-shared/utils/id'
import { copyToClipboard, exportFile, useQuasar } from 'quasar'
import CommonItem from 'src/components/CommonItem.vue'
import AInput from 'src/components/AInput'
import CopyBtn from 'src/components/CopyBtn.vue'
import MenuItem from 'src/components/MenuItem.vue'
import { useThisEntityConf } from 'src/composables/entity-conf'
import { mutate } from 'src/utils/zero-session'
import { getCached, getDownloadUrl } from 'src/utils/blob-cache'
import { entityName } from 'src/utils/defaults'
import { formatBytes, getItemUrl, textBeginning } from 'src/utils/functions'
import { itemParseStatus } from 'src/utils/knowledge'
import { t } from 'src/utils/i18n'
import { computed, ref, toRef } from 'vue'
import { useRouter } from 'vue-router'
import CommonToolbar from 'src/components/CommonToolbar.vue'
import { useMdProps } from 'src/composables/md-props'
import { useBlobURL } from 'src/composables/blob-url'
import { MdPreview } from 'md-editor-v3'
import CodeEditor from 'src/components/CodeEditor.vue'
import FilePreview from 'src/components/FilePreview.vue'
import { useEditProxy } from 'src/composables/state-proxy'
import { useWorkspaceStore } from 'src/stores/workspace'
import { client } from 'src/utils/hc'

const props = defineProps<{
  item: FullItem
}>()

const { entity } = useThisEntityConf()
const parseStatus = computed(() => itemParseStatus(props.item, entity.value?.conf))
const parseLabel = computed(() => {
  if (parseStatus.value === 'ready') {
    return entity.value?.conf?.indexed === true
      ? t('Parsed · Vector indexed')
      : t('Parsed · Keyword only')
  }
  if (parseStatus.value === 'parsing') return t('Parsing…')
  if (parseStatus.value === 'unparsed') return t('No text extracted')
  if (parseStatus.value === 'failed') return t('Parse failed')
  return ''
})
const parseClass = computed(() => {
  if (parseStatus.value === 'ready') return 'text-pri'
  if (parseStatus.value === 'unparsed' || parseStatus.value === 'failed') return 'text-warn'
  return 'text-on-sur-var'
})

const previewMode = computed(() => {
  const { item } = props
  const mime = item.mimeType ?? ''
  const name = entity.value?.name ?? ''
  if (mime.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp)$/i.test(name)) return 'image'
  if (item.text && item.language === 'svg') return 'svg'
  if (mime === 'application/pdf' || name.toLowerCase().endsWith('.pdf')) return 'pdf'
  if (mime.includes('word') || /\.docx$/i.test(name)) return 'docx'
  if (mime.includes('spreadsheet') || mime.includes('excel') || /\.xlsx?$/i.test(name)) return 'xlsx'
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('audio/')) return 'audio'
  if (item.text && (item.language === 'markdown' || /\.md$/i.test(name))) return 'markdown'
  if (item.text) return 'text'
  return null
})
const tab = ref((() => {
  if (previewMode.value) return 'preview'
  if (props.item.blobId) return 'file'
  if (props.item.text != null) return 'text'
  return 'empty'
})())
const fileUrl = useBlobURL(computed(() => {
  if (['image', 'video', 'audio'].includes(previewMode.value ?? '')) return props.item.id
  return null
}))
const router = useRouter()
const workspaceStore = useWorkspaceStore()

function goBack() {
  router.push(`/folder/${entity.value?.parentId || workspaceStore.id}`)
}

function updateItem(updates: {
  text?: string
  mimeType?: string
  language?: string
}) {
  mutate(mutators.updateItem({ id: props.item.id, ...updates }))
}

async function download() {
  const cached = await getCached(props.item.id)
  const name = entityName(entity.value)
  if (cached) {
    exportFile(name, cached)
  } else {
    window.open(getItemUrl(props.item.id), '_blank')
  }
}
const $q = useQuasar()
function copyDownloadLink() {
  getDownloadUrl(props.item.id)
    .then(({ url }) => copyToClipboard(url))
    .then(() => {
      $q.notify(t('Download link copied to clipboard'))
    })
    .catch(err => {
      console.error(err)
      $q.notify(t('Failed to get download link: {0}', err.message))
    })
}

async function reparse() {
  if (!workspaceStore.id) return
  try {
    const response = await client.api.kb.reparse.$post({
      json: { workspaceId: workspaceStore.id, id: props.item.id },
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
  }
}

const { mdPreviewProps } = useMdProps()

const { value: itemProxy, update: updateItemProxy } = useEditProxy(
  toRef(props, 'item'),
  ['id', 'text'],
  (id, updates) => {
    mutate(mutators.updateItem({ id, ...updates }))
  },
  { type: 'debounce', wait: 1000 },
)
</script>
