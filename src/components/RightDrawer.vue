<template>
  <q-drawer
    v-if="showDrawer"
    show-if-above
    bg-sur-c-low
    :breakpoint="uiStateStore.rightDrawerBreakpoint"
    side="right"
    v-model="uiStateStore.rightDrawerOpen"
  >
    <div
      flex="~ col"
      h-full
    >
      <template v-if="viewDirId">
        <right-entity-list
          mode="page"
          :root-id="(route.params.id as string)"
          v-model="viewDirId"
          max-h="40%"
          w-full
          mt-2
        />
        <q-separator spaced />
      </template>
      <new-entity-btns p-2 />
      <right-entity-list
        v-if="rightDirStore.dirId"
        flex-1
        min-h-0
        mode="right"
        v-model="rightDirStore.dirId"
        w-full
        py-2
      />
    </div>
  </q-drawer>
</template>

<script setup lang="ts">
import { useUiStateStore } from 'src/stores/ui-state'
import { useRightDirStore } from 'src/stores/right-dir'
import RightEntityList from './RightEntityList.vue'
import NewEntityBtns from './NewEntityBtns.vue'
import { useRoute } from 'vue-router'
import { computed, ref, watchEffect } from 'vue'

const rightDirStore = useRightDirStore()
const uiStateStore = useUiStateStore()

const route = useRoute()
const showDrawer = computed(() => {
  const type = route.params.type
  return type === 'assistant'
})
const viewDirId = ref()
watchEffect(() => {
  viewDirId.value = route.params.id
})
</script>
