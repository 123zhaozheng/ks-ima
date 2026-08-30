import { defineStore, acceptHMRUpdate } from 'pinia'
import { usePerfsState } from 'src/composables/perfs-state'
import { computed, watchEffect } from 'vue'
import { localReactive } from 'src/composables/local-reactive'
import type { ShortcutKey, Writable } from 'src/utils/types'
import { Dark } from 'quasar'
import { useUserDataStore } from './user-data'
import { useWorkspaceStore } from './workspace'
import { DEFAULT_HUE } from 'src/utils/config'

const StorageKey = 'perfs'

export const DefaultPerfs = {
  darkMode: 'auto' as boolean | 'auto',
  themeHue: DEFAULT_HUE,
  mdPreviewTheme: 'vuepress',
  mdCodeTheme: 'atom',
  mdNoMermaid: false,
  mdAutoFoldThreshold: null as number | null,
  showMessageWarnings: false,
  expandReasoningContent: true,
  codePasteOptimize: false,
  sendMessageKey: { key: 'Enter', withCtrl: true } as ShortcutKey,
  regenerateCurrKey: { key: 'KeyR', withCtrl: true } as ShortcutKey,
  editCurrKey: { key: 'KeyE', withCtrl: true } as ShortcutKey,
  scrollUpKey: { key: 'ArrowUp', withCtrl: true } as ShortcutKey,
  scrollDownKey: { key: 'ArrowDown', withCtrl: true } as ShortcutKey,
  scrollTopKey: { key: 'ArrowUp', withShift: true } as ShortcutKey,
  scrollBottomKey: { key: 'ArrowDown', withShift: true } as ShortcutKey,
  focusInputKey: null as ShortcutKey,
  streamingLockBottom: true,
  messageSelectionMenu: true,
  autoGenChatTitle: true,
  chatScrollBtns: true,
}

export type Perfs = typeof DefaultPerfs

export const usePerfsStore = defineStore('perfsStore', () => {
  const userDataStore = useUserDataStore()
  const workspaceStore = useWorkspaceStore()
  const userPerfs = computed(() => userDataStore.perfs ?? {})
  const workspacePerfs = computed(() =>
    workspaceStore.id ? userDataStore.workspacePerfs[workspaceStore.id] ?? {} : {},
  )
  const localPerfs = localReactive<Partial<Writable<Perfs>>>(StorageKey, {})
  const { perfs } = usePerfsState(computed(() => [userPerfs.value, workspacePerfs.value, localPerfs]), DefaultPerfs)

  watchEffect(() => {
    Dark.set(perfs.value.darkMode)
  })

  function update({ updates, deletes, scope }: {
    updates?: Partial<Perfs>
    deletes?: (keyof Perfs)[]
    scope: 'user' | 'workspace' | 'local'
  }) {
    if (scope === 'user') {
      userDataStore.updatePerfs(updates, deletes)
    } else if (scope === 'workspace') {
      if (!workspaceStore.id) return
      userDataStore.updateWorkspacePerfs(workspaceStore.id, updates, deletes)
    } else {
      Object.assign(localPerfs, updates)
      deletes?.forEach(key => {
        delete localPerfs[key]
      })
    }
  }
  return {
    userPerfs,
    workspacePerfs,
    localPerfs,
    perfs,
    update,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(usePerfsStore, import.meta.hot))
}
