<template>
  <div class="tk-section-header">
    <q-icon
      v-if="icon"
      :name="icon"
      size="18px"
      class="tk-section-header-icon"
    />
    <div class="tk-section-header-text">
      <div class="tk-section-header-title">
        {{ title }}
      </div>
      <div
        v-if="description"
        class="tk-section-header-desc"
      >
        {{ description }}
      </div>
    </div>
    <div
      v-if="$slots.actions"
      class="tk-section-header-actions"
    >
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  /** Material Symbol 名称（18px，accent 色），可省略 */
  icon?: string
  title: string
  description?: string
}>()
</script>

<style scoped>
.tk-section-header {
  display: flex;
  align-items: flex-start;
  gap: var(--tk-space-2);
}

.tk-section-header-icon {
  flex: none;
  margin-top: 1px;
  color: var(--tk-accent);
}

.tk-section-header-text {
  flex: 1;
  min-width: 0;
}

.tk-section-header-title {
  font-size: var(--tk-font-size-md);
  font-weight: var(--tk-weight-semibold);
  line-height: var(--tk-lh-tight);
  color: var(--tk-text);
}

.tk-section-header-desc {
  margin-top: 2px;
  font-size: 13px;
  line-height: var(--tk-lh-body);
  color: var(--tk-text-secondary);
}

.tk-section-header-actions {
  display: flex;
  flex: none;
  align-items: center;
  gap: var(--tk-space-1);
}
</style>
