import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'
import { session } from 'src/utils/identity-client'

export const useReadonlyStateStore = defineStore('readonlyState', () => {
  const workspaceStore = useWorkspaceStore()

  const message = computed(() => {
    if (!session.value.isPending && session.value.error) {
      return t('An error has occurred in the current connection.')
    }
    if (workspaceStore.member?.role === 'viewer') {
      return t('Your role is "Viewer"; you can only browse the content in this workspace and cannot make modifications.')
    }
    return null
  })
  const readonly = computed(() => message.value !== null)

  return {
    message,
    readonly,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useReadonlyStateStore, import.meta.hot))
}
