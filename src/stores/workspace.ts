import { defineStore, acceptHMRUpdate } from 'pinia'
import { mutate, user, z } from '../utils/zero-session'
import { client } from '../utils/hc'
import { useQuery } from 'src/composables/zero/query'
import type { FullWorkspace } from 'app/src-shared/queries'
import { queries } from 'app/src-shared/queries'
import { mutators } from 'app/src-shared/mutators'
import type { MemberData } from 'app/src-shared/utils/validators'
import { computed, ref, watch, watchEffect } from 'vue'
import { useRouter } from 'vue-router'
import { useUserDataStore } from './user-data'

export const useWorkspaceStore = defineStore('workspace', () => {
  const userDataStore = useUserDataStore()
  const router = useRouter()
  const id = ref<string | null>(null)
  const { data: workspaces, status: workspacesStatus } = useQuery(() => user.id ? queries.workspaces() : null)

  watch(
    [() => user.id, () => userDataStore.lastWorkspaceId, workspaces],
    async ([uid, last, list]) => {
      if (!uid) {
        id.value = null
        return
      }
      const ids = (list ?? []).map(w => w.id)
      if (!ids.length) {
        try {
          const res = await client.api.connectors.workspaces.$get()
          if (res.ok) {
            const rest = await res.json() as Array<{ id: string }>
            if (Array.isArray(rest)) ids.push(...rest.map(w => w.id))
          }
        } catch {
          return
        }
      }
      if (id.value && ids.includes(id.value)) return
      const next = (last && ids.includes(last) ? last : null) ?? ids[0] ?? null
      if (next) id.value = next
    },
    { immediate: true },
  )

  const { data: workspace, status } = useQuery(() =>
    id.value ? queries.fullWorkspace(id.value) : null,
  )

  z.preload(queries.globalSettings())
  z.preload(queries.publicModels())
  watchEffect(() => {
    if (!id.value) return
    z.preload(queries.models(id.value))
    z.preload(queries.entity({ id: id.value, children: { depth: 3 } }))
    z.preload(queries.entityAccesses(id.value))
    z.preload(queries.recentChats(id.value))
    z.preload(queries.recentItems(id.value))
    z.preload(queries.recentProviders(id.value))
    z.preload(queries.assistants({
      workspaceId: id.value,
      limit: 10,
    }))
  })

  async function updateData(updates: Partial<MemberData>) {
    if (!id.value) return
    await mutate(mutators.updateMemberData({ workspaceId: id.value, ...updates })).client
  }

  function switchWorkspace(to: string) {
    if (id.value !== to) {
      id.value = to
      mutate(mutators.updateLastWorkspaceId(to))
    }
    if (router.currentRoute.value.path !== `/folder/${to}`) router.push(`/folder/${to}`)
  }
  const member = ref<FullWorkspace['member']>()
  watch(workspace, ws => {
    member.value = ws?.member
  }, { immediate: true })
  return {
    id,
    member,
    members: computed(() => workspace.value?.members),
    workspaces,
    workspacesStatus,
    workspace,
    status,
    updateData,
    switchWorkspace,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useWorkspaceStore, import.meta.hot))
}
