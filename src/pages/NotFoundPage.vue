<template>
  <q-page-container>
    <q-page
      flex="~ col"
      justify-center
      pos-relative
    >
      <q-btn
        flat
        round
        dense
        icon="sym_o_menu"
        pos-absolute
        top-2
        left-3
        @click="uiStateStore.toggleMainDrawer"
      />
      <hint-card
        img-url="/emotions/nachoneko/19.webp"
        message="这里什么都没有..."
      />
      <div h="100px" />
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import HintCard from 'src/components/HintCard.vue'
import { useUiStateStore } from 'src/stores/ui-state'

const uiStateStore = useUiStateStore()

</script>
