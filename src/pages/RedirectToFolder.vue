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
          <div class="text-caption q-mt-md">{{ t('A platform administrator must assign you to a workspace.') }}</div>
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
import { connectionState, user } from 'src/utils/zero-session'
import { t } from 'src/utils/i18n'

const props = defineProps<{
  search?: boolean
}>()

useRequireLogin()

const router = useRouter()
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()
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

</script>
