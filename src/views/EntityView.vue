<template>
  <chat-view-wrapper
    v-if="type === 'chat'"
    :id
  />
  <item-view-wrapper
    v-else-if="type === 'item'"
    :id
  />
  <dir-view
    v-else-if="type === 'folder'"
    :id
  />
</template>

<script setup lang="ts">
import type { Row } from '@rocicorp/zero'
import { provide, toRef } from 'vue'
import ChatViewWrapper from './ChatViewWrapper.vue'
import DirView from './DirView.vue'
import ItemViewWrapper from './ItemViewWrapper.vue'

const props = defineProps<{
  id: string
  type: Row['entity']['type']
  position: 'full' | 'left' | 'right'
}>()
provide('position', toRef(props, 'position'))
</script>
