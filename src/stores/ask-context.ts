import { acceptHMRUpdate, defineStore } from 'pinia'
import { computed, ref } from 'vue'

/**
 * Composer prefill handed to the Ask home. Phase 2 only fills it from the
 * knowledge preview pane ("Ask about this document"); Phase 3's composer
 * reads it to scope the question to a single document.
 */
export const useAskContextStore = defineStore('ask-context', () => {
  const documentId = ref<string | null>(null)
  const documentTitle = ref<string | null>(null)

  const hasDocumentScope = computed(() => Boolean(documentId.value))

  function askAboutDocument(id: string, title: string) {
    documentId.value = id
    documentTitle.value = title
  }

  function clearDocumentScope() {
    documentId.value = null
    documentTitle.value = null
  }

  return {
    documentId,
    documentTitle,
    hasDocumentScope,
    askAboutDocument,
    clearDocumentScope,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useAskContextStore, import.meta.hot))
}
