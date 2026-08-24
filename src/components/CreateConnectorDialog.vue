<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 480px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Create connector') }}
        </div>
        <div
          text-on-sur-var
          text-caption
          mt-1
        >
          {{ t('Other agents can connect to this knowledge base via MCP. The key is shown only once.') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <common-item :label="t('Name')">
            <a-input
              v-model="name"
              dense
              filled
              class="min-w-180px"
            />
          </common-item>
          <common-item
            :label="t('Note')"
            :caption="t('Optional. Who this connector is for.')"
          >
            <a-input
              v-model="note"
              dense
              filled
              class="min-w-180px"
            />
          </common-item>
          <common-item
            :label="t('Access')"
            :caption="t('Read can search and ask. Read and write can also create folders and notes.')"
          >
            <q-btn-toggle
              v-model="mode"
              unelevated
              no-caps
              toggle-color="primary"
              :options="[
                { label: t('Read only'), value: 'read' },
                { label: t('Read and write'), value: 'readwrite' },
              ]"
            />
          </common-item>
          <common-item
            :label="t('Folder root')"
            :caption="t('Empty means the whole workspace. Pick a folder to expose only that tree.')"
            clickable
            @click="pickFolder"
          >
            <div
              flex
              items-center
              gap-1
            >
              <span>{{ folderLabel }}</span>
              <q-btn
                v-if="folderRootId"
                flat
                dense
                round
                icon="sym_o_close"
                @click.stop="folderRootId = null"
              />
              <q-icon
                v-else
                name="sym_o_chevron_right"
              />
            </div>
          </common-item>
          <common-item
            :label="t('Expires in (days)')"
            :caption="t('Leave empty for no expiry.')"
          >
            <q-input
              v-model.number="expiresDays"
              type="number"
              dense
              filled
              clearable
              class="w-100px"
            />
          </common-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="primary"
          :label="t('Cancel')"
          @click="onDialogCancel"
        />
        <q-btn
          flat
          color="primary"
          :label="t('Create')"
          :loading="loading"
          :disable="!name.trim()"
          @click="create"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { computed, ref } from 'vue'
import { t } from 'src/utils/i18n'
import { client } from 'src/utils/hc'
import { rejectAfter } from 'src/utils/reject-after'
import { useWorkspaceStore } from 'src/stores/workspace'
import CommonItem from './CommonItem.vue'
import AInput from './AInput'
import SelectDirDialog from './SelectDirDialog.vue'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
const $q = useQuasar()
const workspaceStore = useWorkspaceStore()

const name = ref('intranet-ima')
const note = ref('')
const mode = ref<'read' | 'readwrite'>('read')
const folderRootId = ref<string | null>(null)
const expiresDays = ref<number | null>(null)
const loading = ref(false)

const folderLabel = computed(() => {
  if (!folderRootId.value || folderRootId.value === workspaceStore.id) return t('Whole workspace')
  return folderRootId.value
})

function pickFolder() {
  $q.dialog({
    component: SelectDirDialog,
    componentProps: { title: t('Folder root') },
  }).onOk((id: string) => {
    folderRootId.value = id === workspaceStore.id ? null : id
  })
}

async function create() {
  if (!workspaceStore.id || !name.value.trim()) return
  loading.value = true
  try {
    const expiresAt = expiresDays.value && expiresDays.value > 0
      ? new Date(Date.now() + expiresDays.value * 86400000).toISOString()
      : null
    const res = await Promise.race([
      client.api.connectors.$post({
        json: {
          workspaceId: workspaceStore.id,
          name: name.value.trim(),
          note: note.value.trim() || undefined,
          mode: mode.value,
          folderRootId: folderRootId.value,
          expiresAt,
        },
      }),
      rejectAfter(8000, t('Could not load connectors. Start the API server and try again.')),
    ])
    const data = await res.json() as any
    if (!res.ok || data.error) throw new Error(data.error || t('Failed to create connector'))
    onDialogOK(data)
  } catch (err) {
    $q.notify({
      type: 'negative',
      message: err instanceof Error ? err.message : String(err),
    })
  } finally {
    loading.value = false
  }
}
</script>
