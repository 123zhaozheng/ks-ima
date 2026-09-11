<template>
  <div>
    <div class="page-subtitle q-mb-md">
      查看平台上的重要操作记录：登录、知识库变更、模型配置等
    </div>

    <div class="admin-toolbar">
      <q-select
        v-model="groupFilter"
        outlined
        dense
        emit-value
        map-options
        label="操作类型"
        :options="groupOptions"
      />
      <q-select
        v-model="resultFilter"
        outlined
        dense
        emit-value
        map-options
        label="结果"
        :options="resultOptions"
      />
      <q-btn
        class="tk-btn-ghost"
        flat
        no-caps
        icon="sym_o_refresh"
        label="刷新"
        :loading="loading"
        ml-a
        @click="load"
      />
    </div>

    <q-table
      flat
      bordered
      separator="horizontal"
      class="audit-table"
      :rows="filteredRows"
      :columns="columns"
      row-key="id"
      :loading="loading"
      :rows-per-page-options="[20, 50, 100]"
      :rows-per-page-label="'每页条数'"
      mt-4
    >
      <template #body-cell-createdAt="props">
        <q-td :props="props">
          <span :title="absoluteTime(props.row.createdAt)">{{ relativeTime(props.row.createdAt) }}</span>
        </q-td>
      </template>
      <template #body-cell-actor="props">
        <q-td
          :props="props"
          class="cell-muted"
        >
          {{ props.row.actorId || '系统' }}
        </q-td>
      </template>
      <template #body-cell-action="props">
        <q-td :props="props">
          <div>{{ actionLabel(props.row.action) }}</div>
          <div class="tk-caption">
            {{ props.row.action }}
          </div>
        </q-td>
      </template>
      <template #body-cell-target="props">
        <q-td
          :props="props"
          class="cell-muted"
        >
          <template v-if="props.row.targetId">
            {{ targetTypeLabel(props.row.targetType) }}
            <span class="tk-caption">{{ props.row.targetId }}</span>
          </template>
          <span
            v-else
            class="tk-caption"
          >—</span>
        </q-td>
      </template>
      <template #body-cell-result="props">
        <q-td :props="props">
          <q-badge
            outline
            :color="resultColor(props.row.result)"
          >
            {{ resultLabel(props.row.result) }}
          </q-badge>
          <div
            v-if="props.row.reasonCode"
            class="tk-caption q-mt-xs"
          >
            {{ reasonLabel(props.row.reasonCode) }}
          </div>
        </q-td>
      </template>
      <template #no-data>
        <pane-empty-state
          icon="sym_o_history"
          title="暂无审计记录"
        />
      </template>
    </q-table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import type { components } from 'src/api/generated/schema'
import { identityClient } from 'src/utils/identity-client'
import PaneEmptyState from 'src/components/PaneEmptyState.vue'

type AuditEvent = components['schemas']['AuditEvent']

type ActionGroup = '权限' | '知识库' | '模型' | '账户' | 'MCP' | '认证'

