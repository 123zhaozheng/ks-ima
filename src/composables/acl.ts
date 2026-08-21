import type { Row } from '@rocicorp/zero'
import { computed } from 'vue'
import { canAction, type AclAction } from 'app/src-shared/utils/acl'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useLocalEntitiesStore } from 'src/stores/local-entities'

export function useEntityAcl() {
  const workspaceStore = useWorkspaceStore()
  const local = useLocalEntitiesStore()

  const role = computed(() => workspaceStore.member?.role)
  const userId = computed(() => workspaceStore.member?.userId)

  function ancestorConfs(entity: Row['entity']) {
    return [entity, ...local.getAncestors(entity).toReversed()].map(e => e.conf)
  }

  function can(entity: Row['entity'] | undefined, action: AclAction) {
    if (!entity) return false
    return canAction(role.value, userId.value, ancestorConfs(entity), action)
  }

  function filterVisible<T extends Row['entity']>(entities: T[]) {
    return entities.filter(e => can(e, 'view'))
  }

  return { can, filterVisible }
}
