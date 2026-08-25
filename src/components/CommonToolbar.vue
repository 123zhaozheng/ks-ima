<template>
  <q-toolbar bg-sur-c-low>
    <q-btn
      v-if="!store.mainDrawerAbove && position !== 'right'"
      flat
      dense
      round
      icon="sym_o_menu"
      @click="store.toggleMainDrawer"
      text-on-sur-var
    />
    <slot />
    <template v-if="position === 'right'">
      <q-btn
        flat
        dense
        round
        icon="sym_o_open_in_new"
        :to="entityRoute(rightEntity!.type, rightEntity!.id)"
        text-on-sur-var
      />
      <q-btn
        v-if="$q.screen.gt.xs"
        flat
        dense
        round
        icon="sym_o_close"
        @click="$router.replace({ query: {} })"
        text-on-sur-var
      />
    </template>
    <q-btn
      v-else-if="!store.rightDrawerAbove && showRightDrawerBtn"
      flat
      dense
      round
      icon="sym_o_segment"
      @click="store.toggleRightDrawer"
      text-on-sur-var
    />
  </q-toolbar>
</template>

<script setup lang="ts">
import { useUiStateStore } from 'src/stores/ui-state'
import { computed, inject } from 'vue'
import { useRoute } from 'vue-router'
import type { LayoutPosition } from 'src/utils/types'
import { useRightEntity } from 'src/composables/right-entity'
import { entityRoute } from 'src/utils/functions'

const store = useUiStateStore()
const route = useRoute()
const showRightDrawerBtn = computed(() => {
  const type = route.params.type
  return type === 'assistant'
})

const position = inject<LayoutPosition>('position')!
const rightEntity = useRightEntity()
</script>
