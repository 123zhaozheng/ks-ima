<template>
  <q-list>
    <workspace-item
      v-if="workspace"
      to="/workspace"
      :workspace
    />
    <q-separator />
    <div
      flex
      text-on-sur-var
      items-center
      py-2
      pl-4
      pr-1
    >
      <div>
        {{ t('Workspaces') }}
      </div>
      <q-btn
        icon="sym_o_add"
        :title="t('Add Workspace')"
        flat
        round
        size="sm"
        ml-a
        data-testid="workspace-add"
      >
        <q-menu>
          <q-list>
            <menu-item
              v-close-popup
              :label="t('Create Workspace')"
              icon="sym_o_add_box"
              data-testid="workspace-create-entry"
              @click="showCreateWorkspace = true"
            />
            <menu-item
              v-close-popup
              :label="t('Join workspace')"
              icon="sym_o_join"
              data-testid="workspace-join-entry"
              @click="joinWorkspace"
            />
          </q-list>
        </q-menu>
      </q-btn>
    </div>
    <create-workspace-dialog v-model="showCreateWorkspace" />
    <dense-item
      v-for="w in workspaces"
      :key="w.id"
      :avatar="workspaceAvatar(w)"
      :label="w.name"
      :active="w.id === workspaceStore.id"
      clickable
      @click="workspaceStore.switchWorkspace(w.id)"
      v-close-popup
    />
    <q-separator spaced />
    <menu-item
      :label="t('Account')"
      icon="sym_o_account_circle"
      to="/account"
    />
    <menu-item
      :label="t('Sign Out')"
      icon="sym_o_logout"
      @click="signOut"
      hover:text-err
    />
  </q-list>
</template>

<script setup lang="ts">
import { computed, ref, toRef } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import CreateWorkspaceDialog from './CreateWorkspaceDialog.vue'
import DenseItem from './DenseItem.vue'
import MenuItem from './MenuItem.vue'
import WorkspaceItem from './WorkspaceItem.vue'
import { workspaceAvatar } from 'src/utils/defaults'
import { useWorkspaceStore } from 'src/stores/workspace'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

const workspaceStore = useWorkspaceStore()
const workspace = toRef(workspaceStore, 'workspace')
const $q = useQuasar()

const workspaces = computed(() => workspaceStore.workspaces ?? [])
const showCreateWorkspace = ref(false)

const router = useRouter()
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

function signOut() {
  $q.dialog({
    title: t('Sign Out'),
    message: t('Are you sure you want to sign out?'),
    cancel: true,
    ok: {
      label: t('Sign Out'),
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    await identityClient.signOut()
    workspaceStore.id = null
    router.push('/auth/sign-in')
  })
}
</script>
