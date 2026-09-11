<template>
  <span
    class="tk-status-badge"
    :class="`tk-status-badge--${tone}`"
  >
    <span
      v-if="dot"
      class="tk-status-badge-dot"
    />
    <q-icon
      v-else-if="icon"
      :name="icon"
      size="14px"
    />
    <span class="tk-status-badge-label">{{ label }}</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{
  /** 色调：success=绿 / muted=中性灰 / warning=琥珀 / danger=红 */
  tone: 'success' | 'muted' | 'warning' | 'danger'
  label: string
  /** 小圆点（与 icon 二选一；都不传则只显示 label） */
  dot?: boolean
  /** 14px Material Symbol 名称 */
  icon?: string
}>()
</script>

<style scoped>
.tk-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: var(--tk-weight-medium);
  line-height: 1;
  white-space: nowrap;
}

.tk-status-badge-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--tk-radius-pill);
  background-color: currentColor;
  flex: none;
}

.tk-status-badge--success {
  color: var(--tk-success);
}

.tk-status-badge--muted {
  color: var(--tk-text-tertiary);
}

.tk-status-badge--warning {
  color: var(--tk-warning);
}

.tk-status-badge--danger {
  color: var(--tk-danger);
}
</style>
