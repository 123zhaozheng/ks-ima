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
      <q-toolbar-title>连接器</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page class="tk-page connectors-page">
      <section class="tk-card connectors-card">
        <header class="connectors-card-head">
          <q-icon
            name="sym_o_link"
            size="22px"
            color="primary"
          />
          <div>
            <h1 class="tk-card-title">
              智能体访问
            </h1>
            <p class="tk-card-subtitle">
              交互式连接
            </p>
          </div>
        </header>
        <q-list separator>
          <q-item>
            <q-item-section>
              <q-item-label>MCP 资源</q-item-label>
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
                title="复制"
                @click="copy(mcpUrl)"
              />
            </q-item-section>
          </q-item>
          <q-item>
            <q-item-section>
              <q-item-label caption>
                连接绑定到你的账户，可访问你有权限的全部知识库。
              </q-item-label>
            </q-item-section>
          </q-item>
          <q-item v-if="!grants.length">
            <q-item-section>
              <q-item-label>已连接的智能体</q-item-label>
              <q-item-label caption>
                没有可用的交互式授权。
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
                title="撤销"
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
              服务访问
            </h2>
            <p class="tk-card-subtitle">
              无人值守智能体
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
          <strong>一次性凭据</strong>
          <code class="mono">{{ oneTime.secret }}</code>
          <template #action>
            <q-btn
              flat
              round
              dense
              icon="sym_o_content_copy"
              title="复制"
              @click="copy(oneTime.secret)"
            />
            <q-btn
              flat
              round
              dense
              icon="sym_o_close"
              title="不再提示"
              @click="oneTime = null"
            />
          </template>
        </q-banner>
        <div class="create-grid">
          <q-input
            v-model="form.displayName"
            outlined
            dense
            label="名称"
          />
          <q-input
            v-model="form.purpose"
            outlined
            dense
            label="用途"
          />
          <q-input
            v-model.number="form.expiresDays"
            outlined
            dense
            type="number"
            min="1"
            max="90"
            label="有效天数"
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
            label="创建服务主体"
            :loading="creating"
            @click="createPrincipal"
          />
        </div>
        <q-list separator>
          <q-item v-if="loading">
            <q-item-section>正在加载服务访问…</q-item-section>
          </q-item>
          <q-item v-else-if="!principals.length">
            <q-item-section>暂无服务主体</q-item-section>
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
                {{ principal.scopes.map(scopeLabel).join(' · ') }}
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
                  title="撤销凭据"
                  @click="revokeCredential(principal.id, credential.credentialId)"
                />
              </div>
            </q-item-section>
            <q-item-section side>
              <div>
                <q-btn
                  v-if="activeCredential(principal.id)"
                  flat
                  round
                  dense
                  icon="sym_o_refresh"
                  title="轮换"
                  @click="rotateFirstCredential(principal)"
                />
                <q-btn
                  flat
                  round
                  dense
                  color="negative"
                  icon="sym_o_delete"
                  title="撤销"
                  @click="revokePrincipal(principal.id)"
                />
              </div>
            </q-item-section>
          </q-item>
        </q-list>
      </section>
      <section
        v-if="showJoin"
        class="tk-card connectors-card"
        data-testid="connectors-join-kb"
      >
        <header class="connectors-card-head">
          <q-icon
            name="sym_o_group_add"
            size="22px"
            color="primary"
          />
          <div>
            <h2 class="tk-card-title">
              加入知识库
            </h2>
            <p class="tk-card-subtitle">
              粘贴分享链接即可加入知识库。
            </p>
          </div>
        </header>
        <div class="join-row">
          <q-input
            v-model="shareLink"
            outlined
            dense
            placeholder="分享链接"
          />
          <q-btn
            unelevated
            no-caps
            color="primary"
            label="加入"
            :disable="!shareLink.trim()"
            @click="joinKnowledgeBase"
          />
        </div>
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { copyToClipboard, useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { useKbStore } from 'src/stores/knowledge-base'
import { useUiStateStore } from 'src/stores/ui-state'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient, session } from 'src/utils/identity-client'
import { mcpHttpUrl } from 'src/utils/mcp-config'

type ServicePrincipal = components['schemas']['ServicePrincipalResponse']
type CredentialIssue = components['schemas']['CredentialIssueResponse']
type ServicePrincipalCreate = components['schemas']['ServicePrincipalCreate']
type ConnectedGrant = components['schemas']['ConnectedGrantResponse']
type Credential = components['schemas']['CredentialViewResponse']

const scopeOptions = [
  'mcp:knowledge-bases:read',
  'mcp:knowledge:read',
  'mcp:knowledge:search',
  'mcp:knowledge:write',
]
const kbStore = useKbStore()
const uiStateStore = useUiStateStore()
const $q = useQuasar()
const router = useRouter()

