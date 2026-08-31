import { defineStore, acceptHMRUpdate } from 'pinia'
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { identityClient, session } from 'src/utils/identity-client'
import { useUserDataStore } from './user-data'
import { queryClient } from 'src/boot/vue-query'

export type ManageSection = 'overview' | 'share'

export const useKbStore = defineStore('knowledge-base', () => {
  const userDataStore = useUserDataStore()
  const id = ref<string | null>(null)
  const userId = computed(() => session.value.data?.user.id ?? null)

  const { data: kbs, status: kbsStatus, isFetching: listFetching } = useQuery({
    queryKey: ['knowledge-bases', 'member'],
    queryFn: async () => {
      const result = await identityClient.listKnowledgeBases()
      if (result.error) throw new Error(result.error.message)
      return result.data!
    },
    enabled: computed(() => Boolean(userId.value)),
  })

  // The current knowledge base is looked up synchronously from the membership
  // list, so the switcher name updates immediately without waiting on any
  // detail request.
  const current = computed(() => (kbs.value ?? []).find(kb => kb.id === id.value) ?? null)

  // Auto-initialize the selection only. Never overwrite an id the user just
  // picked: while the membership list is being invalidated/refetched it can be
  // stale, and falling back to the first entry made the switcher flicker.
  watch(
    [userId, () => userDataStore.lastKbId, kbs],
    ([uid, last, list]) => {
      if (!uid) {
        id.value = null
        return
      }
      const ids = (list ?? []).map(kb => kb.id)
      if (id.value == null || !ids.includes(id.value)) {
        if (id.value != null && listFetching.value) return
        const next = (last && ids.includes(last) ? last : null) ?? ids[0] ?? null
        id.value = next
      }
    },
    { immediate: true },
  )

  watch(id, (next, previous) => {
    if (!previous || previous === next) return
    queryClient.cancelQueries({ queryKey: ['grounded', 'kb', previous] })
    queryClient.removeQueries({ queryKey: ['grounded', 'kb', previous] })
  })

  function switchKb(to: string) {
    if (id.value !== to) {
      const previous = id.value
      id.value = to
      if (previous) {
        queryClient.cancelQueries({ queryKey: ['knowledge', 'kb', previous] })
        queryClient.removeQueries({ queryKey: ['knowledge', 'kb', previous] })
        queryClient.cancelQueries({ queryKey: ['grounded', 'kb', previous] })
        queryClient.removeQueries({ queryKey: ['grounded', 'kb', previous] })
      }
      userDataStore.setLastKbId(to)
    }
  }

  // Manage dialog state lives here so the dialog can be opened from any page
  // (toolbar share button, switcher menu entry).
  const manageOpen = ref(false)
  const manageSection = ref<ManageSection>('overview')
  function openManage(section: ManageSection = 'overview') {
    manageSection.value = section
    manageOpen.value = true
  }
  // The dialog is bound to the current knowledge base; close it when the
  // selection disappears so a stale open flag does not resurface later.
  watch(current, next => {
    if (!next) manageOpen.value = false
  })

  // My membership in the current knowledge base: role drives readonly hints
  // and owner-only entry points. The detail API does not return `owned`, so
  // ownership comes from the membership role instead.
  const member = computed(() => {
    if (!current.value || !userId.value) return undefined
    return {
      userId: userId.value,
      role: current.value.role,
    }
  })

  const myRole = computed(() => member.value?.role ?? null)
  const isOwner = computed(() => myRole.value === 'owner')

  return {
    id,
    current,
    member,
    myRole,
    isOwner,
    kbs,
    kbsStatus,
    manageOpen,
    manageSection,
    openManage,
    switchKb,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useKbStore, import.meta.hot))
}
