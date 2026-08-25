<template>
  <q-page-container>
    <q-page class="q-pa-lg">
      <div class="row items-center q-col-gutter-md q-mb-md">
        <div class="col">
          <div class="text-h5">{{ t('Model governance') }}</div>
          <div class="text-caption text-grey-7">{{ t('Central infrastructure and approved workflow versions') }}</div>
        </div>
        <q-btn flat icon="sym_o_refresh" :loading="loading" :aria-label="t('Refresh')" @click="refresh" />
      </div>

      <q-banner v-if="error" class="bg-red-1 text-negative q-mb-md" rounded>
        {{ error }}
        <template #action><q-btn flat :label="t('Retry')" @click="refresh" /></template>
      </q-banner>

      <q-tabs v-model="tab" align="left" class="text-primary" no-caps>
        <q-tab name="gateways" icon="sym_o_hub" :label="t('Gateways')" />
        <q-tab name="models" icon="sym_o_memory" :label="t('Models')" />
        <q-tab name="profiles" icon="sym_o_tune" :label="t('Profiles')" />
        <q-tab name="assignments" icon="sym_o_account_tree" :label="t('Assignments & impact')" />
      </q-tabs>
      <q-separator />

      <q-tab-panels v-model="tab" animated>
        <q-tab-panel name="gateways" class="q-px-none">
          <div class="row justify-end q-mb-md">
            <q-btn v-if="canManage" color="primary" icon="sym_o_add" :label="t('Add gateway')" no-caps @click="showGatewayForm = true" />
          </div>
          <q-card v-if="showGatewayForm && canManage" flat bordered class="q-pa-md q-mb-md">
            <div class="text-subtitle1 q-mb-sm">{{ gatewayEditId ? t('Edit intranet gateway') : t('New intranet gateway') }}</div>
            <div class="row q-col-gutter-md">
              <q-input v-model="gatewayForm.name" class="col-12 col-md-3" outlined dense :label="t('Name')" />
              <q-input v-model="gatewayForm.baseUrl" class="col-12 col-md-5" outlined dense :label="t('Base URL')" />
              <q-input v-if="!gatewayEditId" v-model="gatewayForm.secret" class="col-12 col-md-4" outlined dense type="password" :label="t('Credential (shown once)')" />
              <q-toggle v-model="gatewayForm.insecurePrivate" class="col-12" :label="t('Allow explicitly allowlisted private HTTP')" />
            </div>
            <div class="q-mt-md">
              <q-btn color="primary" :loading="saving" :label="gatewayEditId ? t('Save gateway') : t('Create disabled gateway')" no-caps @click="saveGateway" />
              <q-btn flat class="q-ml-sm" :label="t('Cancel')" no-caps @click="resetGatewayForm" />
            </div>
          </q-card>
          <q-table flat bordered :rows="gateways" :columns="gatewayColumns" row-key="id" :loading="loading" :no-data-label="t('No gateways configured')">
            <template #body-cell-enabled="props">
              <q-td :props="props"><q-toggle v-if="canManage" :model-value="props.row.enabled" @update:model-value="toggleGateway(props.row, $event)" /></q-td>
            </template>
            <template #body-cell-secretPresent="props">
              <q-td :props="props"><q-badge :color="props.row.secretPresent ? 'positive' : 'warning'">{{ props.row.secretPresent ? t('Configured') : t('Missing') }}</q-badge></q-td>
            </template>
            <template #body-cell-actions="props">
              <q-td :props="props" class="q-gutter-xs">
                <template v-if="canManage">
                  <q-btn flat dense icon="sym_o_sync" :aria-label="t('Discover')" @click="discover(props.row.id)" />
                  <q-btn flat dense icon="sym_o_monitor_heart" :aria-label="t('Health')" @click="health(props.row.id)" />
                  <q-btn flat dense icon="sym_o_key" :aria-label="t('Rotate credential')" @click="startRotate(props.row.id)" />
                  <q-btn flat dense icon="sym_o_edit" :aria-label="t('Edit')" @click="editGateway(props.row)" />
                  <q-btn flat dense icon="sym_o_delete" :aria-label="t('Delete')" @click="deleteGateway(props.row.id)" />
                </template>
              </q-td>
            </template>
          </q-table>
          <q-card v-if="rotateId && canManage" flat bordered class="q-pa-md q-mt-md">
            <q-input v-model="rotateSecret" outlined dense type="password" :label="t('New credential (shown once)')" />
            <q-btn class="q-mt-sm" color="primary" :label="t('Rotate')" no-caps @click="rotateGateway" />
            <q-btn class="q-mt-sm q-ml-sm" flat :label="t('Cancel')" no-caps @click="rotateId = ''" />
          </q-card>
        </q-tab-panel>

        <q-tab-panel name="models" class="q-px-none">
          <q-card v-if="canManage" flat bordered class="q-pa-md q-mb-md">
            <div class="text-subtitle1">{{ editingModelId ? t('Edit governed model') : t('Register governed model') }}</div>
            <div class="row q-col-gutter-md q-mt-sm">
              <q-select v-model="modelForm.gatewayId" class="col-12 col-md-3" outlined dense emit-value map-options :options="gateways.map(gateway => ({ label: gateway.name, value: gateway.id }))" :label="t('Gateway')" />
              <q-input v-model="modelForm.remoteName" class="col-12 col-md-3" outlined dense :label="t('Remote model name')" />
              <q-input v-model="modelForm.businessLabel" class="col-12 col-md-3" outlined dense :label="t('Business label')" />
              <q-select v-model="modelForm.capability" class="col-12 col-md-3" outlined dense :options="['chat', 'embedding', 'rerank']" :label="t('Capability')" />
              <q-input v-model.number="modelForm.embeddingDimension" class="col-12 col-md-3" outlined dense type="number" :label="t('Embedding dimension (if applicable)')" />
            </div>
            <q-btn class="q-mt-sm" color="primary" :loading="saving" :label="editingModelId ? t('Save model') : t('Create disabled model')" no-caps @click="saveModel" />
            <q-btn v-if="editingModelId" class="q-mt-sm q-ml-sm" flat :label="t('Cancel')" no-caps @click="resetModelForm" />
          </q-card>
          <q-table flat bordered :rows="models" :columns="modelColumns" row-key="id" :loading="loading" :no-data-label="t('No governed models configured')">
            <template #body-cell-validated="props"><q-td :props="props"><q-badge :color="props.row.validated ? 'positive' : 'warning'">{{ props.row.validated ? t('Validated') : t('Draft') }}</q-badge></q-td></template>
            <template #body-cell-enabled="props"><q-td :props="props"><q-toggle :model-value="props.row.enabled" :disable="!props.row.validated" @update:model-value="toggleModel(props.row, $event)" /></q-td></template>
            <template #body-cell-actions="props"><q-td v-if="canManage" :props="props" class="q-gutter-xs"><q-btn flat dense icon="sym_o_edit" :aria-label="t('Edit')" @click="editModel(props.row)" /><q-btn flat dense icon="sym_o_verified" :aria-label="t('Validate')" @click="validateModel(props.row.id)" /><q-btn flat dense icon="sym_o_delete" :aria-label="t('Delete')" @click="deleteModel(props.row.id)" /></q-td></template>
          </q-table>
        </q-tab-panel>

        <q-tab-panel name="profiles" class="q-px-none">
          <q-card v-if="canManage" flat bordered class="q-pa-md q-mb-md">
            <div class="text-subtitle1">{{ t('Create workflow profile') }}</div>
            <div class="row q-col-gutter-md q-mt-sm">
              <q-select v-model="profileForm.workflow" class="col-12 col-md-3" outlined dense :options="workflows" :label="t('Workflow')" />
              <q-input v-model="profileForm.businessAlias" class="col-12 col-md-3" outlined dense :label="t('Business alias')" />
              <q-input v-model="profileForm.description" class="col-12 col-md-6" outlined dense :label="t('Description')" />
              <q-input v-model="profileForm.config" class="col-12" outlined dense type="textarea" :label="t('Typed configuration JSON')" />
            </div>
            <q-btn class="q-mt-sm" color="primary" :loading="saving" :label="t('Create draft')" no-caps @click="createProfile" />
          </q-card>
          <div class="text-caption text-grey-7 q-mb-md">{{ t('Published workflow versions are immutable. Clone or edit a draft to change behavior.') }}</div>
          <q-list bordered separator>
            <q-item v-for="profile in profiles" :key="profile.id">
              <q-item-section>
                <q-item-label>{{ profile.businessAlias }}</q-item-label>
                <q-item-label caption>{{ profile.workflow }} · {{ profile.description }}</q-item-label>
              </q-item-section>
              <q-item-section v-if="canManage" side>
                <div class="row items-center q-gutter-sm"><q-badge>{{ profile.lifecycle }}</q-badge><span v-if="profile.currentVersion">v{{ profile.currentVersion }}</span><q-btn flat dense icon="sym_o_history" :aria-label="t('Versions')" @click="showVersions(profile.id)" /><q-btn flat dense icon="sym_o_verified" :aria-label="t('Validate')" @click="validateProfile(profile.id)" /><q-btn flat dense icon="sym_o_content_copy" :aria-label="t('Clone')" @click="cloneProfile(profile.id)" /><q-btn flat dense icon="sym_o_delete" :aria-label="t('Delete')" @click="deleteProfile(profile.id)" /></div>
              </q-item-section>
            </q-item>
            <q-item v-if="!profiles.length"><q-item-section class="text-grey-7">{{ t('No profiles configured') }}</q-item-section></q-item>
          </q-list>
          <q-card v-if="selectedProfile && canManage" flat bordered class="q-pa-md q-mt-md">
            <div class="text-subtitle1">{{ t('Draft editor') }} · {{ selectedProfile.businessAlias }}</div>
            <q-input v-model="draftConfig" outlined dense type="textarea" class="q-mt-sm" :label="t('Draft configuration JSON')" />
            <div class="q-mt-sm q-gutter-sm"><q-btn color="primary" :label="t('Save draft')" no-caps @click="saveDraft" /><q-btn flat :label="t('Validate')" no-caps @click="validateProfile(selectedProfile.id)" /><q-btn flat :label="t('Publish')" no-caps @click="publishProfile(selectedProfile.id)" /><q-btn flat :label="t('Disable/restore')" no-caps @click="toggleProfile(selectedProfile)" /></div>
          </q-card>
        </q-tab-panel>

        <q-tab-panel name="assignments" class="q-px-none">
          <div v-if="canManage" class="row q-col-gutter-md"><q-select v-model="selectedWorkspace" class="col-12 col-md-4" outlined dense emit-value map-options :options="workspaces.map(workspace => ({ label: workspace.name, value: workspace.id }))" :label="t('Workspace')" @update:model-value="loadAssignments" /><q-select v-model="impactModelId" class="col-12 col-md-4" outlined dense emit-value map-options :options="models.map(model => ({ label: model.businessLabel, value: model.id }))" :label="t('Embedding impact model')" /><q-btn class="col-12 col-md-2" color="primary" :label="t('Check impact')" no-caps @click="checkImpact" /></div>
          <div v-if="canManage" class="row q-col-gutter-md q-mt-md"><q-select v-model="assignmentWorkflow" class="col-12 col-md-3" outlined dense :options="workflows" :label="t('Workflow')" /><q-select v-model="assignmentProfileId" class="col-12 col-md-4" outlined dense emit-value map-options :options="profiles.filter(profile => profile.workflow === assignmentWorkflow && profile.lifecycle === 'active' && profile.currentVersion > 0).map(profile => ({ label: profile.businessAlias, value: profile.id }))" :label="t('Published profile')" /><q-input v-model.number="assignmentProfileVersion" class="col-12 col-md-2" outlined dense type="number" :label="t('Version')" /><q-btn class="col-12 col-md-2" color="primary" :label="t('Assign')" no-caps @click="assignProfile" /><q-btn class="col-12 col-md-1" flat icon="sym_o_delete" :aria-label="t('Remove assignment')" @click="removeProfile" /></div>
          <q-table class="q-mt-md" flat bordered :rows="assignments" :columns="assignmentColumns" row-key="workflow" :loading="loading" :no-data-label="t('No assignments')" />
          <q-banner v-if="impact" class="q-mt-md" :class="impact.requiresReindex ? 'bg-orange-1' : 'bg-green-1'">{{ impact.requiresReindex ? t('REINDEX_REQUIRED: {0} affected indexes', impact.affected.length) : t('No reindex is required') }}</q-banner>
        </q-tab-panel>
      </q-tab-panels>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import type { components } from 'src/api/generated/schema'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type Gateway = components['schemas']['ModelGateway']
