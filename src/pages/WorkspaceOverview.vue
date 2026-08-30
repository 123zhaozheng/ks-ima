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
      <div class="overview-head">
        <q-toolbar-title>{{ workspaceName }}</q-toolbar-title>
        <div class="overview-head-sub">
          {{ t('Workspace administration') }}
        </div>
      </div>
      <q-space />
      <q-btn
        flat
        round
        dense
        icon="sym_o_refresh"
        :loading="loading"
        :title="t('Refresh')"
        @click="loadAll"
      />
      <q-btn
        v-if="!canAdmin"
        flat
        round
        dense
        icon="sym_o_logout"
        :title="t('Leave workspace')"
        @click="leaveWorkspace"
      />
    </q-toolbar>
  </q-header>
  <q-page-container v-if="workspaceStore.id">
    <q-page class="tk-page overview-page">
      <section class="tk-card overview-section">
        <div class="overview-section-head">
          <div>
            <h2 class="tk-card-title">
              {{ t('Members') }}
            </h2>
          </div>
          <div class="overview-section-actions">
            <q-input
              v-model="memberSearch"
              dense
              outlined
              clearable
              class="overview-search"
              :label="t('Search members')"
              @keyup.enter="loadMembers"
            />
            <q-btn
              v-if="canAdmin"
              unelevated
              no-caps
              color="primary"
              icon="sym_o_person_add"
              :label="t('Add member')"
              @click="addMember"
            />
            <q-btn
              v-if="canAdmin"
              flat
              no-caps
              icon="sym_o_mail"
              :label="t('Invite')"
              @click="inviteMember"
            />
          </div>
        </div>
        <q-banner
          v-if="error"
          rounded
          class="overview-error"
        >
          {{ error }}
          <template #action>
            <q-btn
              flat
              dense
              :label="t('Retry')"
              @click="loadAll"
            />
          </template>
        </q-banner>
        <q-table
          flat
          bordered
          row-key="userId"
          class="overview-table"
          :rows="members"
          :columns="memberColumns"
          :loading="loading"
          :no-data-label="t('No members')"
        >
          <template #body-cell-user="props">
            <q-td :props="props">
              <div>{{ props.row.displayName || props.row.email || props.row.userId }}</div>
              <div class="tk-caption">
                {{ props.row.email }}
              </div>
            </q-td>
          </template>
          <template #body-cell-actions="props">
            <q-td :props="props">
              <q-btn
                v-if="canAdmin"
                flat
                round
                dense
                icon="sym_o_more_vert"
                :title="t('Member actions')"
              >
                <q-menu>
                  <q-list dense>
                    <q-item
                      clickable
                      v-close-popup
                      @click="changeRole(props.row)"
                    >
                      <q-item-section>{{ t('Change role') }}</q-item-section>
                    </q-item>
                    <q-item
                      clickable
                      v-close-popup
                      @click="toggleMember(props.row)"
                    >
                      <q-item-section>{{ props.row.state === 'active' ? t('Disable') : t('Restore') }}</q-item-section>
                    </q-item>
                    <q-item
                      clickable
                      v-close-popup
                      class="text-negative"
                      @click="removeMember(props.row)"
                    >
                      <q-item-section>{{ t('Remove') }}</q-item-section>
                    </q-item>
                  </q-list>
                </q-menu>
              </q-btn>
            </q-td>
          </template>
        </q-table>
        <q-list
          v-if="canAdmin && invitations.length"
          separator
          class="overview-invitations"
        >
          <q-item
            v-for="invitation in invitations"
            :key="invitation.id"
          >
            <q-item-section>
              <q-item-label>{{ invitation.userId }}</q-item-label>
              <q-item-label caption>
                {{ invitation.delivery ?? t('Pending') }} · {{ invitation.role }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                round
                dense
                icon="sym_o_cancel"
                :title="t('Revoke invitation')"
                @click="revokeInvitation(invitation)"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </section>
      <section class="tk-card overview-section">
        <div class="overview-section-head">
          <h2 class="tk-card-title">
            {{ t('Groups') }}
          </h2>
          <div class="overview-section-actions">
            <q-btn
              v-if="canAdmin"
              unelevated
              no-caps
              color="primary"
              icon="sym_o_group_add"
              :label="t('Create group')"
              @click="createGroup"
            />
          </div>
        </div>
        <q-list separator>
          <q-item
            v-for="group in groups"
            :key="group.id"
          >
            <q-item-section>
              <q-item-label>{{ group.name }}</q-item-label>
              <q-item-label caption>
                {{ group.memberCount }} {{ t('members') }}
              </q-item-label>
            </q-item-section>
            <q-item-section
              v-if="canAdmin"
              side
            >
              <q-btn
                flat
                round
                dense
                icon="sym_o_delete"
                color="negative"
                :title="t('Delete group')"
                @click="deleteGroup(group)"
              />
            </q-item-section>
          </q-item>
          <q-item v-if="!groups.length">
            <q-item-section class="overview-empty">
              {{ t('No groups') }}
            </q-item-section>
          </q-item>
        </q-list>
      </section>
      <section class="tk-card overview-section">
        <div class="overview-section-head">
          <h2 class="tk-card-title">
            {{ t('Directory permissions') }}
          </h2>
        </div>
        <q-banner
          v-if="!folders.length"
          class="overview-empty-banner"
        >
          {{ t('No accessible folders') }}
        </q-banner>
        <q-list
          v-else
          separator
        >
          <q-item
            v-for="folder in folders"
            :key="folder.id"
          >
            <q-item-section avatar>
              <q-icon :name="folder.isRoot ? 'sym_o_home' : 'sym_o_folder'" />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ folder.name }}</q-item-label>
              <q-item-label caption>
                {{ folder.lifecycle }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <q-btn
                flat
                round
                dense
                icon="sym_o_lock"
                :title="t('Edit permissions')"
                @click="editAcl(folder)"
              />
            </q-item-section>
          </q-item>
        </q-list>
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { identityClient } from 'src/utils/identity-client'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'
import { queryClient } from 'src/boot/vue-query'
import { t } from 'src/utils/i18n'
import type { components } from 'src/api/generated/schema'
import FolderAclDialog from 'src/components/FolderAclDialog.vue'

type Member = components['schemas']['WorkspaceMember']
type Group = components['schemas']['WorkspaceGroup']
type Folder = components['schemas']['Folder']
type Invitation = components['schemas']['Invitation']
type WorkspaceRole = components['schemas']['WorkspaceMember']['role']
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()
const $q = useQuasar()
const members = ref<Member[]>([])
const groups = ref<Group[]>([])
const folders = ref<Folder[]>([])
const invitations = ref<Invitation[]>([])
const memberSearch = ref('')
const loading = ref(false)
const error = ref('')
const workspaceRole = ref<WorkspaceRole>(
  String(workspaceStore.member?.role) === 'workspace_admin' ? 'workspace_admin' : 'viewer',
)
const workspaceName = computed(() => workspaceStore.workspace?.name ?? workspaceStore.id ?? '')
// The Python workspace role is the only authority for this surface. Platform
// roles and legacy owner/admin labels must never turn on content controls.
const canAdmin = computed(() => workspaceRole.value === 'workspace_admin')
const memberColumns = [
  { name: 'user', label: t('Member'), field: 'userId', align: 'left' as const },
  { name: 'role', label: t('Role'), field: 'role', align: 'left' as const },
  { name: 'state', label: t('State'), field: 'state', align: 'left' as const },
  { name: 'actions', label: '', field: 'actions', align: 'right' as const },
]
async function loadMembers() {
  if (!workspaceStore.id) return
  const result = await identityClient.listWorkspaceMembers(workspaceStore.id, memberSearch.value)
  if (result.data) members.value = result.data
  else error.value = result.error?.message ?? t('Unable to load members')
}
async function loadAll() {
  if (!workspaceStore.id) return
  loading.value = true; error.value = ''
  try {
    const workspace = await identityClient.getMemberWorkspace(workspaceStore.id)
    if (workspace.data?.role) workspaceRole.value = workspace.data.role
    else {
      workspaceRole.value = 'viewer'
      throw new Error(workspace.error?.message ?? t('Workspace access revoked'))
    }
    await Promise.all([loadMembers(), identityClient.listWorkspaceGroups(workspaceStore.id).then(r => { if (r.data) groups.value = r.data }), identityClient.listWorkspaceFolders(workspaceStore.id).then(r => { if (r.data) folders.value = r.data }), identityClient.listWorkspaceInvitations(workspaceStore.id).then(r => { if (r.data) invitations.value = r.data })])
  } finally { loading.value = false }
}
function addMember() {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Add member'), prompt: { model: '', type: 'text', label: t('User ID') }, cancel: true }).onOk(async (userId: string) => { await identityClient.addWorkspaceMember(workspaceStore.id!, { userId, role: 'viewer' }); await loadMembers() })
}
function inviteMember() {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Invite member'), prompt: { model: '', type: 'text', label: t('User ID') }, cancel: true }).onOk(async (userId: string) => {
    const result = await identityClient.issueWorkspaceInvitation(workspaceStore.id!, { userId, role: 'viewer' })
    if (result.data?.boundLink) $q.notify({ message: `${t('Manual invitation link')}: ${result.data.boundLink}`, timeout: 0, actions: [{ icon: 'close', color: 'white' }] })
    else if (result.error) $q.notify({ type: 'negative', message: result.error.message })
    await loadAll()
  })
}
function changeRole(member: Member) {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Change role'), options: { type: 'radio', model: member.role, items: ['workspace_admin', 'knowledge_manager', 'editor', 'viewer'].map(value => ({ label: value, value })) }, cancel: true }).onOk(async (nextRole: 'workspace_admin' | 'knowledge_manager' | 'editor' | 'viewer') => { await identityClient.updateWorkspaceMember(workspaceStore.id!, member.userId, { role: nextRole, expectedVersion: member.version }); await loadMembers() })
}
function toggleMember(member: Member) {
  if (!workspaceStore.id) return
  const state = member.state === 'active' ? 'disabled' : 'active'
  identityClient.updateWorkspaceMember(workspaceStore.id, member.userId, { state, expectedVersion: member.version }).then(loadMembers)
}
function removeMember(member: Member) {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Remove member'), message: t('Remove this member from the workspace?'), cancel: true, ok: { color: 'negative', label: t('Remove') } }).onOk(() => identityClient.removeWorkspaceMember(workspaceStore.id!, member.userId, member.version).then(loadMembers))
}
function revokeInvitation(invitation: Invitation) {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Revoke invitation'), message: t('Revoke this invitation?'), cancel: true }).onOk(() => identityClient.revokeWorkspaceInvitation(workspaceStore.id!, invitation.id).then(loadAll))
}
function leaveWorkspace() {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Leave workspace'), message: t('Leave this workspace?'), cancel: true, ok: { color: 'negative', label: t('Leave') } }).onOk(async () => {
    const result = await identityClient.leaveWorkspaceMember(workspaceStore.id!)
    if (result.error) {
      $q.notify({ message: result.error.message, color: 'negative' })
      return
    }
    await queryClient.invalidateQueries({ queryKey: ['workspaces', 'member'] })
    workspaceStore.id = null
  })
}
function createGroup() {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Create group'), prompt: { model: '', type: 'text', label: t('Group name') }, cancel: true }).onOk((name: string) => identityClient.createWorkspaceGroup(workspaceStore.id!, { name }).then(loadAll))
}
function deleteGroup(group: Group) {
  if (!workspaceStore.id) return
  $q.dialog({ title: t('Delete group'), message: t('ACL grants for this group will be removed.'), cancel: true, ok: { color: 'negative', label: t('Delete') } }).onOk(() => identityClient.deleteWorkspaceGroup(workspaceStore.id!, group.id).then(loadAll))
}
function editAcl(folder: Folder) {
  if (!workspaceStore.id) return
  $q.dialog({ component: FolderAclDialog, componentProps: { entity: { id: folder.id, rootId: workspaceStore.id } } }).onOk(loadAll)
}
watch(() => workspaceStore.id, loadAll, { immediate: true })
</script>

<style scoped>
.overview-head {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.overview-head-sub {
  font-size: 12px;
  color: var(--tk-text-tertiary);
  margin-top: -2px;
}

.overview-page {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-4);
}

.overview-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--tk-space-2);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.overview-section-actions {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  flex-wrap: wrap;
}

.overview-search {
  width: 220px;
}

.overview-error {
  margin: 0 var(--tk-space-4);
  background-color: var(--tk-danger-soft);
  color: var(--tk-danger);
}

.overview-table {
  margin: var(--tk-space-2) var(--tk-space-4) var(--tk-space-4);
  border-radius: var(--tk-radius);
}

.overview-invitations {
  border-top: 1px solid var(--tk-border);
}

.overview-empty,
.overview-empty-banner {
  color: var(--tk-text-secondary);
}

.overview-empty-banner {
  background-color: var(--tk-surface);
}
</style>
