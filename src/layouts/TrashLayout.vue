<template>
  <q-header class="tk-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ t('Trash') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      class="trash-page"
      :style-fn="pageFhStyle"
    >
      <div class="tk-card trash-card">
        <trash-list
          v-if="workspaceStore.id"
          :workspace-id="workspaceStore.id"
          h-full
        />
      </div>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { useUiStateStore } from 'src/stores/ui-state'
import TrashList from 'src/components/KnowledgeTrashList.vue'
import { useWorkspaceStore } from 'src/stores/workspace'
import { pageFhStyle } from 'src/utils/functions'
import { useRequireLogin } from 'src/composables/require-login'

useRequireLogin()

const uiStateStore = useUiStateStore()
const workspaceStore = useWorkspaceStore()
</script>

<style scoped>
.trash-page {
  display: flex;
  flex-direction: column;
  max-width: 860px;
  margin: 0 auto;
  width: 100%;
  padding: var(--tk-space-4);
  box-sizing: border-box;
}

.trash-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
