import { defineStore, acceptHMRUpdate } from 'pinia'
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { identityClient, session } from 'src/utils/identity-client'
import { useUserDataStore } from './user-data'
import { queryClient } from 'src/boot/vue-query'

export const useWorkspaceStore = defineStore('workspace', () => {
  const userDataStore = useUserDataStore()
  const router = useRouter()
  const id = ref<string | null>(null)
  const userId = computed(() => session.value.data?.user.id ?? null)

  const { data: workspaces, status: workspacesStatus } = useQuery({
    queryKey: ['workspaces', 'member'],
    queryFn: async () => {
      const result = await identityClient.listMemberWorkspaces()
      if (result.error) throw new Error(result.error.message)
      return result.data!.items
    },
    enabled: computed(() => Boolean(userId.value)),
  })

  watch(
    [userId, () => userDataStore.lastWorkspaceId, workspaces],
    ([uid, last, list]) => {
      if (!uid) {
        id.value = null
        return
      }
      const ids = (list ?? []).map(w => w.id)
      if (id.value && ids.includes(id.value)) return
      const next = (last && ids.includes(last) ? last : null) ?? ids[0] ?? null
      if (next) id.value = next
    },
    { immediate: true },
  )

  const { data: workspace } = useQuery({
    queryKey: computed(() => ['workspaces', 'member', id.value] as const),
    queryFn: async () => {
      const result = await identityClient.getMemberWorkspace(id.value!)
      if (result.error) throw new Error(result.error.message)
      return result.data!
    },
    enabled: computed(() => Boolean(id.value)),
  })

  watch(id, (next, previous) => {
    if (!previous || previous === next) return
    queryClient.cancelQueries({ queryKey: ['grounded', 'workspace', previous] })
    queryClient.removeQueries({ queryKey: ['grounded', 'workspace', previous] })
  })

  function switchWorkspace(to: string) {
    if (id.value !== to) {
      const previous = id.value
      id.value = to
      if (previous) {
        queryClient.cancelQueries({ queryKey: ['knowledge', 'workspace', previous] })
        queryClient.removeQueries({ queryKey: ['knowledge', 'workspace', previous] })
        queryClient.cancelQueries({ queryKey: ['grounded', 'workspace', previous] })
        queryClient.removeQueries({ queryKey: ['grounded', 'workspace', previous] })
      }
      userDataStore.setLastWorkspaceId(to)
    }
    router.push('/')
  }

  const member = computed(() => {
    if (!workspace.value || !userId.value) return undefined
    return {
      userId: userId.value,
      role: workspace.value.role,
    }
  })

  return {
    id,
    member,
    workspaces,
    workspacesStatus,
    workspace,
    switchWorkspace,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useWorkspaceStore, import.meta.hot))
}
