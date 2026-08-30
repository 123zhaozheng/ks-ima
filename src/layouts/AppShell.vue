<template>
  <q-layout view="lHr Lpr lFf">
    <q-drawer
      v-model="uiStateStore.mainDrawerOpen"
      show-if-above
      :width="uiStateStore.mainDrawerWidth"
      :breakpoint="uiStateStore.mainDrawerBreakpoint"
      class="app-rail"
      flex="~ col"
    >
      <q-item
        v-if="userId"
        clickable
        py-1
      >
        <q-item-section
          avatar
          pr-3
          ml--1
        >
          <a-avatar :avatar="workspaceAvatar(workspaceStore.workspace)" />
        </q-item-section>
        <q-item-section>
          <q-item-label v-if="workspaceStore.workspace">
            {{ workspaceStore.workspace.name }}
          </q-item-label>
          <q-item-label
            v-else
            text-warn
          >
            {{ t('No workspace selected') }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <q-icon name="sym_o_keyboard_arrow_down" />
        </q-item-section>
        <q-menu>
          <workspace-menu-list />
        </q-menu>
      </q-item>
      <q-item
        v-else
        to="/auth/sign-in"
      >
        <q-item-section
          avatar
          min-w-0
        >
          <q-icon name="sym_o_login" />
        </q-item-section>
        <q-item-section>
          <q-item-label>
            {{ t('Sign In / Sign Up') }}
          </q-item-label>
        </q-item-section>
      </q-item>
      <q-separator spaced />
      <template v-if="userId">
        <q-list
          p-2
          flex-1
        >
          <q-item
            to="/"
            exact
            item-rd
            min-h="40px"
            data-testid="rail-nav-ask"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_chat" />
            </q-item-section>
            <q-item-section>
              {{ t('Ask') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/kb"
            item-rd
            min-h="40px"
            data-testid="rail-nav-kb"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_folder" />
            </q-item-section>
            <q-item-section>
              {{ t('Knowledge base') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/history"
            item-rd
            min-h="40px"
            data-testid="rail-nav-history"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_history" />
            </q-item-section>
            <q-item-section>
              {{ t('History') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/connectors"
            item-rd
            min-h="40px"
            data-testid="rail-nav-connectors"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_hub" />
            </q-item-section>
            <q-item-section>
              {{ t('Connectors') }}
            </q-item-section>
          </q-item>
          <q-item-label
            header
            mt-2
          >
            {{ t('Workspace admin') }}
          </q-item-label>
          <q-item
            to="/workspace"
            exact
            item-rd
            min-h="40px"
            data-testid="rail-nav-workspace"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_group" />
            </q-item-section>
            <q-item-section>
              {{ t('Overview') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/workspace/tags"
            item-rd
            min-h="40px"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_tag" />
            </q-item-section>
            <q-item-section>
              {{ t('Tags') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/workspace/models"
            item-rd
            min-h="40px"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_psychology" />
            </q-item-section>
            <q-item-section>
              {{ t('Models') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/trash"
            item-rd
            min-h="40px"
            data-testid="rail-nav-trash"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_delete" />
            </q-item-section>
            <q-item-section>
              {{ t('Trash') }}
            </q-item-section>
          </q-item>
        </q-list>
        <q-list p-2>
          <q-item
            to="/settings"
            item-rd
            min-h="40px"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_settings" />
            </q-item-section>
            <q-item-section>
              {{ t('Personal Settings') }}
            </q-item-section>
          </q-item>
          <q-item
            to="/account"
            item-rd
            min-h="40px"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_account_circle" />
            </q-item-section>
            <q-item-section>
              {{ t('Account') }}
            </q-item-section>
          </q-item>
          <q-item
            v-if="canSeeAdminConsole"
            :href="adminConsoleUrl"
            target="_blank"
            item-rd
            min-h="40px"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_manage_accounts" />
            </q-item-section>
            <q-item-section>
              {{ t('Admin console') }}
            </q-item-section>
          </q-item>
          <q-item
            clickable
            item-rd
            min-h="40px"
            hover:text-err
            @click="signOut"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_logout" />
            </q-item-section>
            <q-item-section>
              {{ t('Sign Out') }}
            </q-item-section>
          </q-item>
        </q-list>
      </template>
    </q-drawer>
    <router-view />
  </q-layout>
</template>

<script setup lang="ts">
import { computed, provide } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { t } from 'src/utils/i18n'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'
import { identityClient, session } from 'src/utils/identity-client'
import { workspaceAvatar } from 'src/utils/defaults'
import AAvatar from 'src/components/AAvatar.vue'
import WorkspaceMenuList from 'src/components/WorkspaceMenuList.vue'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'

const uiStateStore = useUiStateStore()
const workspaceStore = useWorkspaceStore()
const $q = useQuasar()
const router = useRouter()

// Shared Ask state: streams keep running while the main pane routes from the
// Ask home to /ask/:conversationId.
provide(groundedKey, useGroundedKnowledge(() => workspaceStore.id))

const userId = computed(() => session.value.data?.user.id)

const adminRoles = ['super_admin', 'platform_admin', 'security_auditor']
const canSeeAdminConsole = computed(() =>
  session.value.data?.user.platformRoles?.some(role => adminRoles.includes(role)) ?? false)

// The admin console is a separate deployment: same host, port 8081 in
// production (Caddyfile), port 9015 for local development.
const adminConsoleUrl = computed(() => {
  const { protocol, hostname, port } = location
  const adminPort = port === '9015' || port === '9016' ? '9015' : '8081'
  return `${protocol}//${hostname}:${adminPort}/`
})

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

<style scoped>
.app-rail {
  background-color: var(--tk-surface);
  border-right: 1px solid var(--tk-border);
}
</style>
