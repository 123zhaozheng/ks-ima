<template>
  <div class="tk-pane-empty">
    <q-icon
      :name="icon"
      size="32px"
      class="tk-pane-empty-icon"
    />
    <div class="tk-pane-empty-title">
      {{ title }}
    </div>
    <div
      v-if="description"
      class="tk-pane-empty-desc"
    >
      {{ description }}
    </div>
    <div
      v-if="$slots.actions"
      class="tk-pane-empty-actions"
    >
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** Material Symbol 名称（32px，中性灰） */
  icon: string
  title: string
  description?: string
}>()
</script>

<style scoped>
/* 局部空态/错态：pane 内垂直居中，不用整页 spinner 或 warning 图标。 */
.tk-pane-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--tk-space-8) var(--tk-space-6);
}

.tk-pane-empty-icon {
  color: var(--tk-text-tertiary);
  margin-bottom: var(--tk-space-3);
}

.tk-pane-empty-title {
  font-size: var(--tk-font-size-sm);
  font-weight: var(--tk-weight-medium);
  line-height: var(--tk-lh-tight);
  color: var(--tk-text);
}

.tk-pane-empty-desc {
  margin-top: var(--tk-space-2);
  max-width: 320px;
  font-size: 13px;
  line-height: var(--tk-lh-body);
  color: var(--tk-text-secondary);
}

.tk-pane-empty-actions {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-4);
}
</style>
