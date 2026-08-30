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
      >
        <q-menu>
          <q-list>
            <menu-item
              :label="t('Join workspace')"
              icon="sym_o_join"
              @click="joinWorkspace"
            />
          </q-list>
        </q-menu>
      </q-btn>
    </div>
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
import DenseItem from './DenseItem.vue'
import { workspaceAvatar } from 'src/utils/defaults'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'
import { useQuasar } from 'quasar'
import MenuItem from './MenuItem.vue'
import { computed, toRef } from 'vue'
import { useRouter } from 'vue-router'
import WorkspaceItem from './WorkspaceItem.vue'
import { identityClient } from 'src/utils/identity-client'

const workspaceStore = useWorkspaceStore()
const workspace = toRef(workspaceStore, 'workspace')
const $q = useQuasar()

const workspaces = computed(() => workspaceStore.workspaces ?? [])

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
