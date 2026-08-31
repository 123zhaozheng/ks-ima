<template>
  <img
    v-if="vendor?.logo"
    :src="vendor.logo"
    :alt="vendor.name"
    class="model-avatar"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
  <div
    v-else-if="vendor"
    class="model-avatar model-avatar--letter"
    :style="{ width: `${size}px`, height: `${size}px`, backgroundColor: vendor.color, fontSize: `${Math.round(size * 0.5)}px` }"
  >
    {{ vendor.name.charAt(0).toUpperCase() }}
  </div>
  <div
    v-else
    class="model-avatar model-avatar--unknown"
    :style="{ width: `${size}px`, height: `${size}px` }"
  >
    <q-icon
      name="sym_smart_toy"
      :size="`${Math.round(size * 0.66)}px`"
      color="grey-6"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { detectVendor, getVendor } from 'src/admin/model-catalog'
import type { Vendor } from 'src/admin/model-catalog'

const props = withDefaults(defineProps<{
  /** 模型 ID 或服务商地址，用于识别厂商 */
  model?: string | null
  /** 直接指定厂商 ID（优先于 model） */
  vendorId?: string | null
  /** 两档尺寸：24（表格行）/ 32（卡片） */
  size?: 24 | 32
}>(), {
  model: null,
  vendorId: null,
  size: 24,
})

const vendor = computed<Vendor | null>(() => {
  const id = props.vendorId ? props.vendorId : detectVendor(props.model)
  return getVendor(id)
})
</script>

<style scoped>
.model-avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: 50%;
  object-fit: contain;
  background-color: #fff;
  border: 1px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.model-avatar--letter {
  color: #fff;
  font-weight: 600;
  border: none;
  user-select: none;
}

.model-avatar--unknown {
  background-color: #f2f2f7;
  border: none;
}
</style>
