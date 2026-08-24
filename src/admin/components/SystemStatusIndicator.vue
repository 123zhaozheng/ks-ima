<template>
  <q-btn
    flat
    dense
    round
    :icon="icon"
    :color="color"
    :loading="isLoading"
    :disable="isLoading"
    aria-label="Python API status"
  >
    <q-tooltip>{{ tooltip }}</q-tooltip>
  </q-btn>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSystemInfo } from 'src/composables/use-system-info'

const { data, isLoading, isError } = useSystemInfo()
const icon = computed(() => isLoading.value ? 'sym_o_sync' : isError.value ? 'sym_o_cloud_off' : 'sym_o_check_circle')
const color = computed(() => isLoading.value ? 'on-sur-var' : isError.value ? 'negative' : 'positive')
const tooltip = computed(() => {
  if (isLoading.value) return 'Python API: checking'
  if (isError.value) return 'Python API: unavailable'
  return `Python API: ${data.value?.version ?? 'ready'}`
})
</script>
