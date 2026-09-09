<template>
  <q-page-container>
    <q-page class="models-page q-pa-xl">
      <div class="q-mb-lg">
        <div class="text-h5 text-weight-medium">
          模型配置
        </div>
        <div class="page-subtitle q-mt-xs">
          集中管理系统使用的 AI 服务商与模型
        </div>
      </div>

      <q-banner
        v-if="error"
        class="bg-red-1 text-negative q-mb-md error-banner"
        rounded
      >
        {{ error }}
        <template #action>
          <q-btn
            flat
            no-caps
            label="重试"
            @click="refresh"
          />
        </template>
      </q-banner>

      <q-tabs
        v-model="tab"
        align="left"
        no-caps
        active-color="primary"
        indicator-color="primary"
        class="text-grey-8"
      >
        <q-tab
          name="services"
          label="模型服务"
        />
        <q-tab
          name="scenes"
          label="场景配置"
        />
      </q-tabs>
      <q-separator />

      <q-tab-panels
        v-model="tab"
        animated
        style="background: transparent"
      >
        <!-- Tab 1：模型服务 -->
        <q-tab-panel
          name="services"
          class="q-px-none"
        >
          <div class="row items-center justify-end q-mb-md q-gutter-sm">
            <q-btn
              flat
              dense
              no-caps
              icon="sym_o_refresh"
              label="刷新"
              :loading="loading"
              @click="refresh"
            />
            <q-btn
              v-if="canManage"
              color="primary"
              unelevated
              no-caps
              icon="sym_o_add"
              label="添加服务商"
              @click="openGatewayDialog(null)"
            />
          </div>

          <div
            v-if="gateways.length"
            class="row q-col-gutter-md"
          >
            <div
              v-for="gateway in gateways"
              :key="gateway.id"
              class="col-12 col-md-6 col-lg-4"
            >
              <q-card
                flat
                bordered
                class="surface-card q-pa-md full-height"
              >
                <div class="row items-center no-wrap">
                  <model-avatar
                    :model="gateway.baseUrl || gateway.name"
                    :size="32"
                  />
                  <div
                    class="q-ml-sm column"
                    style="min-width: 0"
                  >
                    <div class="text-subtitle1 text-weight-medium ellipsis">
                      {{ gateway.name }}
                    </div>
                    <div class="text-caption text-grey-7 ellipsis">
                      {{ maskedUrl(gateway.baseUrl) }}
                    </div>
                  </div>
                  <q-space />
                  <q-toggle
                    :model-value="gateway.enabled"
                    dense
                    :disable="!canManage"
                    @update:model-value="toggleGateway(gateway, $event)"
                  />
                </div>
                <div class="row items-center q-gutter-sm q-mt-md">
                  <q-btn
                    color="primary"
                    unelevated
                    dense
                    no-caps
                    label="拉取模型"
                    :disable="!canManage"
                    @click="openDiscover(gateway)"
                  />
                  <q-btn
                    flat
                    dense
                    no-caps
                    label="健康检查"
                    @click="health(gateway.id)"
                  />
                  <q-btn
                    flat
                    dense
                    no-caps
                    label="编辑"
                    :disable="!canManage"
                    @click="openGatewayDialog(gateway)"
                  />
                  <q-btn
                    flat
                    dense
                    no-caps
                    class="text-negative"
                    label="删除"
                    :disable="!canManage"
                    @click="deleteGateway(gateway)"
                  />
                </div>
              </q-card>
            </div>
          </div>
          <q-card
            v-else-if="!loading"
            flat
            bordered
            class="surface-card q-pa-xl text-center text-grey-7"
          >
            还没有接入任何服务商。点击右上角「添加服务商」，填写 OpenAI 兼容的地址和密钥即可接入。
          </q-card>

          <div class="text-subtitle1 text-weight-medium q-mt-xl q-mb-sm">
            模型清单
          </div>
          <div class="text-caption text-grey-7 q-mb-md">
            在服务商卡片上点「拉取模型」可以一键导入；模型验证通过后才能启用。
          </div>
          <q-table
            flat
            bordered
            separator="horizontal"
            class="surface-card"
            :rows="models"
            :columns="modelColumns"
            row-key="id"
            :loading="loading"
            no-data-label="还没有模型"
            :rows-per-page-options="[10, 20, 50]"
          >
            <template #body-cell-name="props">
              <q-td :props="props">
                <div class="row items-center no-wrap">
                  <model-avatar
                    :model="props.row.remoteName || props.row.businessLabel"
                    :size="24"
                  />
                  <span class="q-ml-sm">{{ props.row.businessLabel }}</span>
                </div>
              </q-td>
            </template>
            <template #body-cell-capability="props">
              <q-td :props="props">
                <q-badge
                  outline
                  :color="capabilityColor(props.row.capability)"
                >
                  {{ capabilityLabel(props.row.capability) }}
                </q-badge>
              </q-td>
            </template>
            <template #body-cell-remoteName="props">
              <q-td
                :props="props"
                class="text-grey-8"
              >
                {{ props.row.remoteName || '受限' }}
              </q-td>
            </template>
            <template #body-cell-status="props">
              <q-td :props="props">
                <q-badge
                  outline
                  :color="props.row.validated ? 'positive' : 'grey-7'"
                >
                  {{ props.row.validated ? '已验证' : '草稿' }}
                </q-badge>
              </q-td>
            </template>
            <template #body-cell-enabled="props">
              <q-td :props="props">
                <q-toggle
                  :model-value="props.row.enabled"
                  dense
                  :disable="!props.row.validated || !canManage"
                  @update:model-value="toggleModel(props.row, $event)"
                />
              </q-td>
            </template>
            <template #body-cell-actions="props">
              <q-td :props="props">
                <q-btn
                  flat
                  dense
                  no-caps
                  label="验证"
                  :disable="!canManage"
                  @click="validateModel(props.row)"
                />
                <q-btn
                  flat
                  dense
                  no-caps
                  class="text-negative"
                  label="删除"
                  :disable="!canManage"
                  @click="deleteModel(props.row)"
                />
              </q-td>
            </template>
          </q-table>
        </q-tab-panel>

        <!-- Tab 2：场景配置 -->
        <q-tab-panel
          name="scenes"
          class="q-px-none"
        >
          <div class="text-caption text-grey-7 q-mb-md">
            为每个场景选择要使用的模型。修改后点击「保存」即可生效。
          </div>
          <div class="row q-col-gutter-lg">
            <div
              v-for="scene in SCENES"
              :key="scene.id"
              class="col-12 col-xl-6"
            >
              <q-card
                flat
                bordered
                class="surface-card q-pa-lg full-height"
              >
                <div class="row items-start q-mb-md">
                  <div
                    class="column"
                    style="min-width: 0"
                  >
                    <div class="text-subtitle1 text-weight-medium">
                      {{ scene.name }}
                    </div>
                    <div class="text-caption text-grey-7 q-mt-xs">
                      {{ scene.desc }}
                    </div>
                  </div>
                  <q-space />
                </div>

                <div class="row q-col-gutter-sm">
                  <template v-if="scene.id === 'grounded_ask' || scene.id === 'title_generation' || scene.id === 'summarization'">
                    <div class="col-12">
                      <q-select
                        v-model="sceneState[scene.id].chatModelId"
                        outlined
                        dense
                        emit-value
                        map-options
                        clearable
                        label="对话模型"
                        :options="modelOptions('chat')"
                      />
                    </div>
                  </template>
                  <template v-else-if="scene.id === 'embedding'">
                    <div class="col-12">
                      <q-select
                        v-model="sceneState[scene.id].embeddingModelId"
                        outlined
                        dense
                        emit-value
                        map-options
                        clearable
                        label="向量模型"
                        :options="modelOptions('embedding')"
                      />
                    </div>
                  </template>
                  <template v-else>
                    <div class="col-12">
                      <q-select
                        v-model="sceneState[scene.id].rerankModelId"
                        outlined
                        dense
                        emit-value
                        map-options
                        clearable
                        label="重排序模型"
                        :options="modelOptions('rerank')"
                      />
                    </div>
                  </template>
                </div>

                <q-btn
                  v-if="canManage"
                  color="primary"
                  unelevated
                  no-caps
                  label="保存"
                  class="q-mt-md"
                  @click="saveSceneConfig(scene.id)"
                />
              </q-card>
            </div>
          </div>
        </q-tab-panel>

      </q-tab-panels>

      <!-- 添加/编辑服务商对话框 -->
      <q-dialog v-model="gatewayDialog.show">
        <q-card style="width: min(92vw, 560px)">
          <q-card-section>
            <div class="text-h6">
              {{ gatewayDialog.editId ? '编辑服务商' : '添加服务商' }}
            </div>
            <div class="text-caption text-grey-7 q-mt-xs">
              任何 OpenAI 兼容网关都可以接入，填写地址与密钥即可。
            </div>
          </q-card-section>
          <q-card-section class="q-pt-none q-gutter-y-md">
            <q-input
              v-model="gatewayForm.name"
              outlined
              dense
              label="名称"
              placeholder="如：DeepSeek"
            />
            <q-input
              v-model="gatewayForm.baseUrl"
              outlined
              dense
              label="API 地址"
              placeholder="如：https://api.deepseek.com/v1"
            />
            <q-input
              v-if="!gatewayDialog.editId"
              v-model="gatewayForm.secret"
              outlined
              dense
              type="password"
              label="API 密钥（仅显示一次）"
            />
            <div>
              <q-toggle
                v-model="gatewayForm.insecurePrivate"
                dense
                label="允许白名单内的内网 HTTP 地址"
              />
              <div class="text-caption text-grey-7 q-ml-xl">
                仅在使用 HTTP（未加密）的内网地址时需要开启，HTTPS 地址无需此选项。
              </div>
            </div>
          </q-card-section>
          <q-card-actions
            align="right"
            class="q-pa-md"
          >
            <q-btn
              flat
              no-caps
              label="取消"
              @click="gatewayDialog.show = false"
            />
            <q-btn
              color="primary"
              unelevated
              no-caps
              :loading="gatewayDialog.saving"
              :label="gatewayDialog.editId ? '保存' : '添加'"
              @click="saveGateway"
            />
          </q-card-actions>
        </q-card>
      </q-dialog>

      <!-- 拉取模型对话框 -->
      <q-dialog v-model="discoverDialog.show">
        <q-card style="width: min(92vw, 640px)">
          <q-card-section class="row items-center no-wrap">
            <div class="text-h6">
              拉取模型
            </div>
            <div
              v-if="discoverDialog.gateway"
              class="text-caption text-grey-7 q-ml-sm"
            >
              来自「{{ discoverDialog.gateway.name }}」
            </div>
          </q-card-section>
          <q-separator />
          <q-card-section
            v-if="discoverDialog.loading"
            class="row items-center q-gutter-sm text-grey-7"
          >
            <q-spinner
              size="20px"
              color="primary"
            />
            <span>正在拉取远端模型列表…</span>
          </q-card-section>
          <q-card-section
            v-else-if="discoverDialog.error"
            class="text-grey-7"
          >
            {{ discoverDialog.error }}
          </q-card-section>
          <q-card-section
            v-else
            class="scroll q-py-none"
            style="max-height: 56vh"
          >
            <q-list separator>
              <q-item
                v-for="item in discoverDialog.items"
                :key="item.name"
                dense
                class="q-px-sm"
                :class="{ 'discover-item-exists': item.exists }"
              >
                <q-item-section side>
                  <q-checkbox
                    v-model="item.selected"
                    dense
                    :disable="item.exists"
                  />
                </q-item-section>
                <q-item-section
                  avatar
                  class="q-pr-none"
                >
                  <model-avatar
                    :model="item.name"
                    :size="24"
                  />
                </q-item-section>
                <q-item-section>
                  <q-item-label class="text-body2">
                    {{ item.name }}
                    <q-badge
                      v-if="item.exists"
                      outline
                      color="grey-7"
                      class="q-ml-sm"
                    >
                      已导入
                    </q-badge>
                  </q-item-label>
                  <q-item-label caption>
                    <q-badge
                      outline
                      :color="capabilityColor(item.capability)"
                    >
                      {{ capabilityLabel(item.capability) }}
                    </q-badge>
                  </q-item-label>
                </q-item-section>
                <q-item-section
                  v-if="item.capability === 'embedding'"
                  side
                >
                  <q-input
                    v-model.number="item.dimension"
                    dense
                    outlined
                    type="number"
                    label="维度"
                    style="width: 110px"
                    :disable="item.exists"
                  />
                </q-item-section>
              </q-item>
            </q-list>
          </q-card-section>
          <q-separator />
          <q-card-actions
            align="right"
            class="q-pa-md"
          >
            <q-btn
              flat
              no-caps
              label="取消"
              @click="discoverDialog.show = false"
            />
            <q-btn
              color="primary"
              unelevated
              no-caps
              :loading="discoverDialog.importing"
              :disable="!selectedDiscoverCount"
              :label="`导入所选 (${selectedDiscoverCount})`"
              @click="importSelected"
            />
          </q-card-actions>
        </q-card>
      </q-dialog>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import type { QTableColumn } from 'quasar'
