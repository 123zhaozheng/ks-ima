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
      <q-toolbar-title>{{ t('Personal Settings') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page class="tk-page settings-page">
      <section class="tk-card settings-card">
        <settings-list />
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import SettingsList from 'src/components/SettingsList.vue'
import { t } from 'src/utils/i18n'
import { useRequireLogin } from 'src/composables/require-login'
import { useUiStateStore } from 'src/stores/ui-state'

useRequireLogin()

const uiStateStore = useUiStateStore()
</script>

<style scoped>
.settings-page {
  max-width: 720px;
}
</style>
