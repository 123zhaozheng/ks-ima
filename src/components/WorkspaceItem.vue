<template>
  <q-item>
    <q-item-section
      avatar
      min-w-0
      pr-3
      ml--1
    >
      <a-avatar :avatar="workspaceAvatar(workspace)" />
    </q-item-section>
    <q-item-section>
      <q-item-label>
        {{ workspace.name }}
      </q-item-label>
    </q-item-section>
    <slot />
  </q-item>
</template>

<script setup lang="ts">
import type { Row } from '@rocicorp/zero'
import { workspaceAvatar } from 'src/utils/defaults'
import AAvatar from './AAvatar.vue'

defineProps<{
  workspace: Row['workspace']
}>()
</script>