import type { components } from 'src/api/generated/schema'
import { identityClient, session } from 'src/utils/identity-client'
import { apiErrorCode, apiErrorMessage } from 'src/utils/api-error'
import ModelAvatar from '../components/ModelAvatar.vue'
import ReauthDialog from '../components/ReauthDialog.vue'
import VerifyTotpDialog from 'src/components/VerifyTotpDialog.vue'
import { CAPABILITY_LABELS, KNOWN_DIMENSIONS, guessCapability } from 'src/admin/model-catalog'
import type { Capability } from 'src/admin/model-catalog'

type Gateway = components['schemas']['ModelGateway']
type GovernedModel = components['schemas']['GovernedModel']
type Profile = components['schemas']['CapabilityProfile']
type KbInfo = components['schemas']['KnowledgeBaseInfo']
type Workflow = components['schemas']['ProfileCreateRequest']['workflow']

const SCENES: Array<{ id: Workflow, name: string, desc: string }> = [
  { id: 'grounded_ask', name: '知识库问答', desc: '用户在知识库提问时使用的对话与检索参数' },
  { id: 'title_generation', name: '标题生成', desc: '为每段对话自动生成简洁标题' },
  { id: 'summarization', name: '摘要', desc: '对长文本内容自动做摘要' },
  { id: 'embedding', name: '向量化', desc: '把文档转成向量；更换模型后可能需要重建索引' },
  { id: 'reranking', name: '重排序', desc: '对检索结果精排，让最相关的内容排在前面' },
]

