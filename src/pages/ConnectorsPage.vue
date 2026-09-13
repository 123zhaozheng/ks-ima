<template>
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
      <section
        class="tk-card connectors-card"
        data-testid="connectors-mcp-config"
      >
        <header class="connectors-card-head">
          <q-icon
            name="sym_o_key"
            size="22px"
            color="primary"
          />
          <div>
            <h2 class="tk-card-title">
              MCP 配置
            </h2>
            <p class="tk-card-subtitle">
              一键生成，粘贴到 Cursor / Claude Desktop 即可连接
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
        <template v-if="issued">
          <q-banner
            rounded
            class="connectors-hint"
          >
            密钥有效期 90 天，仅此一次完整显示，请立即复制并妥善保管。
          </q-banner>
          <q-btn-toggle
            v-model="clientKind"
            class="connectors-toggle"
            dense
            no-caps
            unelevated
            toggle-color="primary"
            :options="[
              { label: 'Cursor / HTTP', value: 'cursor' },
              { label: 'Claude Desktop', value: 'claude' },
            ]"
          />
          <pre class="connectors-config"><code data-testid="connectors-config-json">{{ configJson }}</code></pre>
          <div class="connectors-actions">
            <q-btn
              unelevated
              no-caps
              color="primary"
              icon="sym_o_content_copy"
              label="复制配置"
              @click="copyConfig"
            />
          </div>
        </template>
        <div
          v-else
          class="connectors-actions"
        >
          <q-btn
            unelevated
            no-caps
            color="primary"
            icon="sym_o_key"
            label="获取 MCP 配置"
            :loading="creating"
            data-testid="connectors-generate"
            @click="generateConfig"
          />
        </div>
        <q-list separator>
          <q-item v-if="loading">
            <q-item-section>正在加载 MCP 配置…</q-item-section>
          </q-item>
          <q-item v-else-if="!keys.length">
            <q-item-section>暂无已生成的密钥</q-item-section>
          </q-item>
          <q-item
            v-for="key in keys"
            :key="key.credentialId"
          >
            <q-item-section>
              <q-item-label>{{ key.displayName }}</q-item-label>
              <q-item-label caption>
                <span class="mono">{{ key.secretPrefix }}…</span> · {{ formatTime(key.expiresAt) }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                round
                dense
                color="negative"
                icon="sym_o_delete"
                title="撤销"
                @click="revokeKey(key.principalId)"
              />
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
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { copyToClipboard, useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { useRecentAuth } from 'src/composables/recent-auth'
import { useRequireLogin } from 'src/composables/require-login'
import { useKbStore } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient, session } from 'src/utils/identity-client'
import { mcpHttpUrl, cursorMcpConfig, claudeDesktopMcpConfig, prettyJson } from 'src/utils/mcp-config'

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
const $q = useQuasar()
const router = useRouter()
useRequireLogin()
const { withRecentAuth } = useRecentAuth()

const principals = ref<ServicePrincipal[]>([])
const grants = ref<ConnectedGrant[]>([])
const credentials = ref<Record<string, Credential[]>>({})
const issued = ref<CredentialIssue | null>(null)
const clientKind = ref<'cursor' | 'claude'>('cursor')
const loading = ref(false)
const creating = ref(false)
const error = ref('')
const shareLink = ref('')
const mcpUrl = mcpHttpUrl()
// Service principals are user-level: they belong to their creator and can
// reach every knowledge base the creator is a member of, so every signed-in
// user manages their own without per-library or folder scoping.
const showJoin = computed(() => kbStore.kbsStatus === 'success' && (kbStore.kbs?.length ?? 0) === 0)
type KeyRow = {
  principalId: string
  displayName: string
  secretPrefix: string
  expiresAt: string
  credentialId: string
}

// Flat key list: one principal per generated key. Revoked or expired
// credentials and revoked principals disappear; only the prefix is known
// after a page refresh.
const keys = computed<KeyRow[]>(() => {
  const rows: KeyRow[] = []
  for (const principal of principals.value) {
    if (principal.state !== 'active') continue
    for (const credential of credentials.value[principal.id] ?? []) {
      if (credential.revokedAt) continue
      if (new Date(credential.expiresAt).getTime() <= Date.now()) continue
      rows.push({
        principalId: principal.id,
        displayName: principal.displayName,
        secretPrefix: credential.secretPrefix,
        expiresAt: credential.expiresAt,
        credentialId: credential.id,
      })
    }
  }
  return rows
})

const configJson = computed(() => {
  if (!issued.value) return ''
  const secret = issued.value.secret
  return clientKind.value === 'claude'
    ? prettyJson(claudeDesktopMcpConfig(secret))
    : prettyJson(cursorMcpConfig(secret))
})

let loadGeneration = 0

function scopeLabel(scope: string) {
  return scope.replace('mcp:', '').replaceAll(':', ' · ')
}

function formatTime(value: string) {
  return new Date(value).toLocaleString()
}

function localStamp() {
  const now = new Date()
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`
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

async function generateConfig() {
  const ownerId = session.value.data?.user.id
  if (!ownerId || creating.value) return
  error.value = ''
  creating.value = true
  // Fixed payload: the page decides every parameter, the user fills nothing.
  const payload = {
    displayName: `MCP 配置 ${localStamp()}`,
    purpose: '连接器页面一键生成',
    ownerUserId: ownerId,
    scopes: scopeOptions,
    expiresAt: new Date(Date.now() + 90 * 86400000).toISOString(),
    rateLimit: 300,
    concurrencyLimit: 10,
    cidrAllowlist: [],
  } satisfies ServicePrincipalCreate
  try {
    // Sensitive op: a recent-auth 401 asks for the password once and retries;
    // a dead session redirects to sign-in through the login watcher instead.
    const result = await withRecentAuth(() => identityClient.createServicePrincipal(payload))
    if (result.data) {
      issued.value = result.data
      await load()
    } else {
      error.value = apiErrorMessage(result.error, '无法生成 MCP 配置')
    }
  } finally {
    creating.value = false
  }
}

async function revokeKey(principalId: string) {
  const result = await identityClient.revokeServicePrincipal(principalId)
  if (result.error) error.value = apiErrorMessage(result.error, '无法撤销密钥')
  else await load()
}

async function revokeGrant(id: string) {
  const result = await identityClient.revokeConnectedOAuthGrant(id)
  if (result.error) error.value = apiErrorMessage(result.error, '无法撤销连接')
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

async function copyConfig() {
  await copyToClipboard(configJson.value)
  $q.notify({ message: '已复制', type: 'positive' })
}

watch(
  () => session.value.data?.user.id,
  (userId, previous) => {
    if (!userId || userId === previous) return
    loadGeneration += 1
    issued.value = null
    principals.value = []
    credentials.value = {}
    grants.value = []
    load().catch(() => undefined)
  },
  { immediate: true },
)
onBeforeUnmount(() => { issued.value = null })
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

.connectors-hint {
  margin: var(--tk-space-2) var(--tk-space-4) 0;
  background-color: var(--tk-accent-soft);
  color: var(--tk-text);
}

.mono,
code {
  font-family: ui-monospace, monospace;
  overflow-wrap: anywhere;
}

.connectors-toggle {
  margin: var(--tk-space-3) var(--tk-space-4) 0;
}

.connectors-config {
  margin: var(--tk-space-3) var(--tk-space-4) 0;
  padding: var(--tk-space-3);
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  background-color: var(--tk-surface-deep);
  overflow: auto;
  max-height: 320px;
}

.connectors-config code {
  white-space: pre;
}

.connectors-actions {
  display: flex;
  justify-content: flex-end;
  padding: var(--tk-space-2) var(--tk-space-4) 0;
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
  .join-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
