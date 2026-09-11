<template>
  <q-header class="tk-topbar">
    <div class="tk-topbar-bar">
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        aria-label="切换侧栏"
        data-testid="app-menu-toggle"
        @click="uiStateStore.toggleMainDrawer"
      />
      <div class="tk-topbar-title">
        <span
          v-if="!topbarTitleOverride"
          class="tk-topbar-title-text"
        >{{ fallbackTitle }}</span>
        <!-- Pages with a live title (the open conversation's subject) teleport
             their own title node here; the override ref hides the default. -->
        <div
          id="topbar-title"
          class="tk-topbar-title-slot"
        />
      </div>
      <!-- Pages inject their page-level actions (badges, share, ...) through
           <teleport defer to="#topbar-actions">. -->
      <div
        id="topbar-actions"
        class="tk-topbar-actions"
      />
    </div>
  </q-header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { topbarTitleOverride } from 'src/composables/topbar'
import { useKbStore } from 'src/stores/knowledge-base'
import { useUiStateStore } from 'src/stores/ui-state'

const route = useRoute()
const kbStore = useKbStore()
const uiStateStore = useUiStateStore()

// The KB workspace names its bar after the selected knowledge base; every
// other page falls back to its route-meta title.
const fallbackTitle = computed(() => {
  if (route.path === '/kb') return kbStore.current?.name ?? '知识库'
  const title = route.meta.title
  return typeof title === 'string' ? title : ''
})
</script>

<style>
/*
 * Shell top bar styles are global (not scoped) because pages teleport title
 * and action nodes into the bar; keep every selector flat (Chrome 109).
 */
.tk-topbar {
  background-color: var(--tk-surface-white);
  color: var(--tk-text);
}

.tk-topbar-bar {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  height: 56px;
  padding: 0 var(--tk-space-3);
}

.tk-topbar-title {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
}

.tk-topbar-title-slot {
  min-width: 0;
  display: flex;
  align-items: center;
}

.tk-topbar-title-text {
  min-width: 0;
  font-size: var(--tk-font-size-md);
  font-weight: var(--tk-weight-semibold);
  letter-spacing: var(--tk-tracking-display);
  color: var(--tk-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tk-topbar-actions {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  flex: none;
}
</style>