type GovernedModel = components['schemas']['GovernedModel']
type Profile = components['schemas']['CapabilityProfile']
type Assignment = components['schemas']['Assignment']
type Impact = components['schemas']['ImpactResponse']
type Workspace = components['schemas']['WorkspaceInfo']
const tab = ref('gateways')
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const gateways = ref<Gateway[]>([])
const models = ref<GovernedModel[]>([])
const profiles = ref<Profile[]>([])
const workspaces = ref<Workspace[]>([])
const assignments = ref<Assignment[]>([])
const selectedWorkspace = ref('')
const assignmentWorkflow = ref('grounded_ask')
const assignmentProfileId = ref('')
const assignmentProfileVersion = ref(1)
const impactModelId = ref('')
const impact = ref<Impact | null>(null)
const rotateId = ref('')
const rotateSecret = ref('')
const selectedProfile = ref<Profile | null>(null)
const draftConfig = ref('{}')
const draftVersion = ref(1)
const workflows = ['grounded_ask', 'title_generation', 'summarization', 'embedding', 'reranking']
const profileForm = reactive({ workflow: 'grounded_ask', businessAlias: '', description: '', config: '{"chatModelId":"","systemPrompt":"Approved internal answers","contextLimit":4096,"outputLimit":512}' })
const editingModelId = ref('')
const modelForm = reactive({ gatewayId: '', remoteName: '', businessLabel: '', capability: 'chat' as 'chat' | 'embedding' | 'rerank', embeddingDimension: null as number | null })
const showGatewayForm = ref(false)
const gatewayEditId = ref('')
const gatewayForm = reactive({ name: '', baseUrl: '', secret: '', insecurePrivate: false })
const canManage = computed(() => session.value.data?.user.platformRoles?.some(role => role === 'super_admin' || role === 'platform_admin') ?? false)