const principals = ref<ServicePrincipal[]>([])
const grants = ref<ConnectedGrant[]>([])
const credentials = ref<Record<string, Credential[]>>({})
const oneTime = ref<CredentialIssue | null>(null)
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const shareLink = ref('')
const mcpUrl = mcpHttpUrl()
// Service principals are user-level: they belong to their creator and can
// reach every knowledge base the creator is a member of, so every signed-in
// user manages their own without per-library or folder scoping.
const showJoin = computed(() => kbStore.kbsStatus === 'success' && (kbStore.kbs?.length ?? 0) === 0)
const form = reactive({
  displayName: '',
  purpose: '',
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
  if (!session.value.data?.user.id) return
  const generation = ++loadGeneration
  loading.value = true
  error.value = ''
  try {
    const [connected, list] = await Promise.all([
      identityClient.listConnectedOAuthGrants(),
      identityClient.listServicePrincipals(),
    ])
    if (generation !== loadGeneration) return
    grants.value = connected.data ?? []
    principals.value = list.data ?? []
    credentials.value = {}
    error.value = connected.error || list.error
      ? apiErrorMessage(connected.error ?? list.error, '无法获取智能体访问信息。')
      : ''
    if (list.error) return
    const details = await Promise.all(
      principals.value.map(principal => identityClient.getServicePrincipal(principal.id)),
    )
    if (generation !== loadGeneration) return
    credentials.value = Object.fromEntries(
      details.flatMap(detail => detail.data ? [[detail.data.id, detail.data.credentials]] : []),
    )
    const detailError = details.find(detail => detail.error)?.error
    error.value = detailError ? apiErrorMessage(detailError, '无法获取智能体访问信息。') : error.value
  } catch {
    if (generation === loadGeneration) error.value = '无法获取智能体访问信息。'
  } finally {
    if (generation === loadGeneration) loading.value = false
  }
}

async function createPrincipal() {
  const ownerId = session.value.data?.user.id
  if (!ownerId || creating.value) return
  error.value = ''
  oneTime.value = null
  if (!form.displayName.trim() || !form.purpose.trim() || !form.scopes.length) {
    error.value = '请填写必需的服务访问字段。'
    return
  }
  creating.value = true
  const expiresDays = Math.min(90, Math.max(1, Number(form.expiresDays) || 1))
  const payload = {
    displayName: form.displayName.trim(),
    purpose: form.purpose.trim(),
    ownerUserId: ownerId,
    scopes: form.scopes,
    expiresAt: new Date(Date.now() + expiresDays * 86400000).toISOString(),
    rateLimit: 300,
    concurrencyLimit: 10,
    cidrAllowlist: [],
  } satisfies ServicePrincipalCreate
  try {
    const result = await identityClient.createServicePrincipal(payload)
    if (result.data) {
      oneTime.value = result.data
      form.displayName = ''
      form.purpose = ''
      await load()
    } else {
      error.value = apiErrorMessage(result.error, '无法创建服务主体')
    }
  } finally {
    creating.value = false
  }
}

async function revokePrincipal(id: string) {
  const result = await identityClient.revokeServicePrincipal(id)
  if (result.error) error.value = apiErrorMessage(result.error, '无法撤销服务主体')
  else await load()
}

async function revokeGrant(id: string) {
  const result = await identityClient.revokeConnectedOAuthGrant(id)
  if (result.error) error.value = apiErrorMessage(result.error, '无法撤销连接')
  else await load()
}

async function rotateFirstCredential(principal: ServicePrincipal) {
  const credential = activeCredential(principal.id)
  if (!credential) return
  oneTime.value = null
  const result = await identityClient.rotateServiceCredential(
    principal.id,
    credential.credentialId,
    { expiresAt: principal.expiresAt, overlapExpiresAt: null },
  )
  if (result.data) oneTime.value = result.data
  else error.value = apiErrorMessage(result.error, '无法轮换凭据')
  await load()
}

async function revokeCredential(principalId: string, credentialId: string) {
  const result = await identityClient.revokeServiceCredential(principalId, credentialId)
  if (result.error) error.value = apiErrorMessage(result.error, '无法撤销凭据')
  else await load()
}

function joinKnowledgeBase() {
  const token = shareLink.value.match(/\/join\/([^/?#]+)/)?.[1] ?? shareLink.value.trim().match(/^([^/?#\s]+)$/)?.[1]
  if (!token) {
    error.value = '这看起来不是知识库分享链接。'
    return
  }
  router.push(`/join/${encodeURIComponent(token)}`)
}

async function copy(value: string) {
  await copyToClipboard(value)
  $q.notify({ message: '已复制', type: 'positive' })
}

watch(
  () => session.value.data?.user.id,
  (userId, previous) => {
    if (!userId || userId === previous) return
    loadGeneration += 1
    oneTime.value = null
    principals.value = []
    credentials.value = {}
    grants.value = []
    load().catch(() => undefined)
  },
  { immediate: true },
)
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

.join-row {
  display: flex;
  gap: var(--tk-space-3);
  align-items: center;
  padding: var(--tk-space-2) var(--tk-space-4) var(--tk-space-4);
}

.join-row .q-input {
  flex: 1;
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

  .join-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
