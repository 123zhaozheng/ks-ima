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
      <q-toolbar-title>{{ t('Connectors') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      v-if="workspaceStore.id"
      class="tk-page connectors-page"
    >
      <section class="tk-card connectors-card">
        <header class="connectors-card-head">
          <q-icon
            name="sym_o_link"
            size="22px"
            color="primary"
          />
          <div>
            <h1 class="tk-card-title">
              {{ t('Agent access') }}
            </h1>
            <p class="tk-card-subtitle">
              {{ t('Interactive connections') }}
            </p>
          </div>
        </header>
        <q-list separator>
          <q-item>
            <q-item-section>
              <q-item-label>{{ t('MCP resource') }}</q-item-label>
              <q-item-label
                caption
                class="mono"
              >
                {{ mcpUrl }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                round
                dense
                icon="sym_o_content_copy"
                :title="t('Copy')"
                @click="copy(mcpUrl)"
              />
            </q-item-section>
          </q-item>
          <q-item v-if="!grants.length">
            <q-item-section>
              <q-item-label>{{ t('Connected agents') }}</q-item-label>
              <q-item-label caption>
                {{ t('No interactive grants are available.') }}
              </q-item-label>
            </q-item-section>
          </q-item>
          <q-item
            v-for="grant in grants"
            :key="grant.id"
          >
            <q-item-section>
              <q-item-label>{{ grant.clientName }}</q-item-label>
              <q-item-label caption>
                {{ grant.scopes.map(scopeLabel).join(' · ') }} · {{ formatTime(grant.expiresAt) }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                round
                dense
                color="negative"
                icon="sym_o_link_off"
                :title="t('Revoke')"
                @click="revokeGrant(grant.id)"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </section>
      <section class="tk-card connectors-card">
        <header class="connectors-card-head">
          <q-icon
            name="sym_o_key"
            size="22px"
            color="primary"
          />
          <div>
            <h2 class="tk-card-title">
              {{ t('Service access') }}
            </h2>
            <p class="tk-card-subtitle">
              {{ t('Unattended agents') }}
            </p>
          </div>
        </header>
        <q-banner
          v-if="error"
          rounded
          class="connectors-banner"
          aria-live="polite"
        >
          {{ error }}
        </q-banner>
        <q-banner
          v-if="oneTime"
          rounded
          class="connectors-secret"
        >
          <strong>{{ t('One-time credential') }}</strong>
          <code class="mono">{{ oneTime.secret }}</code>
          <template #action>
            <q-btn
              flat
              round
              dense
              icon="sym_o_content_copy"
              :title="t('Copy')"
              @click="copy(oneTime.secret)"
            />
            <q-btn
              flat
              round
              dense
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
          />
          <q-input
            v-model="form.purpose"
            outlined
            dense
            :label="t('Purpose')"
          />
          <q-input
            v-model="form.ownerUserId"
            outlined
            dense
            :label="t('Owner user ID')"
          />
          <q-input
            v-model="form.folderRootId"
            outlined
            dense
            :label="t('Folder root (optional)')"
          />
          <q-input
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
          </q-item>
          <q-item v-else-if="isAdmin && !principals.length">
            <q-item-section>{{ t('No service principals') }}</q-item-section>
          </q-item>
          <q-item
            v-for="principal in principals"
            :key="principal.id"
          >
            <q-item-section>
              <q-item-label>{{ principal.displayName }}</q-item-label>
              <q-item-label caption>
                {{ principal.purpose }} · {{ principal.state }} · {{ formatTime(principal.expiresAt) }}
              </q-item-label>
              <q-item-label caption>
                {{ principal.scopes.map(scopeLabel).join(' · ') }}<span v-if="principal.folderRootId"> · {{ t('Folder-scoped') }}</span>
              </q-item-label>
              <div
                v-for="credential in credentials[principal.id] ?? []"
                :key="credential.id"
                class="credential-row"
              >
                <span class="mono">{{ credential.secretPrefix }}...</span>
                <span class="connectors-credential-time">{{ formatTime(credential.expiresAt) }}</span>
                <q-btn
                  v-if="!credential.revokedAt"
                  flat
                  round
                  dense
                  color="negative"
                  icon="sym_o_key_off"
                  :title="t('Revoke credential')"
                  @click="revokeCredential(principal.id, credential.credentialId)"
                />
              </div>
            </q-item-section>
            <q-item-section
              v-if="isAdmin"
              side
            >
              <div>
                <q-btn
                  v-if="activeCredential(principal.id)"
                  flat
                  round
                  dense
                  icon="sym_o_refresh"
                  :title="t('Rotate')"
                  @click="rotateFirstCredential(principal)"
                />
                <q-btn
                  flat
                  round
                  dense
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
    </q-page>
    <q-page
      v-else
      flex
      flex-center
      text-on-sur-var
    >
      <q-spinner
        v-if="!listReady"
        color="primary"
        size="40px"
      />
      <div
        v-else
        class="tk-empty"
        data-testid="connectors-onboarding"
      >
        <q-icon
          name="sym_o_link"
          size="56px"
          class="tk-empty-icon"
        />
        <div class="tk-empty-title">
          {{ t('Connectors live in a workspace') }}
        </div>
        <div class="tk-empty-subtitle">
          {{ t('Create a workspace, or join one with an invitation, to manage agent access.') }}
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            :label="t('Create Workspace')"
            data-testid="connectors-create-workspace"
            @click="showCreateWorkspace = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            :label="t('Join workspace')"
            data-testid="connectors-join-workspace"
            @click="joinWorkspace"
          />
        </div>
      </div>
    </q-page>
  </q-page-container>
  <create-workspace-dialog v-model="showCreateWorkspace" />
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { copyToClipboard, useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import CreateWorkspaceDialog from 'src/components/CreateWorkspaceDialog.vue'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type ServicePrincipal = components['schemas']['ServicePrincipalResponse']
type CredentialIssue = components['schemas']['CredentialIssueResponse']
type ServicePrincipalCreate = components['schemas']['ServicePrincipalCreate']
type ConnectedGrant = components['schemas']['ConnectedGrantResponse']
type Credential = components['schemas']['CredentialViewResponse']

const scopeOptions = [
  'mcp:workspaces:read',
  'mcp:knowledge:read',
  'mcp:knowledge:search',
]
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()
const $q = useQuasar()
const router = useRouter()
const showCreateWorkspace = ref(false)
const listReady = computed(() => workspaceStore.workspacesStatus === 'success')

function joinWorkspace() {
  $q.dialog({
    title: t('Join Workspace'),
    prompt: {
      model: '',
      label: t('Invitation Link'),
    },
    cancel: true,
  }).onOk((link: string) => {
    const token = link.match(/\/invitations\/(.+)/)?.[1]
    token && router.push(`/invitations/${token}`)
  })
}

const principals = ref<ServicePrincipal[]>([])
const grants = ref<ConnectedGrant[]>([])
const credentials = ref<Record<string, Credential[]>>({})
const oneTime = ref<CredentialIssue | null>(null)
const role = ref('')
const loading = ref(false)
const creating = ref(false)
const error = ref('')
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
    error.value = workspace.error || connected.error
      ? apiErrorMessage(workspace.error ?? connected.error, 'Agent access is unavailable.')
      : ''
    principals.value = []
    credentials.value = {}
    if (role.value !== 'workspace_admin') return

    const list = await identityClient.listServicePrincipals(workspaceId)
    if (generation !== loadGeneration) return
    principals.value = list.data ?? []
    error.value = list.error ? apiErrorMessage(list.error, 'Agent access is unavailable.') : error.value
    if (list.error) return
    const details = await Promise.all(
      principals.value.map(principal => identityClient.getServicePrincipal(workspaceId, principal.id)),
    )
    if (generation !== loadGeneration) return
    credentials.value = Object.fromEntries(
      details.flatMap(detail => detail.data ? [[detail.data.id, detail.data.credentials]] : []),
    )
    const detailError = details.find(detail => detail.error)?.error
    error.value = detailError ? apiErrorMessage(detailError, 'Agent access is unavailable.') : error.value
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
      error.value = apiErrorMessage(result.error, 'Could not create service principal')
    }
  } finally {
    creating.value = false
  }
}

async function revokePrincipal(id: string) {
  const workspaceId = workspaceStore.id
  if (!workspaceId) return
  const result = await identityClient.revokeServicePrincipal(workspaceId, id)
  if (result.error) error.value = apiErrorMessage(result.error, 'Could not revoke service principal')
  else await load()
}

async function revokeGrant(id: string) {
  const result = await identityClient.revokeConnectedOAuthGrant(id)
  if (result.error) error.value = apiErrorMessage(result.error, 'Could not revoke connection')
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
  else error.value = apiErrorMessage(result.error, 'Could not rotate credential')
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
  if (result.error) error.value = apiErrorMessage(result.error, 'Could not revoke credential')
  else await load()
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
  load().catch(() => undefined)
})
onMounted(() => { load().catch(() => undefined) })
onBeforeUnmount(() => { oneTime.value = null })
</script>

<style scoped>
.connectors-page {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-4);
}

