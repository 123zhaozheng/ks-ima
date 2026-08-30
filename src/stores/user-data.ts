import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { localReactive } from 'src/composables/local-reactive'

const StorageKey = 'user-data'

type UserState = {
  lastWorkspaceId: string | null
  data: Record<string, any>
  perfs: Record<string, any>
  workspacePerfs: Record<string, Record<string, any>>
}

// User-level UI state lives in the browser. The Python API is authoritative
// for identity/membership; preferences and tips are local-only state.
export const useUserDataStore = defineStore('user-data', () => {
  const state = localReactive<UserState>(StorageKey, {
    lastWorkspaceId: null,
    data: {},
    perfs: {},
    workspacePerfs: {},
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

  function updateWorkspacePerfs(workspaceId: string, updates?: Record<string, any>, deletes?: string[]) {
    const target = { ...(state.workspacePerfs[workspaceId] ?? {}) }
    Object.assign(target, updates)
    deletes?.forEach(key => {
      delete target[key]
    })
    state.workspacePerfs[workspaceId] = target
  }

  function setLastWorkspaceId(workspaceId: string) {
    state.lastWorkspaceId = workspaceId
  }

  return {
    lastWorkspaceId: computed(() => state.lastWorkspaceId ?? undefined),
    data: computed(() => state.data),
    perfs: computed(() => state.perfs),
    workspacePerfs: computed(() => state.workspacePerfs),
    status: computed(() => 'success' as const),
    updateData,
    updatePerfs,
    updateWorkspacePerfs,
    setLastWorkspaceId,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useUserDataStore, import.meta.hot))
}
