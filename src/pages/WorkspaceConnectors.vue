<template>
  <q-page-container>
    <q-page
      v-if="workspaceStore.id"
      class="access-page"
    >
      <section class="band">
        <header>
          <q-icon
            name="sym_o_link"
            size="24px"
          /><div><h1>{{ t('Agent access') }}</h1><p>{{ t('Interactive connections') }}</p></div>
        </header>
        <q-list separator>
          <q-item>
            <q-item-section>
              <q-item-label>{{ t('MCP resource') }}</q-item-label><q-item-label
                caption
                class="mono"
              >
                {{ mcpUrl }}
              </q-item-label>
            </q-item-section><q-item-section side>
              <q-btn
                flat
                round
                icon="sym_o_content_copy"
                :title="t('Copy')"
                @click="copy(mcpUrl)"
              />
            </q-item-section>
          </q-item><q-item v-if="!grants.length">
            <q-item-section>
              <q-item-label>{{ t('Connected agents') }}</q-item-label><q-item-label caption>
                {{ t('No interactive grants are available.') }}
              </q-item-label>
            </q-item-section>
          </q-item><q-item
            v-for="grant in grants"
            :key="grant.id"
          >
            <q-item-section>
              <q-item-label>{{ grant.clientName }}</q-item-label><q-item-label caption>
                {{ grant.scopes.map(scopeLabel).join(' · ') }} · {{ formatTime(grant.expiresAt) }}
              </q-item-label>
            </q-item-section><q-item-section side>
              <q-btn
                flat
                round
                color="negative"
                icon="sym_o_link_off"
                :title="t('Revoke')"
                @click="revokeGrant(grant.id)"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </section>
      <section class="band">
        <header>
          <q-icon
            name="sym_o_key"
            size="24px"
          /><div><h2>{{ t('Service access') }}</h2><p>{{ t('Unattended agents') }}</p></div>
        </header>
        <q-banner
          v-if="error"
          class="text-negative"
          aria-live="polite"
        >
          {{ error }}
        </q-banner>
        <q-banner
          v-if="oneTime"
          class="secret"
        >
          <strong>{{ t('One-time credential') }}</strong><code>{{ oneTime.secret }}</code><template #action>
            <q-btn
              flat
              round
              icon="sym_o_content_copy"
              :title="t('Copy')"
              @click="copy(oneTime.secret)"
            /><q-btn
              flat
              round
              icon="sym_o_close"
              :title="t('Dismiss')"
              @click="oneTime = null"
            />
          </template>
        </q-banner>
        <div
          v-if="isAdmin"
          class="create-grid"
        >
          <q-input
            v-model="form.displayName"
            outlined
            dense
            :label="t('Name')"
          /><q-input
            v-model="form.purpose"
            outlined
            dense
            :label="t('Purpose')"
          /><q-input
            v-model="form.ownerUserId"
            outlined
            dense
            :label="t('Owner user ID')"
          /><q-input
            v-model="form.folderRootId"
            outlined
            dense
            :label="t('Folder root (optional)')"
          /><q-input
            v-model.number="form.expiresDays"
            outlined
            dense
            type="number"
            min="1"
            max="90"
            :label="t('Expires in days')"
          />
          <div class="scopes">
            <q-checkbox
              v-for="scope in scopeOptions"
              :key="scope"
              v-model="form.scopes"
              :val="scope"
              :label="scopeLabel(scope)"
            />
          </div>
          <q-btn
            unelevated
            no-caps
            color="primary"
            icon="sym_o_add"
            :label="t('Create service principal')"
            :loading="creating"
            @click="createPrincipal"
          />
        </div>
        <q-list separator>
          <q-item v-if="!isAdmin && !loading">
            <q-item-section>{{ t('Workspace administrators manage service access.') }}</q-item-section>
          </q-item>
          <q-item v-if="loading">
            <q-item-section>{{ t('Loading service access…') }}</q-item-section>
          </q-item><q-item v-else-if="isAdmin && !principals.length">
            <q-item-section>{{ t('No service principals') }}</q-item-section>
          </q-item><q-item
            v-for="principal in principals"
            :key="principal.id"
          >
            <q-item-section>
              <q-item-label>{{ principal.displayName }}</q-item-label><q-item-label caption>
                {{ principal.purpose }} · {{ principal.state }} · {{ formatTime(principal.expiresAt) }}
              </q-item-label><q-item-label caption>
                {{ principal.scopes.map(scopeLabel).join(' · ') }}<span v-if="principal.folderRootId"> · {{ t('Folder-scoped') }}</span>
              </q-item-label>
              <div
                v-for="credential in credentials[principal.id] ?? []"
                :key="credential.id"
                class="credential-row"
              >
                <span class="mono">{{ credential.secretPrefix }}...</span>
                <span>{{ formatTime(credential.expiresAt) }}</span>
                <q-btn
                  v-if="!credential.revokedAt"
                  flat
                  round
                  color="negative"
                  icon="sym_o_key_off"
                  :title="t('Revoke credential')"
                  @click="revokeCredential(principal.id, credential.credentialId)"
                />
              </div>
            </q-item-section><q-item-section
              v-if="isAdmin"
              side
            >
              <div>
                <q-btn
                  v-if="activeCredential(principal.id)"
                  flat
                  round
                  icon="sym_o_refresh"
                  :title="t('Rotate')"
                  @click="rotateFirstCredential(principal)"
                /><q-btn
                  flat
                  round
                  color="negative"
                  icon="sym_o_delete"
                  :title="t('Revoke')"
                  @click="revokePrincipal(principal.id)"
                />
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </section>
      <section
        v-if="isAdmin"
        class="band"
      >
        <header>
          <q-icon
            name="sym_o_history"
            size="24px"
          /><div><h2>{{ t('Legacy connectors') }}</h2><p>{{ t('Compatibility access') }}</p></div>
        </header>
        <q-list separator>
          <q-item>
            <q-item-section>{{ t('Existing connector keys remain available during migration.') }}</q-item-section>
            <q-item-section side>
              <q-btn
                outline
                no-caps
                :label="t('Create connector')"
                @click="openLegacyCreate"
              />
            </q-item-section>
          </q-item>
          <q-item
            v-for="row in legacyRows"
            :key="row.id"
          >
            <q-item-section>
              <q-item-label>{{ row.name }}</q-item-label>
              <q-item-label caption>
                {{ row.keyPrefix }}... · {{ row.mode === 'readwrite' ? t('Read and write') : t('Read only') }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <div>
                <q-btn
                  flat
                  no-caps
                  :label="t('Rotate key')"
                  @click="rotateLegacy(row.id)"
                />
                <q-btn
                  flat
                  no-caps
                  color="negative"
                  :label="t('Revoke')"
                  @click="revokeLegacy(row.id)"
                />
              </div>
            </q-item-section>
          </q-item>
          <q-item v-if="legacyLoading">
            <q-item-section>{{ t('Loading connectors…') }}</q-item-section>
          </q-item>
          <q-item v-else-if="legacyError">
            <q-item-section class="text-negative">{{ legacyError }}</q-item-section>
          </q-item>
          <q-item v-else-if="!legacyRows.length">
            <q-item-section>{{ t('No legacy connectors') }}</q-item-section>
          </q-item>
        </q-list>
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { copyToClipboard, useQuasar } from 'quasar'
import { useWorkspaceStore } from 'src/stores/workspace'
import CreateConnectorDialog from 'src/components/CreateConnectorDialog.vue'
import ConnectorCreatedDialog from 'src/components/ConnectorCreatedDialog.vue'
import { client } from 'src/utils/hc'
import { rejectAfter } from 'src/utils/reject-after'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type ServicePrincipal = components['schemas']['ServicePrincipalResponse']
type CredentialIssue = components['schemas']['CredentialIssueResponse']
type ServicePrincipalCreate = components['schemas']['ServicePrincipalCreate']
type ConnectedGrant = components['schemas']['ConnectedGrantResponse']
type Credential = components['schemas']['CredentialViewResponse']
type LegacyConnector = {
  id: string
  name: string
  keyPrefix: string
  mode: 'read' | 'readwrite'
}

const scopeOptions = [
  'mcp:workspaces:read',
  'mcp:knowledge:read',
  'mcp:knowledge:search',
]
const workspaceStore = useWorkspaceStore()
const $q = useQuasar()
const principals = ref<ServicePrincipal[]>([])
const grants = ref<ConnectedGrant[]>([])
const credentials = ref<Record<string, Credential[]>>({})
const oneTime = ref<CredentialIssue | null>(null)
const role = ref('')
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const legacyRows = ref<LegacyConnector[]>([])
const legacyLoading = ref(false)
const legacyError = ref('')
const mcpUrl = window.location.origin.replace(/\/$/, '') + '/mcp'
const isAdmin = computed(() => role.value === 'workspace_admin')
const form = reactive({
  displayName: '',
  purpose: '',
  ownerUserId: '',
  folderRootId: '',
  expiresDays: 30,
  scopes: ['mcp:knowledge:read'],
})
let loadGeneration = 0

function scopeLabel(scope: string) {
  return scope.replace('mcp:', '').replaceAll(':', ' · ')
}

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

function activeCredential(principalId: string) {
  return credentials.value[principalId]?.find(
    credential => !credential.revokedAt && new Date(credential.expiresAt).getTime() > Date.now(),
  )
}

function isLegacyConnector(value: unknown): value is LegacyConnector {
  if (!value || typeof value !== 'object') return false
  if (!('id' in value) || !('name' in value) || !('keyPrefix' in value) || !('mode' in value)) return false
  return typeof value.id === 'string' &&
    typeof value.name === 'string' &&
    typeof value.keyPrefix === 'string' &&
    (value.mode === 'read' || value.mode === 'readwrite')
}

async function loadLegacy(workspaceId: string, generation: number) {
  legacyLoading.value = true
  legacyError.value = ''
  try {
    const response = await Promise.race([
      client.api.connectors.$get({ query: { workspaceId } }),
      rejectAfter(5000),
    ])
    if (generation !== loadGeneration) return
    if (!response.ok) throw new Error('legacy connector request failed')
    const body: unknown = await response.json()
    if (!Array.isArray(body) || !body.every(isLegacyConnector)) {
      throw new Error('legacy connector response is invalid')
    }
    legacyRows.value = body
  } catch {
    if (generation === loadGeneration) {
      legacyRows.value = []
      legacyError.value = t('Could not load legacy connectors.')
    }
  } finally {
    if (generation === loadGeneration) legacyLoading.value = false
  }
}

async function load() {
  const workspaceId = workspaceStore.id
  if (!workspaceId) return
  const generation = ++loadGeneration
  loading.value = true
  error.value = ''
  try {
    const [workspace, connected] = await Promise.all([
      identityClient.getMemberWorkspace(workspaceId),
      identityClient.listConnectedOAuthGrants(),
    ])
    if (generation !== loadGeneration) return
    role.value = workspace.data?.role ?? ''
    grants.value = (connected.data ?? []).filter(grant => grant.workspaceId === workspaceId)
    error.value = workspace.error?.message ?? connected.error?.message ?? ''
    principals.value = []
    credentials.value = {}
    if (role.value !== 'workspace_admin') return

    const legacyLoad = loadLegacy(workspaceId, generation)
    const list = await identityClient.listServicePrincipals(workspaceId)
    if (generation !== loadGeneration) return
    principals.value = list.data ?? []
    error.value = list.error?.message ?? error.value
    if (list.error) { await legacyLoad; return }
    const details = await Promise.all(
      principals.value.map(principal => identityClient.getServicePrincipal(workspaceId, principal.id)),
    )
    if (generation !== loadGeneration) return
    credentials.value = Object.fromEntries(
      details.flatMap(detail => detail.data ? [[detail.data.id, detail.data.credentials]] : []),
    )
    error.value = details.find(detail => detail.error)?.error?.message ?? error.value
    await legacyLoad
  } catch {
    if (generation === loadGeneration) error.value = t('Agent access is unavailable.')
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function createPrincipal() {
  const workspaceId = workspaceStore.id
  if (!workspaceId || creating.value) return
  error.value = ''
  oneTime.value = null
  if (!form.displayName.trim() || !form.purpose.trim() || !form.ownerUserId || !form.scopes.length) {
    error.value = t('Complete the required service access fields.')
    return
  }
  creating.value = true
  const expiresDays = Math.min(90, Math.max(1, Number(form.expiresDays) || 1))
  const payload = {
    displayName: form.displayName.trim(),
    purpose: form.purpose.trim(),
    ownerUserId: form.ownerUserId,
    folderRootId: form.folderRootId || null,
    scopes: form.scopes,
    expiresAt: new Date(Date.now() + expiresDays * 86400000).toISOString(),
    rateLimit: 300,
    concurrencyLimit: 10,
    cidrAllowlist: [],
  } satisfies ServicePrincipalCreate
  try {
    const result = await identityClient.createServicePrincipal(workspaceId, payload)
    if (result.data) {
      oneTime.value = result.data
      form.displayName = ''
      form.purpose = ''
      await load()
    } else {
      error.value = result.error?.message ?? t('Could not create service principal')
    }
  } finally {
    creating.value = false
  }
}

async function revokePrincipal(id: string) {
  const workspaceId = workspaceStore.id
  if (!workspaceId) return
  const result = await identityClient.revokeServicePrincipal(workspaceId, id)
  if (result.error) error.value = result.error.message
  else await load()
}

async function revokeGrant(id: string) {
  const result = await identityClient.revokeConnectedOAuthGrant(id)
  if (result.error) error.value = result.error.message
  else await load()
}

async function rotateFirstCredential(principal: ServicePrincipal) {
  const workspaceId = workspaceStore.id
  const credential = activeCredential(principal.id)
  if (!workspaceId || !credential) return
  oneTime.value = null
  const result = await identityClient.rotateServiceCredential(
    workspaceId,
    principal.id,
    credential.credentialId,
    { expiresAt: principal.expiresAt, overlapExpiresAt: null },
  )
  if (result.data) oneTime.value = result.data
  else error.value = result.error?.message ?? t('Could not rotate credential')
  await load()
}

async function revokeCredential(principalId: string, credentialId: string) {
  const workspaceId = workspaceStore.id
  if (!workspaceId) return
  const result = await identityClient.revokeServiceCredential(
    workspaceId,
    principalId,
    credentialId,
  )
  if (result.error) error.value = result.error.message
  else await load()
}

function showLegacySecret(value: unknown) {
  if (!value || typeof value !== 'object' || !('apiKey' in value) || typeof value.apiKey !== 'string') return
  $q.dialog({
    component: ConnectorCreatedDialog,
    componentProps: { apiKey: value.apiKey },
  })
}

function openLegacyCreate() {
  $q.dialog({ component: CreateConnectorDialog }).onOk((value: unknown) => {
    showLegacySecret(value)
    load().catch(() => undefined)
  })
}

function rotateLegacy(id: string) {
  $q.dialog({
    title: t('Rotate key'),
    message: t('The old key stops working immediately and a new key is shown once.'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    const response = await client.api.connectors[':id'].rotate.$post({ param: { id } })
    const body: unknown = await response.json()
    showLegacySecret(body)
    if (body && typeof body === 'object' && 'error' in body && typeof body.error === 'string') {
      $q.notify({ type: 'negative', message: body.error })
    }
    await load()
  })
}

function revokeLegacy(id: string) {
  $q.dialog({
    title: t('Revoke'),
    message: t('This key will stop working immediately.'),
    cancel: true,
    persistent: true,
  }).onOk(async () => {
    await client.api.connectors[':id'].$delete({ param: { id } })
    await load()
  })
}

async function copy(value: string) {
  await copyToClipboard(value)
  $q.notify({ message: t('Copied'), type: 'positive' })
}

watch(
  () => session.value.data?.user.id,
  userId => {
    if (!form.ownerUserId && userId) form.ownerUserId = userId
  },
  { immediate: true },
)
watch(() => workspaceStore.id, () => {
  loadGeneration += 1
  oneTime.value = null
  principals.value = []
  credentials.value = {}
  grants.value = []
  legacyRows.value = []
  load().catch(() => undefined)
})
onMounted(() => { load().catch(() => undefined) })
onBeforeUnmount(() => { oneTime.value = null })
</script>

<style scoped>
.access-page{max-width:900px;margin:0 auto;padding:20px}.band{padding:18px 0 28px;border-bottom:1px solid var(--q-outline-variant)}header{display:flex;align-items:center;gap:12px;margin-bottom:14px}h1,h2{margin:0;font-size:20px}p{margin:2px 0 0;color:var(--q-on-surface-variant)}.mono,code{font-family:ui-monospace,monospace;overflow-wrap:anywhere}.secret{margin:12px 0}.secret strong,.secret code{display:block;margin-bottom:6px}.create-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:18px 0}.scopes{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:4px 14px}.credential-row{display:grid;grid-template-columns:minmax(100px,1fr) minmax(140px,auto) 40px;align-items:center;gap:8px;margin-top:8px}@media(max-width:640px){.access-page{padding:12px}.create-grid{grid-template-columns:1fr}.scopes{grid-column:auto;flex-direction:column}.credential-row{grid-template-columns:1fr 40px}.credential-row span:nth-child(2){grid-column:1}}
</style>
