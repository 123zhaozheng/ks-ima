import { acceptHMRUpdate, defineStore } from 'pinia'
import { useQuasar } from 'quasar'
import { computed, ref } from 'vue'

export const useUiStateStore = defineStore('ui-state', () => {
  const mainDrawerWidth = 275
  const mainDrawerBreakpoint = 1200
  const mainDrawerOpen = ref(false)
  function toggleMainDrawer() {
    mainDrawerOpen.value = !mainDrawerOpen.value
  }
  const $q = useQuasar()
  const mainDrawerAbove = computed(() => $q.screen.width > mainDrawerBreakpoint)

  return {
    mainDrawerWidth,
    mainDrawerBreakpoint,
    mainDrawerOpen,
    mainDrawerAbove,
    toggleMainDrawer,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useUiStateStore, import.meta.hot))
}
