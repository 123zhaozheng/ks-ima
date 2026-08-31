import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { useKbStore } from 'src/stores/knowledge-base'
import { t } from 'src/utils/i18n'
import { session } from 'src/utils/identity-client'

export const useReadonlyStateStore = defineStore('readonlyState', () => {
  const kbStore = useKbStore()

  const message = computed(() => {
    if (!session.value.isPending && session.value.error) {
      return t('An error has occurred in the current connection.')
    }
    if (kbStore.member?.role === 'viewer') {
      return t('Your role is read-only; you can browse the content in this knowledge base but cannot make changes.')
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
