<template>
  <q-item
    min-h="40px"
    py-1
  >
    <q-item-section
      v-if="avatar"
      avatar
      min-w-0
      pr-3
      ml--1
    >
      <a-avatar
        :avatar
        :size="avatarSize ?? '27px'"
      />
    </q-item-section>
    <q-item-section>
      <q-item-label>
        {{ label }}
      </q-item-label>
      <q-item-label
        v-if="caption"
        caption
      >
        {{ caption }}
      </q-item-label>
    </q-item-section>
    <slot />
  </q-item>
</template>

<script setup lang="ts">
import type { Avatar } from 'src/utils/validators'
import AAvatar from './AAvatar.vue'

defineProps<{
  label: string
  avatar?: Avatar | null
  caption?: string | null
  avatarSize?: string
}>()
</script>
