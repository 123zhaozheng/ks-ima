<template>
  <entity-list
    v-model="dirId"
    @entity-click="onEntityClick"
    :list-options-override="{
      orderBy: ['id', mode === 'right' ? 'desc' : 'asc']
    }"
  />
</template>

<script setup lang="ts">
import type { FullEntity } from 'app/src-shared/queries'
import EntityList from './EntityList.vue'
import { entityRoute } from 'src/utils/functions'
import { useActiveEntitiesStore } from 'src/stores/active-entities'
import { useRouter } from 'vue-router'

defineProps<{
  mode: 'left' | 'right' | 'page'
}>()

const dirId = defineModel<string>({ required: true })

const activeEntitiesStore = useActiveEntitiesStore()

const router = useRouter()
function onEntityClick({ type, id }: FullEntity) {
  if (type === 'shortcut') {
    activeEntitiesStore.runShortcut(id)
  } else {
    const link = entityRoute(type, id)
    link && router.push(link)
  }
}
</script>
