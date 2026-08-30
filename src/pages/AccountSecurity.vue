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
      <q-toolbar-title>{{ t('Account Security') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page class="tk-page security-page">
      <q-banner
        v-if="error"
        rounded
        class="security-error"
      >
        {{ error }}
      </q-banner>
      <section class="tk-card security-card">
        <div class="security-card-head">
          <h2 class="tk-card-title">
            {{ t('Account profile') }}
          </h2>
        </div>
        <div class="security-card-body">
          <q-input
            v-model="displayName"
            dense
            outlined
            :label="t('Display name')"
            :loading="loading"
          />
          <q-btn
            unelevated
            no-caps
            color="primary"
            :label="t('Save profile')"
            :loading="loading"
            @click="saveProfile"
          />
        </div>
      </section>
      <section class="tk-card security-card">
        <div class="security-card-head">
          <div>
            <h2 class="tk-card-title">
              {{ t('Two-factor authentication') }}
            </h2>
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
          class="security-card-body"
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
          class="security-codes"
        >
          <div class="security-codes-title">
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
      </section>
      <section class="tk-card security-card">
        <div class="security-card-head">
          <h2 class="tk-card-title">
            {{ t('Active sessions') }}
          </h2>
          <q-space />
          <q-btn
            flat
            no-caps
            color="negative"
            :label="t('Revoke all')"
            :loading="loading"
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
            <q-item-section class="security-empty">
              {{ t('No other active sessions.') }}
            </q-item-section>
          </q-item>
        </q-list>
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { identityClient, session } from 'src/utils/identity-client'
import { useUiStateStore } from 'src/stores/ui-state'
import { t } from 'src/utils/i18n'
import type { components } from 'src/api/generated/schema'

const uiStateStore = useUiStateStore()

type SessionInfo = components['schemas']['SessionInfo']
const displayName = ref('')
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
  displayName.value = session.value.data?.user.displayName ?? ''
}
async function saveProfile() {
  loading.value = true
  const result = await identityClient.updateProfile({ displayName: displayName.value })
  if (result.error) error.value = result.error.message
  loading.value = false
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
async function revoke(id: string) { await identityClient.revokeSession(id); await load() }
async function revokeAll() { await identityClient.revokeAllSessions(); await load() }
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
.security-page {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-4);
  max-width: 800px;
}

.security-error {
  background-color: var(--tk-danger-soft);
  color: var(--tk-danger);
}

.security-card-head {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.security-card-body {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-3);
  padding: var(--tk-space-2) var(--tk-space-4) var(--tk-space-4);
}

.security-codes {
  margin: 0 var(--tk-space-4) var(--tk-space-4);
  padding: var(--tk-space-3);
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface);
  border: 1px solid var(--tk-border);
}

.security-codes-title {
  font-weight: 600;
  margin-bottom: var(--tk-space-2);
}

.security-codes pre {
  margin: 0 0 var(--tk-space-2);
  font-family: ui-monospace, monospace;
  white-space: pre-wrap;
}

.security-empty {
  color: var(--tk-text-secondary);
}
</style>
