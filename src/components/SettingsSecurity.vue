<template>
  <section
    class="tk-card settings-card"
    data-testid="settings-security"
  >
    <div class="settings-card-head">
      <h2 class="tk-card-title">
        {{ t('Security') }}
      </h2>
    </div>
    <q-banner
      v-if="error"
      rounded
      class="settings-error"
    >
      {{ error }}
    </q-banner>
    <q-list>
      <common-item
        icon="sym_o_lock"
        :label="t('Change password')"
        clickable
        data-testid="settings-change-password"
        @click="changePassword"
      >
        <q-icon name="sym_o_chevron_right" />
      </common-item>
    </q-list>
    <q-separator spaced />
    <div class="settings-sub">
      <div class="settings-sub-head">
        <div>
          <h3 class="settings-sub-title">
            {{ t('Two-factor authentication') }}
          </h3>
          <p class="tk-card-subtitle">
            {{ t('Use an authenticator app or a recovery code at sign-in.') }}
          </p>
        </div>
        <q-space />
        <q-btn
          v-if="!totpUri"
          unelevated
          no-caps
          color="primary"
          :label="t('Set up TOTP')"
          :loading="loading"
          data-testid="settings-totp-setup"
          @click="startTotp"
        />
        <q-btn
          v-else
          flat
          no-caps
          color="negative"
          :label="t('Disable TOTP')"
          :loading="loading"
          @click="disableTotp"
        />
      </div>
      <div
        v-if="totpUri"
        class="settings-sub-body"
      >
        <q-input
          :model-value="totpUri"
          readonly
          type="textarea"
          outlined
          :label="t('Authenticator setup URI')"
        />
        <q-input
          v-model="totpCode"
          outlined
          inputmode="numeric"
          :label="t('Verification code')"
        />
        <q-btn
          unelevated
          no-caps
          color="primary"
          :label="t('Confirm and show recovery codes')"
          :loading="loading"
          @click="confirmTotp"
        />
      </div>
      <div
        v-if="recoveryCodes.length"
        class="settings-codes"
      >
        <div class="settings-codes-title">
          {{ t('Save these recovery codes now') }}
        </div>
        <pre>{{ recoveryCodes.join('\n') }}</pre>
        <q-btn
          flat
          dense
          no-caps
          icon="sym_o_download"
          :label="t('Download recovery codes')"
          @click="downloadCodes"
        />
      </div>
    </div>
    <q-separator spaced />
    <div class="settings-sub">
      <div class="settings-sub-head">
        <h3 class="settings-sub-title">
          {{ t('Active sessions') }}
        </h3>
        <q-space />
        <q-btn
          flat
          no-caps
          color="negative"
          :label="t('Revoke all')"
          :loading="loading"
          data-testid="settings-revoke-all"
          @click="revokeAll"
        />
      </div>
      <q-list separator>
        <q-item
          v-for="item in sessions"
          :key="item.id"
        >
          <q-item-section>
            <q-item-label>
              {{ item.userAgent || t('Unknown browser') }}
              <q-badge
                v-if="item.current"
                color="primary"
              >
                {{ t('Current') }}
              </q-badge>
            </q-item-label>
            <q-item-label caption>
              {{ t('Last active {0}; expires {1}', new Date(item.lastActivityAt).toLocaleString(), new Date(item.expiresAt).toLocaleString()) }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-btn
              v-if="!item.current"
              icon="sym_o_logout"
              flat
              round
              dense
              :title="t('Revoke')"
              @click="revoke(item.id)"
            />
          </q-item-section>
        </q-item>
        <q-item v-if="!sessions.length">
          <q-item-section class="settings-empty">
            {{ t('No other active sessions.') }}
          </q-item-section>
        </q-item>
      </q-list>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useQuasar } from 'quasar'
import type { components } from 'src/api/generated/schema'
import ChangePasswordDialog from 'src/components/ChangePasswordDialog.vue'
import CommonItem from 'src/components/CommonItem.vue'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type SessionInfo = components['schemas']['SessionInfo']

const $q = useQuasar()

const sessions = ref<SessionInfo[]>([])
const totpUri = ref('')
const totpCode = ref('')
const recoveryCodes = ref<string[]>([])
const error = ref('')
const loading = ref(false)

async function load() {
  const result = await identityClient.listSessions()
  if (result.error) error.value = result.error.message
  sessions.value = result.data ?? []
}

function changePassword() {
  $q.dialog({ component: ChangePasswordDialog })
}

async function startTotp() {
  loading.value = true
  const result = await identityClient.startTotp()
  if (result.error) error.value = result.error.message
  totpUri.value = result.data?.otpauthUri ?? ''
  loading.value = false
}

async function confirmTotp() {
  loading.value = true
  const result = await identityClient.confirmTotp(totpCode.value)
  if (result.error) error.value = result.error.message
  recoveryCodes.value = result.data?.recoveryCodes ?? []
  loading.value = false
}

async function disableTotp() {
  loading.value = true
  const result = await identityClient.disableTotp()
  if (result.error) error.value = result.error.message
  if (!result.error) totpUri.value = ''
  loading.value = false
}

async function revoke(id: string) {
  await identityClient.revokeSession(id)
  await load()
}

async function revokeAll() {
  await identityClient.revokeAllSessions()
  await load()
}

function downloadCodes() {
  const blob = new Blob([recoveryCodes.value.join('\n')], { type: 'text/plain' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = 'ima-recovery-codes.txt'
  link.click()
  URL.revokeObjectURL(link.href)
}

onMounted(load)
</script>

<style scoped>
.settings-card-head {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.settings-error {
  margin: 0 var(--tk-space-4) var(--tk-space-2);
  background-color: var(--tk-danger-soft);
  color: var(--tk-danger);
}

.settings-sub-head {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-2) var(--tk-space-4);
}

.settings-sub-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--tk-text);
  margin: 0;
}

.settings-sub-body {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-3);
  padding: var(--tk-space-2) var(--tk-space-4) var(--tk-space-4);
}

.settings-codes {
  margin: 0 var(--tk-space-4) var(--tk-space-4);
  padding: var(--tk-space-3);
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface);
  border: 1px solid var(--tk-border);
}

.settings-codes-title {
  font-weight: 600;
  margin-bottom: var(--tk-space-2);
}

.settings-codes pre {
  margin: 0 0 var(--tk-space-2);
  font-family: ui-monospace, monospace;
  white-space: pre-wrap;
}

.settings-empty {
  color: var(--tk-text-secondary);
}
</style>
