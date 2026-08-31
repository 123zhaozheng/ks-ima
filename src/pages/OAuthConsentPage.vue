<template>
  <q-page-container>
    <q-page class="consent-page">
      <header class="consent-header">
        <q-icon
          name="sym_o_verified_user"
          size="32px"
          color="primary"
        />
        <div>
          <h1>{{ t('Connect agent') }}</h1>
          <p v-if="preview">
            {{ preview.clientName }}
          </p>
        </div>
      </header>

      <q-banner
        v-if="session.isPending"
        class="state-banner"
      >
        {{ t('Loading authorization request…') }}
      </q-banner>
      <q-banner
        v-else-if="!session.data"
        class="state-banner text-negative"
      >
        {{ t('Your session expired. Sign in to continue.') }}
        <template #action>
          <q-btn
            flat
            no-caps
            :label="t('Sign in')"
            :to="signInTarget"
          />
        </template>
      </q-banner>
      <q-banner
        v-else-if="error"
        class="state-banner text-negative"
        aria-live="polite"
      >
        {{ error }}
        <template
          v-if="needsRecentAuth"
          #action
        >
          <q-btn
            flat
            no-caps
            :label="t('Sign in')"
            :to="signInTarget"
          />
        </template>
      </q-banner>

      <template v-if="preview && session.data">
        <section class="consent-section">
          <h2>{{ t('Connection') }}</h2>
          <q-list separator>
            <q-item>
              <q-item-section>
                <q-item-label caption>
                  {{ t('Client') }}
                </q-item-label><q-item-label>{{ preview.clientName }}</q-item-label>
              </q-item-section>
            </q-item>
            <q-item>
              <q-item-section>
                <q-item-label caption>
                  {{ t('Resource') }}
                </q-item-label><q-item-label class="mono">
                  {{ preview.resource }}
                </q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </section>

        <section class="consent-section">
          <h2>{{ t('Access') }}</h2>
          <div class="scope-list">
            <q-badge
              v-for="scope in preview.scopes"
              :key="scope"
              outline
              color="primary"
            >
              {{ scopeLabel(scope) }}
            </q-badge>
          </div>
          <q-banner
            v-if="preview.writeAccess"
            class="write-warning"
            text-warning
          >
            <q-icon name="sym_o_edit" /> {{ t('This connection can change knowledge content.') }}
          </q-banner>
          <q-list separator>
            <q-item>
              <q-item-section>
                <q-item-label caption>
                  {{ t('Expires') }}
                </q-item-label><q-item-label>{{ formatTime(preview.expiresAt) }}</q-item-label>
              </q-item-section>
            </q-item>
          </q-list>
        </section>

        <footer class="consent-actions">
          <q-btn
            flat
            no-caps
            icon="sym_o_close"
            :label="t('Deny')"
            :loading="submitting"
            :disable="submitting"
            @click="submit(false)"
          />
          <q-btn
            unelevated
            no-caps
            color="primary"
            icon="sym_o_check"
            :label="preview.consentRequired ? t('Approve') : t('Continue')"
            :loading="submitting"
            :disable="submitting"
            @click="submit(true)"
          />
        </footer>
      </template>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type ConsentView = components['schemas']['ConsentView']
type ConsentSubmit = components['schemas']['ConsentSubmit']

const route = useRoute()
const preview = ref<ConsentView | null>(null)
const error = ref('')
const submitting = ref(false)
const signInTarget = computed(() => ({ path: '/auth/sign-in', query: { redirect: route.fullPath } }))
const authorizationQuery = computed(() => route.fullPath.split('?', 2)[1]?.split('#', 1)[0] ?? '')
const needsRecentAuth = computed(() => one('ui_error') === 'recent_auth')
let loadGeneration = 0

function one(name: string) { const value = route.query[name]; return typeof value === 'string' ? value : '' }
function scopeLabel(scope: string) { return scope.replace('mcp:', '').replaceAll(':', ' · ') }
function formatTime(value: string) { return new Date(value).toLocaleString() }

async function load() {
  if (session.value.isPending || !session.value.data || !authorizationQuery.value) return
  const generation = ++loadGeneration
  const result = await identityClient.previewOAuthConsent(authorizationQuery.value)
  if (generation !== loadGeneration) return
  preview.value = result.data ?? null
  error.value = result.error?.message ?? (needsRecentAuth.value ? t('Sign in again to approve this connection.') : '')
}

function submit(approved: boolean) {
  if (!preview.value || submitting.value) return
  const state = one('state')
  const challenge = one('code_challenge')
  if (!state || !challenge) { error.value = t('The authorization request is incomplete.'); return }
  submitting.value = true
  error.value = ''
  const payload = {
    approved,
    clientId: one('client_id'),
    redirectUri: preview.value.redirectUri,
    resource: preview.value.resource,
    scope: preview.value.scopes.join(' '),
    state,
    codeChallenge: challenge,
    codeChallengeMethod: 'S256',
    expiresAt: preview.value.expiresAt,
  } satisfies ConsentSubmit
  const form = document.createElement('form')
  form.method = 'post'; form.action = '/oauth/authorize/decision'
  const values: Record<string, string> = {
    approved: String(payload.approved),
    client_id: payload.clientId,
    redirect_uri: payload.redirectUri,
    resource: payload.resource,
    scope: payload.scope,
    state: payload.state,
    code_challenge: payload.codeChallenge,
    code_challenge_method: payload.codeChallengeMethod,
    expires_at: payload.expiresAt,
    csrf_token: decodeURIComponent(document.cookie.split('; ').find(value => value.startsWith('ima_csrf='))?.split('=').slice(1).join('=') ?? ''),
  }
  for (const [name, value] of Object.entries(values)) { const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value; form.appendChild(input) }
  document.body.appendChild(form); form.submit()
}

watch(
  [() => route.fullPath, () => session.value.isPending, () => session.value.data?.user.id],
  () => {
    preview.value = null
    error.value = ''
    load().catch(() => undefined)
  },
  { immediate: true },
)
</script>

<style scoped>
.consent-page { max-width: 760px; margin: 0 auto; padding: 32px 20px; }
.consent-header { display: flex; gap: 14px; align-items: center; margin-bottom: 24px; }
h1 { margin: 0; font-size: 26px; line-height: 1.2; color: var(--tk-text); } h2 { font-size: 17px; margin: 0 0 8px; color: var(--tk-text); }
p { margin: 4px 0 0; color: var(--tk-text-secondary); }
.consent-section { padding: 18px 0; border-top: 1px solid var(--tk-border); }
.scope-list { display: flex; flex-wrap: wrap; gap: 8px; padding: 8px 0 14px; }
.write-warning, .state-banner { margin: 12px 0; border-radius: var(--tk-radius); } .mono { font-family: ui-monospace, monospace; overflow-wrap: anywhere; }
.consent-actions { display: flex; justify-content: flex-end; gap: 8px; padding-top: 18px; border-top: 1px solid var(--tk-border); }
@media (max-width: 600px) { .consent-page { padding: 20px 14px; } .consent-actions { justify-content: stretch; } .consent-actions :deep(.q-btn) { flex: 1; } }
</style>
