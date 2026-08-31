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
      <template v-if="user">
        <section
          class="tk-card settings-card"
          data-testid="settings-profile"
        >
          <div class="settings-card-head">
            <h2 class="tk-card-title">
              {{ t('Profile') }}
            </h2>
          </div>
          <q-list>
            <common-item :label="t('Name')">
              <a-input
                :model-value="user.displayName"
                dense
                filled
                :loading="saving"
                @change="updateName"
              />
            </common-item>
            <common-item :label="t('Email')">
              {{ user.email }}
            </common-item>
          </q-list>
        </section>
        <settings-security />
        <settings-list />
      </template>
      <div
        v-else-if="pending"
        class="settings-state"
      >
        <q-spinner color="primary" />
      </div>
      <q-banner
        v-else
        rounded
        class="settings-expired"
      >
        {{ t('Your session expired. Sign in to continue.') }}
      </q-banner>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import AInput from 'src/components/AInput'
import CommonItem from 'src/components/CommonItem.vue'
import SettingsList from 'src/components/SettingsList.vue'
import SettingsSecurity from 'src/components/SettingsSecurity.vue'
import { useRequireLogin } from 'src/composables/require-login'
import { useUiStateStore } from 'src/stores/ui-state'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

useRequireLogin()

const uiStateStore = useUiStateStore()
const $q = useQuasar()

const pending = computed(() => session.value.isPending)
const user = computed(() => session.value.data?.user)
const saving = ref(false)

async function updateName(displayName: string) {
  const next = displayName.trim()
  if (!next || next === user.value?.displayName) return
  saving.value = true
  const result = await identityClient.updateProfile({ displayName: next })
  if (result.error) $q.notify({ type: 'negative', message: result.error.message })
  else await identityClient.getSession()
  saving.value = false
}
</script>

<style scoped>
.settings-page {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-4);
  max-width: 720px;
}

.settings-card-head {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.settings-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--tk-space-8);
}

.settings-expired {
  background-color: var(--tk-surface);
  color: var(--tk-text-secondary);
}
</style>
