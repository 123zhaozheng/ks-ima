<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Update Workspace') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <common-item :label="t('Name')">
            <q-input
              v-model="workspace.name"
              dense
            />
          </common-item>
          <common-item :label="t('Plan')">
            <plan-select
              v-model="workspace.planId"
              dense
              class="w-120px"
            />
          </common-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="err"
          :label="t('Delete')"
          @click="deleteWorkspace"
          :loading="deleting"
        />
        <q-space />
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
          @click="update"
          :loading
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { reactive, ref } from 'vue'
import { client } from 'src/utils/hc'
import type { Row } from '@rocicorp/zero'
import { diff } from 'app/src-shared/utils/functions'
import PlanSelect from './PlanSelect.vue'
import CommonItem from '../../components/CommonItem.vue'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const props = defineProps<{
  workspace: Row['workspace']
}>()

const workspace = reactive({ ...props.workspace })

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const loading = ref(false)
const deleting = ref(false)
const $q = useQuasar()
function update() {
  loading.value = true
  client.api.admin.updateWorkspace.$post({
    json: {
      id: props.workspace.id,
      ...diff(props.workspace, workspace),
    },
  }).then(async res => {
    const data = await res.json()
    if ('error' in data) throw new Error(data.error)
    onDialogOK()
  }).catch(err => {
    $q.notify({
      message: t('Failed to update workspace: {0}', err.message),
      color: 'negative',
    })
  }).finally(() => {
    loading.value = false
  })
}
function deleteWorkspace() {
  $q.dialog({
    title: t('Delete Workspace'),
    message: t('Are you sure you want to delete workspace "{0}"?', props.workspace.name),
    cancel: true,
    ok: {
      label: t('Delete'),
      color: 'negative',
      flat: true,
    },
  }).onOk(() => {
    deleting.value = true
    client.api.admin.deleteWorkspace.$post({
      json: { id: props.workspace.id },
    }).then(async res => {
      const data = await res.json()
      if ('error' in data) throw new Error(data.error)
      onDialogOK()
    }).catch(err => {
      $q.notify({
        message: t('Failed to delete workspace: {0}', err.message),
        color: 'negative',
      })
    }).finally(() => {
      deleting.value = false
    })
  })
}
</script>