/** 后端 _audit / append_audit 写入的全部 action 码（含兜底） */
const AUDIT_ACTIONS: Record<string, { label: string, group: ActionGroup }> = {
  // 认证
  'auth.sign_in': { label: '登录', group: '认证' },
  'auth.password_changed': { label: '修改密码', group: '认证' },
  'auth.password_verified': { label: '密码核验', group: '认证' },
  'auth.password_reset': { label: '完成密码重置', group: '认证' },
  'auth.password_reset_delivery': { label: '发送密码重置邮件', group: '认证' },
  'auth.invite_delivery': { label: '发送邀请邮件', group: '认证' },
  'auth.invite_accepted': { label: '接受邀请', group: '认证' },
  'auth.profile_updated': { label: '更新个人资料', group: '认证' },
  'auth.session_revoked': { label: '退出登录', group: '认证' },
  'auth.totp_enabled': { label: '启用两步验证', group: '认证' },
  'auth.totp_disabled': { label: '关闭两步验证', group: '认证' },
  // 账户
  'user.created': { label: '创建用户', group: '账户' },
  'user.updated': { label: '更新用户', group: '账户' },
  'user.disabled': { label: '停用用户', group: '账户' },
  'user.restored': { label: '恢复用户', group: '账户' },
  'user.deleted': { label: '删除用户', group: '账户' },
  'user.sessions_revoked': { label: '强制用户下线', group: '账户' },
  'user.password_reset': { label: '重置用户密码', group: '账户' },
  'user.totp_reset': { label: '重置用户两步验证', group: '账户' },
  'role.granted': { label: '授予平台角色', group: '账户' },
  'role.revoked': { label: '撤销平台角色', group: '账户' },
  'settings.updated': { label: '更新平台设置', group: '账户' },
  // 知识库
  'kb.created': { label: '创建知识库', group: '知识库' },
  'kb.renamed': { label: '重命名知识库', group: '知识库' },
  'kb.archived': { label: '归档知识库', group: '知识库' },
  'kb.restored': { label: '恢复知识库', group: '知识库' },
  'kb.deleted': { label: '删除知识库', group: '知识库' },
  'kb.member.updated': { label: '调整成员角色', group: '知识库' },
  'kb.member.removed': { label: '移除成员', group: '知识库' },
  'kb.member.left': { label: '退出知识库', group: '知识库' },
  'kb.folder.created': { label: '新建文件夹', group: '知识库' },
  'kb.folder.renamed': { label: '重命名文件夹', group: '知识库' },
  'kb.folder.moved': { label: '移动文件夹', group: '知识库' },
  'kb.folder.reordered': { label: '调整文件夹排序', group: '知识库' },
  'kb.folder.deleted': { label: '删除文件夹', group: '知识库' },
  'kb.share_link.created': { label: '创建分享链接', group: '知识库' },
  'kb.share_link.revoked': { label: '撤销分享链接', group: '知识库' },
  'kb.share_link.accepted': { label: '通过分享链接加入', group: '知识库' },
  // 权限（访问策略与第三方授权）
  'kb.authorization.denied': { label: '知识库访问被拒绝', group: '权限' },
  'oauth.client.registered': { label: '注册 OAuth 客户端', group: '权限' },
  'oauth.code.issued': { label: '签发授权码', group: '权限' },
  'oauth.code.exchanged': { label: '交换授权码', group: '权限' },
  'oauth.access_token.issued': { label: '签发访问令牌', group: '权限' },
  'oauth.grant.approved': { label: '批准授权', group: '权限' },
  'oauth.grant.revoked': { label: '撤销授权', group: '权限' },
  'oauth.grant.revoked_all': { label: '撤销全部授权', group: '权限' },
  'oauth.refresh_token.issued': { label: '签发刷新令牌', group: '权限' },
  'oauth.refresh_token.rotated': { label: '轮换刷新令牌', group: '权限' },
  'oauth.refresh_token.replay': { label: '检测到刷新令牌重放', group: '权限' },
  'oauth.consent.denied': { label: '拒绝授权同意', group: '权限' },
  // 模型
  'model.gateway.created': { label: '添加服务商', group: '模型' },
  'model.gateway.updated': { label: '更新服务商', group: '模型' },
  'model.gateway.deleted': { label: '删除服务商', group: '模型' },
  'model.gateway.enabled': { label: '启用服务商', group: '模型' },
  'model.gateway.disabled': { label: '停用服务商', group: '模型' },
  'model.gateway.secret_rotated': { label: '轮换服务商密钥', group: '模型' },
  'model.gateway.health_checked': { label: '服务商健康检查', group: '模型' },
  'model.registry.created': { label: '添加模型', group: '模型' },
  'model.registry.updated': { label: '更新模型', group: '模型' },
  'model.registry.deleted': { label: '删除模型', group: '模型' },
  'model.registry.validated': { label: '验证模型', group: '模型' },
  'model.registry.enabled': { label: '启用模型', group: '模型' },
  'model.registry.disabled': { label: '停用模型', group: '模型' },
  'model.profile.created': { label: '创建场景配置', group: '模型' },
  'model.profile.draft_updated': { label: '更新场景草稿', group: '模型' },
  'model.profile.published': { label: '发布场景配置', group: '模型' },
  'model.profile.validated': { label: '验证场景配置', group: '模型' },
  'model.profile.disabled': { label: '停用场景配置', group: '模型' },
  'model.profile.restored': { label: '恢复场景配置', group: '模型' },
  'model.profile.deleted': { label: '删除场景配置', group: '模型' },
  'model.profile.cloned': { label: '克隆场景配置', group: '模型' },
  'model.execution.denied': { label: '模型调用被拒绝', group: '模型' },
  // MCP
  'mcp.service_principal.created': { label: '创建 MCP 服务主体', group: 'MCP' },
  'mcp.credential.issued': { label: '签发 MCP 凭据', group: 'MCP' },
  'mcp.credential.rotated': { label: '轮换 MCP 凭据', group: 'MCP' },
  'mcp.credential.revoked': { label: '撤销 MCP 凭据', group: 'MCP' },
  'mcp.credential.exchanged': { label: '交换 MCP 凭据', group: 'MCP' },
  'mcp.tool.allowed': { label: '允许调用 MCP 工具', group: 'MCP' },
  'mcp.tool.denied': { label: '拒绝调用 MCP 工具', group: 'MCP' },
  'mcp.network.denied': { label: '拒绝 MCP 网络访问', group: 'MCP' },
  'mcp.concurrency.denied': { label: '拒绝 MCP 并发调用', group: 'MCP' },
  'legacy.mcp.alias_used': { label: '使用旧版 MCP 别名', group: 'MCP' },
}

