import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'
import { connectionState } from 'src/utils/zero-session'

export const useReadonlyStateStore = defineStore('readonlyState', () => {
  const workspaceStore = useWorkspaceStore()

  const message = computed(() => {
    if (connectionState.value.name === 'disconnected') {
      return t('Currently offline, you can only browse existing local content and cannot perform write operations.')
    }
    if (connectionState.value.name === 'error') {
      return t('An error has occurred in the current connection.')
    }
    if (workspaceStore.member?.role === 'guest') {
      return t('Your role is "Guest"; you can only browse the content in this workspace and cannot make modifications.')
    }
    return null
  })
  const readonly = computed(() => message.value !== null)

  return {
    connectionState,
    message,
    readonly,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useReadonlyStateStore, import.meta.hot))
}