.connectors-card-head {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.connectors-banner {
  margin: var(--tk-space-2) var(--tk-space-4) 0;
  background-color: var(--tk-danger-soft);
  color: var(--tk-danger);
}

.connectors-secret {
  margin: var(--tk-space-2) var(--tk-space-4) 0;
  background-color: var(--tk-accent-soft);
  color: var(--tk-text);
}

.connectors-secret strong,
.connectors-secret code {
  display: block;
  margin-bottom: var(--tk-space-1);
}

.mono,
code {
  font-family: ui-monospace, monospace;
  overflow-wrap: anywhere;
}

.create-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--tk-space-3);
  padding: var(--tk-space-4) var(--tk-space-4) 0;
}

.scopes {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: var(--tk-space-1) 14px;
}

.credential-row {
  display: grid;
  grid-template-columns: minmax(100px, 1fr) minmax(140px, auto) 40px;
  align-items: center;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-2);
}

.connectors-credential-time {
  color: var(--tk-text-secondary);
  font-size: 13px;
}

@media (max-width: 640px) {
  .create-grid {
    grid-template-columns: 1fr;
  }

  .scopes {
    grid-column: auto;
    flex-direction: column;
  }

  .credential-row {
    grid-template-columns: 1fr 40px;
  }

  .credential-row span:nth-child(2) {
    grid-column: 1;
  }
}
</style>