const tab = ref('services')
const loading = ref(false)
const error = ref('')
const gateways = ref<Gateway[]>([])
const models = ref<GovernedModel[]>([])
const profiles = ref<Profile[]>([])
const kbs = ref<KbInfo[]>([])
const sceneState = ref<Record<Workflow, { chatModelId: string | null, embeddingModelId: string | null, rerankModelId: string | null }>>({
  grounded_ask: { chatModelId: null, embeddingModelId: null, rerankModelId: null },
  title_generation: { chatModelId: null, embeddingModelId: null, rerankModelId: null },
  summarization: { chatModelId: null, embeddingModelId: null, rerankModelId: null },
  embedding: { chatModelId: null, embeddingModelId: null, rerankModelId: null },
  reranking: { chatModelId: null, embeddingModelId: null, rerankModelId: null },
})

// ---------- 场景配置 ----------
function modelOptions(capability: Capability) {
  return models.value
    .filter(model => model.enabled && model.capability === capability)
    .map(model => ({ label: modelLabel(model), value: model.id }))
}
const canManage = computed(() => session.value.data?.user.platformRoles?.some(role => role === 'super_admin' || role === 'platform_admin') ?? false)
const $q = useQuasar()

const modelColumns: QTableColumn[] = [
  { name: 'name', label: '名称', field: 'businessLabel', align: 'left' },
  { name: 'capability', label: '能力', field: 'capability' },
  { name: 'remoteName', label: '远端名称', field: 'remoteName' },
  { name: 'status', label: '状态', field: 'validated' },
  { name: 'enabled', label: '启用', field: 'enabled' },
  { name: 'actions', label: '操作', field: 'id' },
]

