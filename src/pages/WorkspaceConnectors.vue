<template>
  <q-page p-4>
    <div
      text-h6
      mb-2
    >
      {{ t('Connectors') }}
    </div>
    <div
      text-on-sur-var
      mb-4
    >
      {{ t('Other agents can connect to this knowledge base via MCP. Create an API key and paste the config into your agent.') }}
    </div>
    <q-btn
      color="primary"
      unelevated
      :label="t('Create connector')"
      @click="create"
      mb-4
    />
    <q-list
      bordered
      separator
    >
      <q-item
        v-for="row in rows"
        :key="row.id"
      >
        <q-item-section>
          <q-item-label>{{ row.name }}</q-item-label>
          <q-item-label caption>
            {{ row.keyPrefix }}… · {{ row.mode }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-btn
            flat
            color="negative"
            :label="t('Revoke')"
            @click="revoke(row.id)"
          />
        </q-item-section>
      </q-item>
      <q-item v-if="!rows.length">
        <q-item-section class="text-on-sur-var">
          {{ t('No connectors yet.') }}
        </q-item-section>
      </q-item>
    </q-list>
  </q-page>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { useWorkspaceStore } from 'src/stores/workspace'
import { client } from 'src/utils/hc'
import { onMounted, ref } from 'vue'
import { Dialog, Notify } from 'quasar'
import { copyToClipboard } from 'quasar'

const workspaceStore = useWorkspaceStore()
const rows = ref<any[]>([])

async function load() {
  if (!workspaceStore.id) return
  const res = await client.api.connectors.$get({ query: { workspaceId: workspaceStore.id } })
  rows.value = await res.json() as any[]
}

async function create() {
  Dialog.create({
    title: t('Create connector'),
    prompt: { model: 'intranet-ima', label: t('Name') },
    cancel: true,
  }).onOk(async (name: string) => {
    const res = await client.api.connectors.$post({
      json: {
        workspaceId: workspaceStore.id!,
        name,
        mode: 'readwrite',
      },
    })
    const data = await res.json() as any
    if (data.apiKey) {
      await copyToClipboard(JSON.stringify(data.config, null, 2))
      Notify.create({
        message: t('API key created. MCP config copied to clipboard. Save the key now; it will not be shown again.'),
        timeout: 8000,
      })
    }
    await load()
  })
}

async function revoke(id: string) {
  await client.api.connectors[':id'].$delete({ param: { id } })
  await load()
}

onMounted(load)
</script>
