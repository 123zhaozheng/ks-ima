<template>
  <q-page-container>
    <q-page
      max-w="900px"
      mx-a
      p-4
    >
      <q-banner
        v-if="error"
        rounded
        bg-err-c
        text-on-err-c
        mb-4
      >
        {{ error }}
      </q-banner>
      <q-card
        flat
        bordered
        mb-4
      >
        <q-card-section>
          <div class="text-h6">
            Account profile
          </div>
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="displayName"
            label="Display name"
            :loading="loading"
          />
          <q-btn
            label="Save profile"
            color="primary"
            mt-3
            :loading="loading"
            @click="saveProfile"
          />
        </q-card-section>
      </q-card>
      <q-card
        flat
        bordered
        mb-4
      >
        <q-card-section class="row items-center">
          <div>
            <div class="text-h6">
              Two-factor authentication
            </div>
            <div class="text-caption">
              Use an authenticator app or a recovery code at sign-in.
            </div>
          </div>
          <q-space />
          <q-btn
            v-if="!totpUri"
            label="Set up TOTP"
            color="primary"
            :loading="loading"
            @click="startTotp"
          />
          <q-btn
            v-else
            label="Disable TOTP"
            color="negative"
            flat
            :loading="loading"
            @click="disableTotp"
          />
        </q-card-section>
        <q-card-section v-if="totpUri">
          <q-input
            :model-value="totpUri"
            readonly
            type="textarea"
            label="Authenticator setup URI"
          />
          <q-input
            v-model="totpCode"
            label="Verification code"
            inputmode="numeric"
            mt-3
          />
          <q-btn
            label="Confirm and show recovery codes"
            color="primary"
            mt-3
            :loading="loading"
            @click="confirmTotp"
          />
        </q-card-section>
        <q-card-section
          v-if="recoveryCodes.length"
          bg-warning
          text-dark
        >
          <div class="text-subtitle1">
            Save these recovery codes now
          </div>
          <pre>{{ recoveryCodes.join('\n') }}</pre>
          <q-btn
            label="Download recovery codes"
            icon="download"
            flat
            @click="downloadCodes"
          />
        </q-card-section>
      </q-card>
      <q-card
        flat
        bordered
      >
        <q-card-section class="row items-center">
          <div class="text-h6">
            Active sessions
          </div>
          <q-space />
          <q-btn
            label="Revoke all"
            color="negative"
            flat
            :loading="loading"
            @click="revokeAll"
          />
        </q-card-section>
        <q-list separator>
          <q-item
            v-for="item in sessions"
            :key="item.id"
          >
            <q-item-section>
              <q-item-label>
                {{ item.userAgent || 'Unknown browser' }} <q-badge
                  v-if="item.current"
                  color="primary"
                >
                  Current
                </q-badge>
              </q-item-label>
              <q-item-label caption>
                Last active {{ new Date(item.lastActivityAt).toLocaleString() }}; expires {{ new Date(item.expiresAt).toLocaleString() }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                v-if="!item.current"
                icon="logout"
                flat
                round
                @click="revoke(item.id)"
              />
            </q-item-section>
          </q-item>
          <q-item v-if="!sessions.length">
            <q-item-section>No other active sessions.</q-item-section>
          </q-item>
        </q-list>
      </q-card>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { identityClient, session } from 'src/utils/identity-client'
import type { components } from 'src/api/generated/schema'

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