function notify(message: string, color: 'positive' | 'negative' | 'warning' = 'positive') {
  $q.notify({ message, color })
}
function capabilityLabel(capability: string) {
  return CAPABILITY_LABELS[capability as Capability] ?? capability
}
function capabilityColor(capability: string) {
  if (capability === 'embedding') return 'teal'
  if (capability === 'rerank') return 'purple'
  return 'primary'
}
function maskedUrl(url: string | null | undefined) {
  if (!url) return '地址已隐藏'
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

// ---------- 敏感操作的近期认证 ----------
type MutationResult<T> = { data?: T, error?: { code?: string, message: string } }

function reauthenticate(): Promise<boolean> {
  return new Promise(resolve => {
    $q.dialog({ component: ReauthDialog, persistent: true })
      .onOk((challenge?: string) => {
        if (!challenge) {
          resolve(true)
          return
        }
        $q.dialog({ component: VerifyTotpDialog, componentProps: { challenge }, persistent: true })
          .onOk(() => resolve(true))
          .onCancel(() => resolve(false))
      })
      .onCancel(() => resolve(false))
  })
}

async function withRecentAuth<T>(action: () => Promise<MutationResult<T>>): Promise<MutationResult<T>> {
  let result = await action()
  if (result.error && apiErrorCode(result.error) === 'HTTP_401' && await reauthenticate()) {
    result = await action()
  }
  return result
}

// ---------- 服务商 ----------
const gatewayDialog = reactive({ show: false, editId: '', saving: false })
const gatewayForm = reactive({ name: '', baseUrl: '', secret: '', insecurePrivate: false })

watch(() => gatewayForm.baseUrl, url => {
  // HTTP 地址必须显式允许内网明文（后端对 HTTP 强制要求该开关）
  if (url.trim().startsWith('http://')) gatewayForm.insecurePrivate = true
})

function openGatewayDialog(gateway: Gateway | null) {
  gatewayDialog.editId = gateway?.id ?? ''
  Object.assign(gatewayForm, gateway
    ? { name: gateway.name, baseUrl: gateway.baseUrl ?? '', secret: '', insecurePrivate: gateway.insecurePrivate }
    : { name: '', baseUrl: '', secret: '', insecurePrivate: false })
  gatewayDialog.show = true
}

async function saveGateway() {
  if (!gatewayForm.name || !gatewayForm.baseUrl) {
    notify('请填写名称和 API 地址', 'warning')
    return
  }
  gatewayDialog.saving = true
  const editing = gateways.value.find(gateway => gateway.id === gatewayDialog.editId)
  let allowedHosts: string[] = []
  if (gatewayForm.insecurePrivate) {
    try {
      allowedHosts = [new URL(gatewayForm.baseUrl.trim()).hostname]
    } catch {
      allowedHosts = []
    }
  }
  const result = editing
    ? await withRecentAuth(() => identityClient.updateModelGateway(editing.id, { name: gatewayForm.name, baseUrl: gatewayForm.baseUrl, insecurePrivate: gatewayForm.insecurePrivate, expectedVersion: editing.version }))
    : await withRecentAuth(() => identityClient.createModelGateway({ name: gatewayForm.name, baseUrl: gatewayForm.baseUrl, allowedCapabilities: ['chat', 'embedding', 'rerank'], insecurePrivate: gatewayForm.insecurePrivate, allowedHosts, allowedCidrs: [], connectTimeoutMs: 5000, readTimeoutMs: 30000, writeTimeoutMs: 30000, poolTimeoutMs: 5000, maxResponseBytes: 8388608, secret: gatewayForm.secret || undefined }))
  gatewayDialog.saving = false
  if (result.error) {
    notify(`保存失败：${result.error.message}`, 'negative')
    return
  }
  gatewayDialog.show = false
  await refresh()
}

async function toggleGateway(gateway: Gateway, enabled: boolean) {
  const result = enabled
    ? await withRecentAuth(() => identityClient.enableModelGateway(gateway.id, { expectedVersion: gateway.version }))
    : await withRecentAuth(() => identityClient.disableModelGateway(gateway.id, { expectedVersion: gateway.version }))
  if (result.error) notify(`操作失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
  else await refresh()
}

function deleteGateway(gateway: Gateway) {
  $q.dialog({
    title: '删除服务商',
    message: `确定删除服务商「${gateway.name}」吗？删除后其下的模型将无法使用。`,
    cancel: { label: '取消', flat: true },
    ok: { label: '删除', color: 'negative', unelevated: true },
  }).onOk(async () => {
    const result = await withRecentAuth(() => identityClient.deleteModelGateway(gateway.id))
    if (result.error) notify(`删除失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
    else await refresh()
  })
}

