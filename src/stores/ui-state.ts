import { acceptHMRUpdate, defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStateStore = defineStore('ui-state', () => {
  const mainDrawerWidth = 76
  const mainDrawerBreakpoint = 1200
  const mainDrawerOpen = ref(false)
  function toggleMainDrawer() {
    mainDrawerOpen.value = !mainDrawerOpen.value
  }

  return {
    mainDrawerWidth,
    mainDrawerBreakpoint,
    mainDrawerOpen,
    toggleMainDrawer,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useUiStateStore, import.meta.hot))
}
