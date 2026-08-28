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
      <q-toolbar-title>{{ workspace?.name || t('Workspace') }}</q-toolbar-title>
    </q-toolbar>
    <q-tabs
      v-if="workspaceStore.id"
      active-color="primary"
      align="left"
      no-caps
    >
      <q-route-tab
        :label="t('Overview')"
        to="/workspace"
      />
      <q-route-tab
        :label="t('Capabilities')"
        to="/workspace/models"
      />
      <q-route-tab
        :label="t('Agent access')"
        to="/workspace/connectors"
      />
      <q-route-tab
        :label="t('Tags')"
        to="/workspace/tags"
      />
      <q-route-tab
        :label="t('Ask')"
        to="/workspace/ask"
      />
    </q-tabs>
  </q-header>
  <router-view v-if="workspaceStore.id" />
</template>

<script setup lang="ts">
import { useWorkspaceStore } from 'src/stores/workspace'
import { toRef } from 'vue'
import { t } from 'src/utils/i18n'
import { useUiStateStore } from 'src/stores/ui-state'
import { useRequireLogin } from 'src/composables/require-login'

useRequireLogin()

const uiStateStore = useUiStateStore()

const workspaceStore = useWorkspaceStore()
const workspace = toRef(workspaceStore, 'workspace')
</script>
