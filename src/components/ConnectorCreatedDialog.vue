<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    persistent
  >
    <q-card style="width: min(92vw, 640px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Save this key now') }}
        </div>
        <div
          text-warn
          text-caption
          mt-1
        >
          {{ t('It will not be shown again. Paste it into the agent, then close this dialog.') }}
        </div>
      </q-card-section>
      <q-card-section py-0>
        <q-input
          :model-value="apiKey"
          readonly
          filled
          dense
          type="textarea"
          autogrow
        >
          <template #append>
            <q-btn
              flat
              dense
              no-caps
              :label="t('Copy')"
              @click="copyText(apiKey)"
            />
          </template>
        </q-input>
        <div
          text-on-sur-var
          text-caption
          mt-3
          mb-1
        >
          {{ t('Service URL') }}: {{ mcpUrl }}
        </div>
        <div
          v-if="probeStatus === 'ok'"
          text-suc
          text-caption
          mt-2
        >
          {{ t('Connected. This key can list MCP tools.') }}
          {{ probeTools.join(', ') }}
        </div>
        <div
          v-else-if="probeStatus === 'fail'"
          text-err
          text-caption
          mt-2
        >
          {{ probeError }}
        </div>
        <div
          v-else
          text-on-sur-var
          text-caption
          mt-2
        >
          {{ t('Testing connection…') }}
        </div>
        <q-tabs
          v-model="tab"
          dense
          no-caps
          active-color="primary"
          align="left"
        >
          <q-tab
            name="cursor"
            :label="t('Cursor')"
          />
          <q-tab
            name="claude"
            :label="t('Claude Desktop')"
          />
          <q-tab
            name="json"
            :label="t('JSON')"
          />
        </q-tabs>
        <q-tab-panels
          v-model="tab"
          animated
        >
          <q-tab-panel
            v-for="panel in panels"
            :key="panel.name"
            :name="panel.name"
            px-0
          >
            <div
              text-caption
              text-on-sur-var
              mb-2
            >
              {{ panel.hint }}
            </div>
            <q-input
              :model-value="panel.body"
              readonly
              filled
              type="textarea"
              autogrow
            >
              <template #append>
                <q-btn
                  flat
                  dense
                  no-caps
                  :label="t('Copy')"
                  @click="copyText(panel.body)"
                />
              </template>
            </q-input>
          </q-tab-panel>
        </q-tab-panels>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          unelevated
          no-caps
          color="primary"
          :label="t('I have saved the key')"
          @click="onDialogOK()"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, copyToClipboard, Notify } from 'quasar'
import { computed, onMounted, ref } from 'vue'
import { t } from 'src/utils/i18n'
import { claudeDesktopMcpConfig, cursorMcpConfig, mcpHttpUrl, prettyJson, probeMcpConnection } from 'src/utils/mcp-config'

const props = defineProps<{
  apiKey: string
}>()

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()
const tab = ref('cursor')
const mcpUrl = mcpHttpUrl()
const probeStatus = ref<'pending' | 'ok' | 'fail'>('pending')
const probeError = ref('')
const probeTools = ref<string[]>([])

const panels = computed(() => [
  {
    name: 'cursor',
    hint: t('Paste into Cursor MCP settings (mcp.json). Dev uses http://127.0.0.1:3000/api/mcp, not the Vite port.'),
    body: prettyJson(cursorMcpConfig(props.apiKey)),
  },
  {
    name: 'claude',
    hint: t('Claude Desktop uses stdio. This template runs mcp-remote as a local bridge, with --allow-http for intranet URLs.'),
    body: prettyJson(claudeDesktopMcpConfig(props.apiKey)),
  },
  {
    name: 'json',
    hint: t('Generic Streamable HTTP config for internal agents.'),
    body: prettyJson(cursorMcpConfig(props.apiKey)),
  },
])

async function copyText(text: string) {
  await copyToClipboard(text)
  Notify.create({ message: t('Copied'), type: 'positive', timeout: 1500 })
}

onMounted(async () => {
  try {
    const result = await probeMcpConnection(props.apiKey, mcpUrl)
    probeTools.value = result.tools
    probeStatus.value = 'ok'
  } catch (err) {
    probeStatus.value = 'fail'
    probeError.value = err instanceof Error ? err.message : String(err)
  }
})
</script>