const gatewayColumns: QTableColumn<Gateway>[] = [
  { name: 'name', label: t('Name'), field: 'name', align: 'left' },
  { name: 'baseUrl', label: t('Endpoint'), field: row => row.baseUrl || t('Restricted') },
  { name: 'secretPresent', label: t('Credential'), field: 'secretPresent' },
  { name: 'enabled', label: t('Enabled'), field: 'enabled' },
  { name: 'actions', label: t('Actions'), field: 'id' },
]
const modelColumns: QTableColumn<GovernedModel>[] = [
  { name: 'businessLabel', label: t('Label'), field: 'businessLabel', align: 'left' },
  { name: 'capability', label: t('Capability'), field: 'capability' },
  { name: 'remoteName', label: t('Remote name'), field: row => row.remoteName || t('Restricted') },
  { name: 'validated', label: t('Validation'), field: 'validated' },
  { name: 'enabled', label: t('Enabled'), field: 'enabled' },
  { name: 'actions', label: t('Actions'), field: 'id' },
]
const assignmentColumns: QTableColumn<Assignment>[] = [
  { name: 'workflow', label: t('Workflow'), field: 'workflow', align: 'left' },
  { name: 'profileVersion', label: t('Profile version'), field: 'profileVersion' },
  { name: 'availability', label: t('Availability'), field: 'availability' },
  { name: 'version', label: t('Assignment version'), field: 'version' },
]

