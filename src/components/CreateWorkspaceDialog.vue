<template>
  <q-dialog
    v-model="show"
    @hide="name = ''"
  >
    <q-card min-w="360px">
      <q-card-section class="text-h6">
        {{ t('Create Workspace') }}
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="name"
          outlined
          autofocus
          :label="t('Workspace name')"
          data-testid="workspace-name-input"
          @keyup.enter="create"
        />
        <div class="tk-caption q-mt-sm">
          {{ t('You will become the administrator of the new workspace.') }}
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          :label="t('Cancel')"
        />
        <q-btn
          flat
          color="primary"
          :label="t('Create')"
          :loading="creating"
          :disable="!name.trim()"
          data-testid="workspace-create-button"
          @click="create"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Notify } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import { useWorkspaceStore } from 'src/stores/workspace'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  created: [workspaceId: string]
}>()

const show = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const name = ref('')
const creating = ref(false)
const queryClient = useQueryClient()
const workspaceStore = useWorkspaceStore()

async function create() {
  const workspaceName = name.value.trim()
  if (!workspaceName || creating.value) return
  creating.value = true
  try {
    const { data, error } = await identityClient.createSelfWorkspace({
      name: workspaceName,
    })
    if (error || !data) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Workspace created') })
    show.value = false
    // Membership list drives the workspace switcher; refresh then select it.
    await queryClient.invalidateQueries({ queryKey: ['workspaces', 'member'] })
    workspaceStore.switchWorkspace(data.id)
    emit('created', data.id)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
  } finally {
    creating.value = false
  }
}
</script>
