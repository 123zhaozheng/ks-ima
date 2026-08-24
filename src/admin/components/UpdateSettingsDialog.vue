<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 500px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Global Settings') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list v-if="value">
          <common-item :label="t('Default chat model')">
            <model-select
              :model-value="value.defaultChatModel"
              @update:model-value="updates.defaultChatModel = $event"
              dense
            />
          </common-item>
          <common-item :label="t('Default chat title model')">
            <model-select
              :model-value="value.defaultChatTitleModel"
              @update:model-value="updates.defaultChatTitleModel = $event"
              dense
            />
          </common-item>
          <common-item
            :label="t('Embedding model')"
            :caption="t('Platform default. A workspace can override this under Models.')"
          >
            <model-select
              :model-value="value.embeddingModelId"
              @update:model-value="updates.embeddingModelId = $event"
              dense
            />
          </common-item>
          <common-item
            :label="t('Rerank model')"
            :caption="t('Platform default. A workspace can override this under Models.')"
          >
            <model-select
              :model-value="value.rerankModelId"
              @update:model-value="updates.rerankModelId = $event"
              dense
            />
          </common-item>
          <common-item :label="t('Max workspaces per user')">
            <q-input
              :model-value="value.maxWorkspacesPerUser"
              @update:model-value="updates.maxWorkspacesPerUser = parseInt($event as string)"
              type="number"
              dense
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
          :label="t('Update')"
          @click="updateSettings"
          :loading
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { computed, reactive, ref } from 'vue'
import CommonItem from '../../components/CommonItem.vue'
import { queries } from 'app/src-shared/queries'
import { useQuery } from 'src/composables/zero/query'
import ModelSelect from 'src/components/ModelSelect.vue'
import { client } from 'src/utils/hc'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { data: settings } = useQuery(() => queries.globalSettings())
const updates = reactive<Record<string, any>>({})
const value = computed(() => settings.value && {
  ...settings.value,
  ...updates,
})

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const loading = ref(false)
const $q = useQuasar()
function updateSettings() {
  loading.value = true
  client.api.admin.updateGlobalSettings.$post({
    json: {
      id: settings.value!.id,
      ...updates,
    },
  }).then(async res => {
    const data = await res.json()
    if ('error' in data) throw new Error(data.error)
    onDialogOK()
  }).catch(err => {
    $q.notify({
      message: t('Failed to update settings: {0}', err.message),
      color: 'negative',
    })
  }).finally(() => {
    loading.value = false
  })
}
</script>