async function refresh() {
  loading.value = true
  error.value = ''
  const [gatewayResult, modelResult, profileResult, workspaceResult] = await Promise.all([
    identityClient.listModelGateways(), identityClient.listGovernedModels(), identityClient.listCapabilityProfiles(), identityClient.listWorkspaces(),
  ])
  gateways.value = gatewayResult.data?.items ?? []
  models.value = modelResult.data?.items ?? []
  profiles.value = profileResult.data?.items ?? []
  workspaces.value = workspaceResult.data?.items ?? []
  error.value = gatewayResult.error?.message || modelResult.error?.message || profileResult.error?.message || workspaceResult.error?.message || ''
  loading.value = false
}
function resetGatewayForm() { showGatewayForm.value = false; gatewayEditId.value = ''; Object.assign(gatewayForm, { name: '', baseUrl: '', secret: '', insecurePrivate: false }) }
function editGateway(row: Gateway) { gatewayEditId.value = row.id; showGatewayForm.value = true; Object.assign(gatewayForm, { name: row.name, baseUrl: row.baseUrl ?? '', secret: '', insecurePrivate: row.insecurePrivate }) }
async function saveGateway() {
  saving.value = true
  const row = gateways.value.find(gateway => gateway.id === gatewayEditId.value)
  const result = gatewayEditId.value
    ? await identityClient.updateModelGateway(gatewayEditId.value, { name: gatewayForm.name, baseUrl: gatewayForm.baseUrl, insecurePrivate: gatewayForm.insecurePrivate, expectedVersion: row?.version ?? 1 })
    : await identityClient.createModelGateway({ name: gatewayForm.name, baseUrl: gatewayForm.baseUrl, allowedCapabilities: ['chat', 'embedding', 'rerank'], insecurePrivate: gatewayForm.insecurePrivate, allowedHosts: [], allowedCidrs: [], connectTimeoutMs: 5000, readTimeoutMs: 30000, writeTimeoutMs: 30000, poolTimeoutMs: 5000, maxResponseBytes: 8388608, secret: gatewayForm.secret })
  saving.value = false
  if (result.error) error.value = result.error.message
  else { resetGatewayForm(); await refresh() }
}
async function toggleGateway(row: Gateway, enabled: boolean) { const result = enabled ? await identityClient.enableModelGateway(row.id, { expectedVersion: row.version }) : await identityClient.disableModelGateway(row.id, { expectedVersion: row.version }); if (result.error) error.value = result.error.message; else await refresh() }
async function discover(id: string) { const result = await identityClient.discoverModelGateway(id); error.value = result.error?.message || (result.data ? t('Discovered {0} model names', result.data.names.length) : '') }
function startRotate(id: string) { rotateId.value = id; rotateSecret.value = '' }
async function rotateGateway() { if (!rotateId.value || !rotateSecret.value) return; const row = gateways.value.find(gateway => gateway.id === rotateId.value); const result = await identityClient.rotateModelGatewaySecret(rotateId.value, { secret: rotateSecret.value, expectedVersion: row?.version }); if (result.error) error.value = result.error.message; else { rotateId.value = ''; rotateSecret.value = ''; await refresh() } }
async function health(id: string) { const result = await identityClient.checkModelGatewayHealth(id); if (result.error) error.value = result.error.message; else error.value = t('Health check completed') }
async function deleteGateway(id: string) { const result = await identityClient.deleteModelGateway(id); if (result.error) error.value = result.error.message; else await refresh() }
function editModel(row: GovernedModel) { editingModelId.value = row.id; Object.assign(modelForm, { gatewayId: row.gatewayId ?? '', remoteName: row.remoteName ?? '', businessLabel: row.businessLabel, capability: row.capability, embeddingDimension: row.embeddingDimension }) }
function resetModelForm() { editingModelId.value = ''; Object.assign(modelForm, { gatewayId: '', remoteName: '', businessLabel: '', capability: 'chat', embeddingDimension: null }) }
async function saveModel() { saving.value = true; const result = editingModelId.value ? await identityClient.updateGovernedModel(editingModelId.value, { businessLabel: modelForm.businessLabel, embeddingDimension: modelForm.embeddingDimension ?? undefined, expectedVersion: models.value.find(model => model.id === editingModelId.value)?.version ?? 1 }) : await identityClient.createGovernedModel({ gatewayId: modelForm.gatewayId, remoteName: modelForm.remoteName, businessLabel: modelForm.businessLabel, capability: modelForm.capability, embeddingDimension: modelForm.embeddingDimension ?? undefined }); saving.value = false; if (result.error) error.value = result.error.message; else { resetModelForm(); await refresh() } }
async function validateModel(id: string) { const row = models.value.find(model => model.id === id); const result = await identityClient.validateGovernedModel(id, { expectedVersion: row?.version }); if (result.error) error.value = result.error.message; else await refresh() }
async function toggleModel(row: GovernedModel, enabled: boolean) { const result = enabled ? await identityClient.enableGovernedModel(row.id, { expectedVersion: row.version }) : await identityClient.disableGovernedModel(row.id, { expectedVersion: row.version }); if (result.error) error.value = result.error.message; else await refresh() }
async function deleteModel(id: string) { const result = await identityClient.deleteGovernedModel(id); if (result.error) error.value = result.error.message; else await refresh() }
async function createProfile() { try { const config = JSON.parse(profileForm.config) as Record<string, unknown>; const result = await identityClient.createCapabilityProfile({ workflow: profileForm.workflow as components['schemas']['ProfileCreateRequest']['workflow'], businessAlias: profileForm.businessAlias, description: profileForm.description, config }); if (result.error) error.value = result.error.message; else await refresh() } catch { error.value = t('Profile configuration must be valid JSON') } }
async function showVersions(id: string) { const result = await identityClient.listCapabilityProfileVersions(id); if (result.error) error.value = result.error.message; else { selectedProfile.value = profiles.value.find(profile => profile.id === id) ?? null; const draft = result.data?.items.find(version => version.state === 'draft'); draftVersion.value = draft?.draftVersion ?? 1; draftConfig.value = JSON.stringify(draft?.config ?? {}, null, 2) } }
async function saveDraft() { if (!selectedProfile.value) return; try { const result = await identityClient.patchCapabilityProfileDraft(selectedProfile.value.id, { config: JSON.parse(draftConfig.value) as Record<string, unknown>, expectedDraftVersion: draftVersion.value }); if (result.error) error.value = result.error.message; else { draftVersion.value += 1; await showVersions(selectedProfile.value.id) } } catch { error.value = t('Profile configuration must be valid JSON') } }
async function validateProfile(id: string) { const result = await identityClient.validateCapabilityProfile(id); if (result.error) error.value = result.error.message; else error.value = result.data?.ok ? t('Profile is valid') : t('Profile is unavailable') }
async function publishProfile(id: string) { const result = await identityClient.publishCapabilityProfile(id, { config: JSON.parse(draftConfig.value) as Record<string, unknown>, expectedDraftVersion: draftVersion.value }); if (result.error) error.value = result.error.message; else await refresh() }
async function cloneProfile(id: string) { const result = await identityClient.cloneCapabilityProfile(id); if (result.error) error.value = result.error.message; else await refresh() }
async function toggleProfile(profile: Profile) { const result = profile.lifecycle === 'disabled' ? await identityClient.restoreCapabilityProfile(profile.id) : await identityClient.disableCapabilityProfile(profile.id); if (result.error) error.value = result.error.message; else await refresh() }
async function deleteProfile(id: string) { const result = await identityClient.deleteCapabilityProfile(id); if (result.error) error.value = result.error.message; else await refresh() }
async function loadAssignments() { if (!selectedWorkspace.value) return; const result = await identityClient.listCapabilityAssignments(selectedWorkspace.value); assignments.value = result.data?.items ?? []; if (result.error) error.value = result.error.message }
async function assignProfile() { if (!selectedWorkspace.value || !assignmentProfileId.value) return; const result = await identityClient.assignCapabilityProfile(selectedWorkspace.value, assignmentWorkflow.value, { workflow: assignmentWorkflow.value as components['schemas']['AssignmentRequest']['workflow'], profileId: assignmentProfileId.value, profileVersion: assignmentProfileVersion.value, expectedVersion: assignments.value.find(assignment => assignment.workflow === assignmentWorkflow.value)?.version }); if (result.error) error.value = result.error.message; else await loadAssignments() }
async function removeProfile() { if (!selectedWorkspace.value) return; const current = assignments.value.find(assignment => assignment.workflow === assignmentWorkflow.value); if (!current) return; const result = await identityClient.removeCapabilityProfile(selectedWorkspace.value, assignmentWorkflow.value, current.version); if (result.error) error.value = result.error.message; else await loadAssignments() }
async function checkImpact() { if (!impactModelId.value) return; const result = await identityClient.modelGovernanceImpact(impactModelId.value); impact.value = result.data ?? null; if (result.error) error.value = result.error.message }
onMounted(refresh)
</script>
