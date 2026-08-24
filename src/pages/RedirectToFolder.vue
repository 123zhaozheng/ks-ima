<template>
  <q-page-container>
    <q-page
      flex
      flex-center
      text-on-sur-var
    >
      <div
        text-center
        px-6
      >
        <template v-if="user.id && !workspaceStore.id && offline">
          <q-icon
            name="sym_o_cloud_off"
            size="56px"
          />
          <div
            text-h6
            mt-3
          >
            {{ t('Currently offline, you can only browse existing local content and cannot perform write operations.') }}
          </div>
        </template>
        <q-spinner
          v-else-if="user.id && !workspaceStore.id && !listReady"
          color="primary"
          size="40px"
        />
        <template v-else-if="user.id && !workspaceStore.id">
          <q-icon
            name="sym_o_folder_open"
            size="56px"
          />
          <div
            text-h6
            mt-3
          >
            {{ t('No workspace selected') }}
          </div>
          <q-btn
            unelevated
            no-caps
            color="primary"
            mt-4
            :label="t('Create workspace')"
            @click="createWorkspace"
          />
        </template>
      </div>
    </q-page>
  </q-page-container>
</template>
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useRequireLogin } from 'src/composables/require-login'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'
import { connectionState, mutate, user } from 'src/utils/zero-session'
import { t } from 'src/utils/i18n'
import { useQuasar } from 'quasar'
import { mutators } from 'app/src-shared/mutators'
import { genId, genIds } from 'app/src-shared/utils/id'

const props = defineProps<{
  search?: boolean
}>()

useRequireLogin()

const router = useRouter()
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()
const $q = useQuasar()
const listReady = computed(() => workspaceStore.workspacesStatus === 'complete')
const offline = computed(() => {
  const name = connectionState.value.name
  return name === 'disconnected' || name === 'error'
})

watch(() => workspaceStore.id, id => {
  if (!id) return
  router.replace(`/folder/${id}`)
  if (props.search) uiStateStore.searchDialogOpen = true
}, { immediate: true })

function createWorkspace() {
  $q.dialog({
    title: t('Create Workspace'),
    prompt: {
      model: '',
      label: t('Name'),
    },
    cancel: true,
    ok: t('Create'),
  }).onOk(async name => {
    const id = genId()
    await mutate(mutators.createWorkspace({
      ids: [id, ...genIds(22)],
      name,
    })).client
    workspaceStore.switchWorkspace(id)
  })
}
</script>
