<template>
  <q-avatar
    v-if="avatar.type === 'text'"
    :style
  >
    {{ avatar.text }}
  </q-avatar>
  <q-avatar
    v-else-if="avatar.type === 'icon'"
    :icon="avatar.icon"
    :style
  />
  <q-avatar
    v-else-if="avatar.type === 'url'"
    :style
  >
    <img :src="avatar.url">
  </q-avatar>
  <q-avatar
    v-else-if="avatar.type === 'svg'"
    :icon="`svguse:/svg/${avatar.name}.svg#icon`"
    :style
  />
</template>

<script setup lang="ts">
import { useQuasar } from 'quasar'
import { hctToHex } from 'src/utils/functions'
import type { Avatar } from 'src/utils/validators'
import { computed } from 'vue'

const props = defineProps<{
  avatar: Avatar
}>()

const $q = useQuasar()
const style = computed(() => {
  if (props.avatar.hue == null) return {}
  const { hue } = props.avatar
  return $q.dark.isActive
    ? { color: hctToHex(hue, 40, 90), backgroundColor: hctToHex(hue, 40, 30) }
    : { color: hctToHex(hue, 40, 10), backgroundColor: hctToHex(hue, 40, 90) }
})
</script>