const HEALTH_LABELS: Record<string, string> = {
  healthy: '正常',
  degraded: '降级',
  unavailable: '不可用',
  unknown: '未知',
}

async function health(id: string) {
  const result = await withRecentAuth(() => identityClient.checkModelGatewayHealth(id))
  if (result.error) {
    notify(`健康检查失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
    return
  }
  const items = result.data ?? []
  if (!items.length) {
    notify('健康检查完成')
    return
  }
  const counts = new Map<string, number>()
  for (const item of items) {
    const capability = typeof item.capability === 'string' ? item.capability : ''
    const state = typeof item.state === 'string' ? item.state : ''
    const label = `${capabilityLabel(capability)}${HEALTH_LABELS[state] ?? state}`
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  const summary = [...counts.entries()].map(([label, n]) => (n > 1 ? `${label}×${n}` : label)).join('、')
  notify(`健康检查完成：${summary}`)
  await refresh()
}

// ---------- 拉取模型 ----------
interface DiscoverItem {
  name: string
  capability: Capability
  dimension: number | null
  selected: boolean
  exists: boolean
}

const discoverDialog = reactive({
  show: false,
  gateway: null as Gateway | null,
  loading: false,
  importing: false,
  error: '',
  items: [] as DiscoverItem[],
})

const selectedDiscoverCount = computed(() => discoverDialog.items.filter(item => item.selected && !item.exists).length)

async function openDiscover(gateway: Gateway) {
  discoverDialog.gateway = gateway
  discoverDialog.loading = true
  discoverDialog.error = ''
  discoverDialog.items = []
  discoverDialog.show = true
  const result = await withRecentAuth(() => identityClient.discoverModelGateway(gateway.id))
  discoverDialog.loading = false
  if (result.error) {
    discoverDialog.error = `拉取失败：${apiErrorMessage(result.error, '请稍后重试')}`
    return
  }
  const names = result.data?.names ?? []
  if (!names.length) {
    discoverDialog.error = '远端没有返回任何模型，请检查地址与密钥是否正确。'
    return
  }
  discoverDialog.items = names.map(name => {
    const capability = guessCapability(name)
    return {
      name,
      capability,
      dimension: capability === 'embedding' ? (KNOWN_DIMENSIONS[name] ?? null) : null,
      selected: false,
      exists: models.value.some(model => model.gatewayId === gateway.id && model.remoteName === name),
    }
  })
}

async function importSelected() {
  const gateway = discoverDialog.gateway
  if (!gateway) return
  discoverDialog.importing = true
  const chosen = discoverDialog.items.filter(item => item.selected && !item.exists)
  let imported = 0
  let pending = 0
  const failures: string[] = []
  for (const item of chosen) {
    const created = await withRecentAuth(() => identityClient.createGovernedModel({
      gatewayId: gateway.id,
      remoteName: item.name,
      businessLabel: item.name,
      capability: item.capability,
      embeddingDimension: item.capability === 'embedding' ? (item.dimension ?? undefined) : undefined,
    }))
    if (created.error || !created.data) {
      failures.push(`${item.name}：${apiErrorMessage(created.error, '创建失败')}`)
      if (apiErrorCode(created.error) === 'HTTP_401') break
      continue
    }
    // 尽力验证并启用，让导入的模型开箱可用；失败则保留为草稿
    const validated = await withRecentAuth(() => identityClient.validateGovernedModel(created.data!.id))
    if (validated.data?.validated) {
      await withRecentAuth(() => identityClient.enableGovernedModel(created.data!.id))
    } else {
      pending += 1
    }
    imported += 1
  }
  discoverDialog.importing = false
  discoverDialog.show = false
  await refresh()
  if (failures.length) notify(`部分模型导入失败：${failures.join('；')}`, 'negative')
  else notify(pending ? `已导入 ${imported} 个模型，其中 ${pending} 个验证未通过，暂不可启用` : `已导入 ${imported} 个模型并全部启用`)
}

// ---------- 模型清单 ----------
function modelLabel(model: GovernedModel) {
  return model.remoteName && model.remoteName !== model.businessLabel
    ? `${model.businessLabel}（${model.remoteName}）`
    : model.businessLabel
}

async function validateModel(model: GovernedModel) {
  const result = await withRecentAuth(() => identityClient.validateGovernedModel(model.id, { expectedVersion: model.version }))
  if (result.error) {
    notify(`验证失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
    return
  }
  if (result.data?.validated) notify(`「${model.businessLabel}」验证通过`)
  else notify(`「${model.businessLabel}」验证未通过，请检查服务商与模型名称`, 'negative')
  await refresh()
}

async function toggleModel(model: GovernedModel, enabled: boolean) {
  const result = enabled
    ? await withRecentAuth(() => identityClient.enableGovernedModel(model.id, { expectedVersion: model.version }))
    : await withRecentAuth(() => identityClient.disableGovernedModel(model.id, { expectedVersion: model.version }))
  if (result.error) notify(`操作失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
  else await refresh()
}

function deleteModel(model: GovernedModel) {
  $q.dialog({
    title: '删除模型',
    message: `确定删除模型「${model.businessLabel}」吗？`,
    cancel: { label: '取消', flat: true },
    ok: { label: '删除', color: 'negative', unelevated: true },
  }).onOk(async () => {
    const result = await withRecentAuth(() => identityClient.deleteGovernedModel(model.id))
    if (result.error) notify(`删除失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
    else await refresh()
  })
}

