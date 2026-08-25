<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Delete Workspace') }}
        </div>
      </q-card-section>
      <q-card-section py-0>
        {{ t('Are you sure you want to delete this workspace?') }}
        <strong>
          {{ t('All data in this workspace will be deleted irreversibly.') }}
        </strong>
        {{ t('If you are sure, enter the workspace name to continue.') }}
      </q-card-section>
      <q-card-section pb-2>
        <workspace-item
          :workspace
          :members="workspace.members"
        />
      </q-card-section>
      <q-card-section py-2>
        <q-input
          v-model="name"
          :label="t('Workspace Name')"
        />
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
          color="err"
          :label="t('Delete')"
          @click="deleteWorkspace"
          :loading
          :disable="!match"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { computed, ref } from 'vue'
import WorkspaceItem from './WorkspaceItem.vue'
import type { FullWorkspace } from 'app/src-shared/queries'
import { mutate } from 'src/utils/zero-session'
import { mutators } from 'app/src-shared/mutators'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const props = defineProps<{
  workspace: FullWorkspace
}>()

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const name = ref('')

const match = computed(() => name.value === props.workspace.name)

const $q = useQuasar()
const loading = ref(false)
function deleteWorkspace() {
  loading.value = true
  mutate(mutators.deleteWorkspace(props.workspace.id)).server.then(() => {
    onDialogOK()
  }).catch(err => {
    console.error(err)
    $q.notify({
      message: t('Failed to delete workspace: {0}', err.message),
      color: 'negative',
    })
  }).finally(() => {
    loading.value = false
  })
}
</script>
