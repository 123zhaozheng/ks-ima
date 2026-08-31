import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { localReactive } from 'src/composables/local-reactive'

const StorageKey = 'user-data'

type UserState = {
  lastKbId: string | null
  data: Record<string, any>
  perfs: Record<string, any>
  kbPerfs: Record<string, Record<string, any>>
}

// User-level UI state lives in the browser. The Python API is authoritative
// for identity/membership; preferences and tips are local-only state.
export const useUserDataStore = defineStore('user-data', () => {
  const state = localReactive<UserState>(StorageKey, {
    lastKbId: null,
    data: {},
    perfs: {},
    kbPerfs: {},
  })

  function updateData(updates: Record<string, any>) {
    Object.assign(state.data, updates)
  }

  function updatePerfs(updates?: Record<string, any>, deletes?: string[]) {
    Object.assign(state.perfs, updates)
    deletes?.forEach(key => {
      delete state.perfs[key]
    })
  }

  function updateKbPerfs(kbId: string, updates?: Record<string, any>, deletes?: string[]) {
    const target = { ...(state.kbPerfs[kbId] ?? {}) }
    Object.assign(target, updates)
    deletes?.forEach(key => {
      delete target[key]
    })
    state.kbPerfs[kbId] = target
  }

  function setLastKbId(kbId: string) {
    state.lastKbId = kbId
  }

  return {
    lastKbId: computed(() => state.lastKbId ?? undefined),
    data: computed(() => state.data),
    perfs: computed(() => state.perfs),
    kbPerfs: computed(() => state.kbPerfs),
    status: computed(() => 'success' as const),
    updateData,
    updatePerfs,
    updateKbPerfs,
    setLastKbId,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useUserDataStore, import.meta.hot))
}