// ---------- 数据加载 ----------
async function refresh() {
  loading.value = true
  error.value = ''
  const [gatewayResult, modelResult, profileResult, kbResult] = await Promise.all([
    identityClient.listModelGateways(),
    identityClient.listGovernedModels(),
    identityClient.listCapabilityProfiles(),
    identityClient.adminListKnowledgeBases(),
  ])
  gateways.value = gatewayResult.data?.items ?? []
  models.value = modelResult.data?.items ?? []
  profiles.value = profileResult.data?.items ?? []
  kbs.value = kbResult.data?.items ?? []
  error.value = gatewayResult.error?.message || modelResult.error?.message || profileResult.error?.message || kbResult.error?.message || ''
  loading.value = false
}

onMounted(refresh)

// ---------- 场景配置保存 ----------
async function saveSceneConfig(_id: Workflow) { // eslint-disable-line @typescript-eslint/no-unused-vars, @typescript-eslint/require-await
  // TODO: Implement backend API for updating scene model bindings directly
  notify('功能开发中：模型绑定即将支持直接保存', 'warning')
  /*
  const result = await withRecentAuth(() => identityClient.updateSceneConfiguration(id, { chatModelId: state.chatModelId, embeddingModelId: state.embeddingModelId, rerankModelId: state.rerankModelId }))
  if (result.error) {
    notify(`保存失败：${apiErrorMessage(result.error, '请稍后重试')}`, 'negative')
    return
  }
  notify('已保存')
  */
}
</script>

<style scoped>
.models-page {
  background: var(--tk-bg);
}

.page-subtitle {
  color: var(--tk-text-secondary);
  font-size: 14px;
}

.surface-card {
  background: var(--tk-surface-white);
  border-radius: var(--tk-radius);
  border-color: var(--tk-border);
}

.error-banner {
  border-radius: var(--tk-radius);
}

.discover-item-exists {
  opacity: 0.5;
}
</style>
