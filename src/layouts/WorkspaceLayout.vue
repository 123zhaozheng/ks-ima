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
      <q-toolbar-title>{{ workspace?.name }}</q-toolbar-title>
    </q-toolbar>
    <q-tabs
      v-if="workspace?.member?.role === 'owner' || workspace?.member?.role === 'admin'"
      active-color="primary"
      align="left"
      no-caps
    >
      <q-route-tab
        :label="t('Overview')"
        to="/workspace"
      />
      <q-route-tab
        :label="t('Connectors')"
        to="/workspace/connectors"
      />
      <q-route-tab
        :label="t('Logs')"
        to="/workspace/usage"
      />
    </q-tabs>
  </q-header>
  <router-view v-if="workspace" />
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