/** reason 码中文（PolicyReason、身份原因、模型治理原因、网关探测原因） */
const REASONS: Record<string, string> = {
  allowed: '允许',
  inactive_actor: '操作者已停用',
  inactive_knowledge_base: '知识库已停用',
  missing_membership: '不是知识库成员',
  insufficient_role: '权限不足',
  root_protected: '根目录受保护',
  last_owner: '不能移除最后一位所有者',
  version_conflict: '版本冲突',
  smtp_delivery_failed: '邮件发送失败',
  rate_limited: '请求过于频繁',
  invalid_or_expired: '无效或已过期',
  INVALID_PROFILE_CONFIG: '配置格式无效',
  MODEL_UNAVAILABLE: '关联模型不可用',
  WORKFLOW_OPERATION_MISMATCH: '场景与操作不匹配',
  NO_ASSIGNMENT: '尚未分配',
  UNAVAILABLE: '不可用',
  DIMENSION_MISMATCH: '向量维度不匹配',
  TIMEOUT: '超时',
  NETWORK_ERROR: '网络错误',
  UPSTREAM_HTTP_ERROR: '上游服务返回错误',
  INVALID_RESPONSE: '响应格式无效',
  RESPONSE_TOO_LARGE: '响应过大',
  INVALID_BASE_URL: '地址无效',
  INSECURE_GATEWAY: '未允许内网 HTTP 地址',
  DNS_FAILURE: '域名解析失败',
  DNS_EMPTY: '域名解析为空',
  HOST_NOT_ALLOWLISTED: '域名不在白名单',
  PRIVATE_ADDRESS_REJECTED: '内网地址被拒绝',
  ADDRESS_NOT_ALLOWLISTED: '地址不在白名单',
  PUBLIC_ADDRESS_REJECTED: '公网地址被拒绝',
  REDIRECT_REJECTED: '重定向被拒绝',
  INVALID_ALLOWLIST: '白名单配置无效',
  CUSTOM_CA_UNAVAILABLE: '自定义证书不可用',
  UNKNOWN_CAPABILITY: '未知能力',
  INVALID_MODELS_RESPONSE: '模型列表响应无效',
  INVALID_CHAT_RESPONSE: '对话响应无效',
  INVALID_EMBEDDING_RESPONSE: '向量化响应无效',
}

const RESULTS: Record<string, string> = {
  success: '成功',
  failure: '失败',
  failed: '失败',
  challenge: '待验证',
}

const TARGET_TYPES: Record<string, string> = {
  user: '用户',
  knowledge_base: '知识库',
  kb: '知识库',
  kb_member: '成员',
  folder: '文件夹',
  share_link: '分享链接',
  model_gateway: '服务商',
  governed_model: '模型',
  capability_profile: '场景配置',
  session: '会话',
  platform_settings: '平台设置',
  oauth_client: 'OAuth 客户端',
  oauth_grant: 'OAuth 授权',
  service_principal: '服务主体',
  credential: '凭据',
}

const rows = ref<AuditEvent[]>([])
const loading = ref(true)
const groupFilter = ref('')
const resultFilter = ref('')

const columns: QTableColumn[] = [
  { name: 'createdAt', label: '时间', field: 'createdAt', align: 'left', sortable: true },
  { name: 'actor', label: '操作者', field: 'actorId', align: 'left' },
  { name: 'action', label: '动作', field: 'action', align: 'left' },
  { name: 'target', label: '对象', field: 'targetId', align: 'left' },
  { name: 'result', label: '结果', field: 'result', align: 'left' },
]

const groupOptions = computed(() => [
  { label: '全部类型', value: '' },
  ...(['权限', '知识库', '模型', '账户', 'MCP', '认证'] as ActionGroup[]).map(group => ({ label: group, value: group })),
])

const resultOptions = [
  { label: '全部结果', value: '' },
  { label: '成功', value: 'success' },
  { label: '失败', value: 'failure' },
]

const filteredRows = computed(() => rows.value.filter(row => {
  if (groupFilter.value && AUDIT_ACTIONS[row.action]?.group !== groupFilter.value) return false
  if (resultFilter.value === 'success') return row.result === 'success'
  if (resultFilter.value === 'failure') return row.result !== 'success'
  return true
}))

function actionLabel(action: string) {
  return AUDIT_ACTIONS[action]?.label ?? action
}
function reasonLabel(code: string) {
  return REASONS[code] ?? code
}
function resultLabel(result: string) {
  return RESULTS[result] ?? result
}
function resultColor(result: string) {
  return result === 'success' ? 'positive' : 'negative'
}
function targetTypeLabel(type: string | null | undefined) {
  if (!type) return ''
  return `${TARGET_TYPES[type] ?? type} `
}

function relativeTime(iso: string) {
  const time = new Date(iso).getTime()
  if (Number.isNaN(time)) return iso
  const diff = Date.now() - time
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  if (diff < 30 * 86_400_000) return `${Math.floor(diff / 86_400_000)} 天前`
  return new Date(iso).toLocaleDateString()
}
function absoluteTime(iso: string) {
  const time = new Date(iso)
  return Number.isNaN(time.getTime()) ? iso : time.toLocaleString()
}

async function load() {
  loading.value = true
  const result = await identityClient.listAudit()
  rows.value = result.data?.items ?? []
  loading.value = false
}
load()
</script>

<style scoped>
.page-subtitle {
  color: var(--tk-text-secondary);
  font-size: 13px;
}

.cell-muted {
  color: var(--tk-text-secondary);
}
</style>
