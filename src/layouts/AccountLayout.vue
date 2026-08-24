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
      /><q-toolbar-title>Account</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      v-if="user"
      max-w="800px"
      mx-a
      py-2
    >
      <q-list>
        <common-item label="Name">
          <a-input
            :model-value="user.displayName"
            @change="updateName"
            dense
            filled
          />
        </common-item>
        <common-item label="Email">
          {{ user.email }}
        </common-item>
        <common-item
          label="Security and sessions"
          clickable
          @click="$router.push('/account/security')"
        >
          <q-icon name="sym_o_security" />
        </common-item>
        <common-item
          label="Change password"
          clickable
          @click="changePassword"
        >
          <q-icon name="sym_o_chevron_right" />
        </common-item>
      </q-list>
    </q-page>
    <q-page
      v-else-if="loading"
      flex
      items-center
      justify-center
    >
      <q-spinner />
    </q-page>
    <q-page
      v-else
      flex
      items-center
      justify-center
    >
      <q-banner>Account session expired or unavailable.</q-banner>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import CommonItem from 'src/components/CommonItem.vue'
import AInput from 'src/components/AInput'
import ChangePasswordDialog from 'src/components/ChangePasswordDialog.vue'
import { useUiStateStore } from 'src/stores/ui-state'
import { identityClient, session } from 'src/utils/identity-client'
import { useQuasar } from 'quasar'

const uiStateStore = useUiStateStore()
const $q = useQuasar()
const loading = ref(session.value.isPending)
const user = computed(() => session.value.data?.user)
async function updateName(displayName: string) {
  loading.value = true
  const result = await identityClient.updateProfile({ displayName })
  if (result.error) $q.notify({ type: 'negative', message: result.error.message })
  else await identityClient.getSession()
  loading.value = false
}
function changePassword() { $q.dialog({ component: ChangePasswordDialog }) }
</script>
