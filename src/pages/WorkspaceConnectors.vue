<template>
  <q-page-container>
    <q-page
      v-if="workspaceStore.id"
      max-w="800px"
      mx-a
      py-2
    >
      <q-list>
        <q-item-label header>
          {{ t('Connectors') }}
        </q-item-label>
        <q-item>
          <q-item-section>
            <q-item-label>
              {{ t('Other agents connect to this knowledge base as an MCP server. This product does not install other MCP plugins.') }}
            </q-item-label>
            <q-item-label caption>
              {{ mcpUrl }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-btn
              flat
              dense
              round
              icon="sym_o_content_copy"
              :title="t('Copy')"
              @click="copyUrl"
            />
            <q-btn
              unelevated
              no-caps
              color="primary"
              :label="t('Create connector')"
              @click="openCreate"
            />
          </q-item-section>
        </q-item>

        <q-item
          v-for="row in rows"
          :key="row.id"
        >
          <q-item-section>
            <q-item-label>{{ row.name }}</q-item-label>
            <q-item-label caption>
              {{ row.keyPrefix }}… · {{ modeLabel(row.mode) }}
              <span v-if="row.folderRootId"> · {{ t('Folder-scoped') }}</span>
              <span v-if="row.expiresAt"> · {{ t('Expires') }} {{ formatTime(row.expiresAt) }}</span>
              <span v-if="row.lastUsedAt"> · {{ t('Last used') }} {{ formatTime(row.lastUsedAt) }}</span>
              <span v-else-if="row.note"> · {{ row.note }}</span>
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <div
              flex
              items-center
              gap-1
            >
              <q-btn
                flat
                no-caps
                :label="t('Rotate key')"
                @click="rotate(row.id)"
              />
              <q-btn
                flat
                no-caps
                color="negative"
                :label="t('Revoke')"
                @click="revoke(row.id)"
              />
            </div>
          </q-item-section>
        </q-item>
        <q-item
          v-if="loadingList"
          text-on-sur-var
        >
          <q-item-section>
            {{ t('Loading connectors…') }}
          </q-item-section>
        </q-item>
        <q-item
          v-else-if="loadError"
          text-err
        >
          <q-item-section>
            {{ loadError }}
          </q-item-section>
        </q-item>
        <q-item
          v-else-if="!rows.length"
          text-on-sur-var
        >
          <q-item-section>
            {{ t('No connectors yet. Create one to let Cursor or another agent ask this library.') }}
          </q-item-section>
        </q-item>
      </q-list>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { useWorkspaceStore } from 'src/stores/workspace'
import { client } from 'src/utils/hc'
import { onMounted, ref, watch } from 'vue'
import { copyToClipboard, useQuasar } from 'quasar'
import CreateConnectorDialog from 'src/components/CreateConnectorDialog.vue'
import ConnectorCreatedDialog from 'src/components/ConnectorCreatedDialog.vue'
import { mcpHttpUrl } from 'src/utils/mcp-config'
import { rejectAfter } from 'src/utils/reject-after'

type ConnectorRow = {
  id: string
  name: string
  note?: string | null
  keyPrefix: string
  mode: 'read' | 'readwrite'
  folderRootId?: string | null
  expiresAt?: string | Date | null
  lastUsedAt?: string | Date | null
}

const workspaceStore = useWorkspaceStore()
const $q = useQuasar()
const rows = ref<ConnectorRow[]>([])
const mcpUrl = mcpHttpUrl()
const loadError = ref('')
const loadingList = ref(false)

async function load() {
  if (!workspaceStore.id) return
  loadingList.value = true
  try {
    const res = await Promise.race([
      client.api.connectors.$get({ query: { workspaceId: workspaceStore.id } }),
      rejectAfter(5000),
    ])
    if (!res.ok) {
      rows.value = []
      loadError.value = t('Could not load connectors. Start the API server and try again.')
      return
    }
    const data = await res.json()
    if (!Array.isArray(data)) {
      rows.value = []
      loadError.value = t('Could not load connectors. Start the API server and try again.')
      return
    }
    rows.value = data as ConnectorRow[]
    loadError.value = ''
  } catch {
    rows.value = []
    loadError.value = t('Could not load connectors. Start the API server and try again.')
  } finally {
    loadingList.value = false
  }
}

function modeLabel(mode: string) {
  return mode === 'readwrite' ? t('Read and write') : t('Read only')
}

function formatTime(value: string | Date) {
  return new Date(value).toLocaleString()
}

function copyUrl() {
  copyToClipboard(mcpUrl)
  $q.notify({ message: t('Copied'), type: 'positive', timeout: 1500 })
}

function openCreate() {
  $q.dialog({
    component: CreateConnectorDialog,
  }).onOk((data: { apiKey?: string }) => {
    if (data?.apiKey) {
      $q.dialog({
        component: ConnectorCreatedDialog,
        componentProps: { apiKey: data.apiKey },
      })
    }
    load()
  })
}

function rotate(id: string) {
  $q.dialog({
    title: t('Rotate key'),
    message: t('The old key stops working immediately and a new key is shown once.'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    const res = await client.api.connectors[':id'].rotate.$post({ param: { id } })
    const data = await res.json() as { apiKey?: string, error?: string }
    if (data.apiKey) {
      $q.dialog({
        component: ConnectorCreatedDialog,
        componentProps: { apiKey: data.apiKey },
      })
    } else if (data.error) {
      $q.notify({ type: 'negative', message: data.error })
    }
    load()
  })
}

function revoke(id: string) {
  $q.dialog({
    title: t('Revoke'),
    message: t('This key will stop working immediately.'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    await client.api.connectors[':id'].$delete({ param: { id } })
    await load()
  })
}

watch(() => workspaceStore.id, load)
onMounted(load)
</script>
