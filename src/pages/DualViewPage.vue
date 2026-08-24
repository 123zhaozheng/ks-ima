<template>
  <q-page-container>
    <q-page
      flex
      :style-fn="pageFhStyle"
    >
      <entity-view
        :key="`${$route.params.type}-${$route.params.id}`"
        :type="($route.params.type as EntityType)"
        :id="($route.params.id as string)"
        :position="isKnowledge || !rightEntity ? 'full' : 'left'"
      />
      <entity-view
        v-if="rightEntity && !isKnowledge && $q.screen.gt.xs"
        :id="rightEntity.id"
        :type="rightEntity.type"
        position="right"
      />
    </q-page>
  </q-page-container>
  <q-drawer
    v-if="$q.screen.lt.sm && rightEntity && !isKnowledge"
    :model-value="!!rightEntity"
    @update:model-value="!$event && $router.replace({ query: {} })"
    bg-sur-c-low
    :breakpoint="Infinity"
    side="right"
    :width="$q.screen.width * 0.85"
  >
    <entity-view
      v-if="rightEntity"
      :id="rightEntity.id"
      :type="rightEntity.type"
      position="right"
    />
  </q-drawer>
</template>

<script setup lang="ts">
import type { EntityType } from 'app/src-shared/utils/validators'
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { pageFhStyle } from 'src/utils/functions'
import EntityView from 'src/views/EntityView.vue'
import { useRightEntity } from 'src/composables/right-entity'

const route = useRoute()
const rightEntity = useRightEntity()
const isKnowledge = computed(() => {
  const type = route.params.type
  return type === 'folder' || type === 'item' || type === 'chat'
})
</script>
