<template>
  <q-btn
    flat
    dense
    round
    :icon="icon"
    :color="color"
    :loading="isLoading"
    :disable="isLoading"
    aria-label="后端服务状态"
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
  if (isLoading.value) return '后端服务：检查中'
  if (isError.value) return '后端服务：不可用'
  return `后端服务：${data.value?.version ?? '正常'}`
})
</script>
