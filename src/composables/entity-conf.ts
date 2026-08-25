import type { Ref } from 'vue'
import { computed, inject } from 'vue'
import { mutate } from 'src/utils/zero-session'
import { expandAncestors } from 'src/utils/functions'
import { usePerfsState } from './perfs-state'
import { mutators } from 'app/src-shared/mutators'
import type { LayoutPosition } from 'src/utils/types'
import { useEntityStore } from 'src/stores/entity'
import type { FullEntity } from 'app/src-shared/queries'
import { queries } from 'app/src-shared/queries'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useQuery } from './zero/query'

const DefaultConf = {
  chatAssistantId: null as string | null,
}

export type EntityConf = typeof DefaultConf

export function useEntityConf(entity: Ref<FullEntity | undefined>) {
  const ancestors = computed(() => entity.value ? expandAncestors(entity.value) : [])
  const sources = computed(() => ancestors.value.map(x => x.conf))
  const { state, perfs: conf } = usePerfsState(sources, DefaultConf, [null, undefined])

  async function update(key: keyof EntityConf, value: any) {
    await mutate(mutators.updateEntityConf({
      id: entity.value!.id,
      updates: { [key]: value },
    })).client
  }
  async function reset(key: keyof EntityConf) {
    await mutate(mutators.updateEntityConf({
      id: entity.value!.id,
      deletes: [key],
    })).client
  }
  return { entity, ancestors, state, conf, update, reset }
}

export function useThisEntityConf() {
  const position = inject<Ref<LayoutPosition>>('position')!
  const entityStore = useEntityStore()
  const entity = computed(() => position.value === 'right' ? entityStore.rightEntity : entityStore.entity)
  return useEntityConf(entity)
}

export function useRootEntityConf() {
  const workspaceStore = useWorkspaceStore()
  const { data: entity } = useQuery(() => workspaceStore.id ? queries.entity({ id: workspaceStore.id }) : null)
  return useEntityConf(entity)
}
