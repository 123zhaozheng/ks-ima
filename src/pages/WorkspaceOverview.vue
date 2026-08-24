<template>
  <q-page-container>
    <q-page
      v-if="workspaceStore.id"
      class="workspace-admin-page"
      padding
    >
      <div class="row items-center q-col-gutter-md q-mb-md">
        <div class="col">
          <div class="text-h6">
            {{ workspaceName }}
          </div>
          <div class="text-caption text-grey-7">
            {{ t('Workspace administration') }}
          </div>
        </div>
        <q-btn
          flat
          round
          icon="refresh"
          :loading="loading"
          :title="t('Refresh')"
          @click="loadAll"
        />
        <q-btn
          v-if="!canAdmin"
          flat
          round
          icon="logout"
          :title="t('Leave workspace')"
          @click="leaveWorkspace"
        />
      </div>
      <q-tabs
        v-model="tab"
        dense
        align="left"
        active-color="primary"
        indicator-color="primary"
      >
        <q-tab
          name="members"
          icon="group"
          :label="t('Members')"
        />
        <q-tab
          name="groups"
          icon="group_work"
          :label="t('Groups')"
        />
        <q-tab
          name="folders"
          icon="folder_tree"
          :label="t('Directory permissions')"
        />
      </q-tabs>
      <q-separator />
      <q-tab-panels
        v-model="tab"
        animated
      >
        <q-tab-panel
          name="members"
          class="q-px-none"
        >
          <div class="row q-col-gutter-sm q-mb-md">
            <div class="col">
              <q-input
                v-model="memberSearch"
                dense
                outlined
                clearable
                :label="t('Search members')"
                @keyup.enter="loadMembers"
              />
            </div>
            <div class="col-auto">
              <q-btn
                v-if="canAdmin"
                color="primary"
                icon="person_add"
                :label="t('Add member')"
                :disable="!canAdmin"
                @click="addMember"
              />
              <q-btn
                v-if="canAdmin"
                flat
                icon="mail"
                :label="t('Invite')"
                @click="inviteMember"
              />
            </div>
          </div>
          <q-banner
            v-if="error"
            class="bg-red-1 text-red-9 q-mb-md"
            rounded
          >
            {{ error }}<template #action>
              <q-btn
                flat
                :label="t('Retry')"
                @click="loadAll"
              />
            </template>
          </q-banner>
          <q-table
            flat
            bordered
            row-key="userId"
            :rows="members"
            :columns="memberColumns"
            :loading="loading"
            :no-data-label="t('No members')"
          >
            <template #body-cell-user="props">
              <q-td :props="props">
                <div>{{ props.row.displayName || props.row.email || props.row.userId }}</div><div class="text-caption text-grey-7">
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
                  icon="more_vert"
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
                      </q-item><q-item
                        clickable
                        v-close-popup
                        @click="toggleMember(props.row)"
                      >
                        <q-item-section>{{ props.row.state === 'active' ? t('Disable') : t('Restore') }}</q-item-section>
                      </q-item><q-item
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
            bordered
            separator
            class="q-mt-md"
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
                  icon="cancel"
                  :title="t('Revoke invitation')"
                  @click="revokeInvitation(invitation)"
                />
              </q-item-section>
            </q-item>
          </q-list>
        </q-tab-panel>
        <q-tab-panel
          name="groups"
          class="q-px-none"
        >
          <div class="row justify-end q-mb-md">
            <q-btn
              v-if="canAdmin"
              color="primary"
              icon="group_add"
              :label="t('Create group')"
              :disable="!canAdmin"
              @click="createGroup"
            />
          </div>
          <q-list
            bordered
            separator
          >
            <q-item
              v-for="group in groups"
              :key="group.id"
            >
              <q-item-section>
                <q-item-label>{{ group.name }}</q-item-label><q-item-label caption>
                  {{ group.memberCount }} {{ t('members') }}
                </q-item-label>
              </q-item-section><q-item-section
                v-if="canAdmin"
                side
              >
                <q-btn
                  v-if="canAdmin"
                  flat
                  round
                  dense
                  icon="delete"
                  color="negative"
                  :title="t('Delete group')"
                  @click="deleteGroup(group)"
                />
              </q-item-section>
            </q-item><q-item v-if="!groups.length">
              <q-item-section class="text-grey-7">
                {{ t('No groups') }}
              </q-item-section>
            </q-item>
          </q-list>
        </q-tab-panel>
        <q-tab-panel
          name="folders"
          class="q-px-none"
        >
          <q-banner
            v-if="!folders.length"
            class="bg-grey-2"
          >
            {{ t('No accessible folders') }}
          </q-banner>
          <q-list
            v-else
            bordered
            separator
          >
            <q-item
              v-for="folder in folders"
              :key="folder.id"
            >
              <q-item-section avatar>
                <q-icon :name="folder.isRoot ? 'home' : 'folder'" />
              </q-item-section><q-item-section>
                <q-item-label>{{ folder.name }}</q-item-label><q-item-label caption>
                  {{ folder.lifecycle }}
                </q-item-label>
              </q-item-section><q-item-section side>
                <q-btn
                  flat
                  round
                  dense
                  icon="lock"
                  :title="t('Edit permissions')"
                  @click="editAcl(folder)"
                />
              </q-item-section>
            </q-item>
          </q-list>
        </q-tab-panel>
      </q-tab-panels>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuasar } from 'quasar'
import { identityClient } from 'src/utils/identity-client'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'
import type { components } from 'src/api/generated/schema'
import FolderAclDialog from 'src/components/FolderAclDialog.vue'

type Member = components['schemas']['WorkspaceMember']
type Group = components['schemas']['WorkspaceGroup']
type Folder = components['schemas']['Folder']
type Invitation = components['schemas']['Invitation']
type WorkspaceRole = components['schemas']['WorkspaceMember']['role']
const workspaceStore = useWorkspaceStore()
const $q = useQuasar()
const tab = ref('members')
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
  $q.dialog({ title: t('Leave workspace'), message: t('Leave this workspace?'), cancel: true, ok: { color: 'negative', label: t('Leave') } }).onOk(() => identityClient.leaveWorkspaceMember(workspaceStore.id!).then(() => { workspaceStore.id = null }))
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
