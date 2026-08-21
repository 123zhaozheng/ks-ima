<template>
  <q-drawer
    show-if-above
    bg-sur-c
    flex="~ col"
    p-2
  >
    <q-list>
      <q-item
        to="/users"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_group" />
        </q-item-section>
        <q-item-section>
          {{ t('Users') }}
        </q-item-section>
      </q-item>
      <q-item
        to="/workspaces"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_deployed_code" />
        </q-item-section>
        <q-item-section>
          {{ t('Workspaces') }}
        </q-item-section>
      </q-item>
      <q-item
        to="/plans"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_sell" />
        </q-item-section>
        <q-item-section>
          {{ t('Plans') }}
        </q-item-section>
      </q-item>
      <q-item
        to="/models"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_neurology" />
        </q-item-section>
        <q-item-section>
          {{ t('Models') }}
        </q-item-section>
      </q-item>
      <q-item
        clickable
        @click="openSettings"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_settings" />
        </q-item-section>
        <q-item-section>
          {{ t('Settings') }}
        </q-item-section>
      </q-item>
    </q-list>
    <q-list mt-a>
      <q-item
        clickable
        @click="signOut"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_logout" />
        </q-item-section>
        <q-item-section>
          {{ t('Sign Out') }}
        </q-item-section>
      </q-item>
    </q-list>
  </q-drawer>
</template>

<script setup lang="ts">
import { useQuasar } from 'quasar'
import { authClient } from 'src/utils/auth-client'
import { t } from 'src/utils/i18n'
import { useRouter } from 'vue-router'
import UpdateSettingsDialog from './UpdateSettingsDialog.vue'

const router = useRouter()
function signOut() {
  authClient.signOut()
  router.push('/auth/sign-in')
}

const $q = useQuasar()
function openSettings() {
  $q.dialog({
    component: UpdateSettingsDialog,
  })
}
</script>
