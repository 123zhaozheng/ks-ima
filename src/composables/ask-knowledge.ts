import { createEntity } from 'src/utils/create-entity'
import { chatParentId } from 'src/utils/knowledge'
import { useActiveEntitiesStore } from 'src/stores/active-entities'
import { useLocalEntitiesStore } from 'src/stores/local-entities'
import { useWorkspaceStore } from 'src/stores/workspace'
import { Notify } from 'quasar'
import { connectionState } from 'src/utils/zero-session'
import { t } from 'src/utils/i18n'
import { rejectAfter } from 'src/utils/reject-after'

let opening = false

export function useAskKnowledge() {
  const activeEntitiesStore = useActiveEntitiesStore()
  const localEntitiesStore = useLocalEntitiesStore()
  const workspaceStore = useWorkspaceStore()

  return async function askKnowledge() {
    if (opening) return
    if (!workspaceStore.id) {
      Notify.create({ message: t('No workspace selected'), color: 'negative' })
      return
    }
    const state = connectionState.value.name
    if (state === 'disconnected' || state === 'error') {
      Notify.create({ message: t('Knowledge service is unavailable. Try again after reconnecting.'), color: 'negative' })
      return
    }
    const parentId = chatParentId(
      activeEntitiesStore.shortcuts,
      localEntitiesStore.entities,
      workspaceStore.id,
    )
    opening = true
    const dismiss = Notify.create({
      message: t('Opening Ask…'),
      spinner: true,
      timeout: 0,
      group: false,
    })
    const controller = new AbortController()
    try {
      await Promise.race([
        createEntity(parentId, 'chat', controller.signal),
        rejectAfter(10_000, t('Opening Ask timed out. Please try again.')),
      ])
    } catch (err) {
      Notify.create({
        message: t('Could not open Ask: {0}', err instanceof Error ? err.message : String(err)),
        color: 'negative',
      })
    } finally {
      controller.abort()
      opening = false
      dismiss()
    }
  }
}
