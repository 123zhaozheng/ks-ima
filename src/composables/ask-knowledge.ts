import { useWorkspaceStore } from 'src/stores/workspace'
import { Notify } from 'quasar'
import { t } from 'src/utils/i18n'
import { useRouter } from 'vue-router'

// Ask runs on the migrated grounded-ask page backed by the Python API.
export function useAskKnowledge() {
  const workspaceStore = useWorkspaceStore()
  const router = useRouter()

  return function askKnowledge() {
    if (!workspaceStore.id) {
      Notify.create({ message: t('No workspace selected'), color: 'negative' })
      return
    }
    router.push('/workspace/ask')
  }
}
