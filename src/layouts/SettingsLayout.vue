<template>
  <q-header
    bg-sur-c-low
    text-on-sur
  >
    <q-toolbar>
      <q-btn
        v-if="!uiStateStore.mainDrawerAbove"
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
        text-on-sur-var
      />
      <q-toolbar-title>
        {{ t('Personal Settings') }}
      </q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      max-w="800px"
      mx-a
    >
      <settings-list />
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
