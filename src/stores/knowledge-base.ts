import { defineStore, acceptHMRUpdate } from 'pinia'
import { useQuery } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { identityClient, session } from 'src/utils/identity-client'
import { useUserDataStore } from './user-data'
import { queryClient } from 'src/boot/vue-query'

export const useKbStore = defineStore('knowledge-base', () => {
  const userDataStore = useUserDataStore()
  const router = useRouter()
  const id = ref<string | null>(null)
  const userId = computed(() => session.value.data?.user.id ?? null)

  const { data: kbs, status: kbsStatus } = useQuery({
    queryKey: ['knowledge-bases', 'member'],
    queryFn: async () => {
      const result = await identityClient.listKnowledgeBases()
      if (result.error) throw new Error(result.error.message)
      return result.data!
    },
    enabled: computed(() => Boolean(userId.value)),
  })

  watch(
    [userId, () => userDataStore.lastKbId, kbs],
    ([uid, last, list]) => {
      if (!uid) {
        id.value = null
        return
      }
      const ids = (list ?? []).map(kb => kb.id)
      if (id.value && ids.includes(id.value)) return
      const next = (last && ids.includes(last) ? last : null) ?? ids[0] ?? null
      if (next) id.value = next
    },
    { immediate: true },
  )

  const { data: kb } = useQuery({
    queryKey: computed(() => ['knowledge-bases', 'member', id.value] as const),
    queryFn: async () => {
      const result = await identityClient.getKnowledgeBase(id.value!)
      if (result.error) throw new Error(result.error.message)
      return result.data!
    },
    enabled: computed(() => Boolean(id.value)),
  })

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
    router.push('/')
  }

  // My membership in the current knowledge base: role drives readonly hints
  // and owner-only entry points.
  const member = computed(() => {
    if (!kb.value || !userId.value) return undefined
    return {
      userId: userId.value,
      role: kb.value.role,
    }
  })

  const myRole = computed(() => member.value?.role ?? null)
  const isOwner = computed(() => kb.value?.owned ?? false)

  return {
    id,
    member,
    myRole,
    isOwner,
    kbs,
    kbsStatus,
    kb,
    switchKb,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useKbStore, import.meta.hot))
}
