<template>
  <q-header
    bg-sur-c-low
    text-on-sur
  >
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ t('Trash') }}</q-toolbar-title>
      <q-space />
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page :style-fn="pageFhStyle">
      <trash-list
        v-if="workspaceStore.id"
        :workspace-id="workspaceStore.id"
        h-full
      />
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
