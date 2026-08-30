<template>
  <!--
    Workspace admin pages now own their headers (the rail replaced the old
    tab bar). This layout only keeps the login + workspace guards.
  -->
  <router-view v-if="workspaceStore.id" />
  <q-page-container
    v-else
    class="ws-guard"
  >
    <q-page
      flex
      flex-center
      text-on-sur-var
    >
      <q-spinner
        v-if="!listReady"
        color="primary"
        size="40px"
      />
      <div
        v-else
        class="tk-empty"
        data-testid="workspace-onboarding"
      >
        <q-icon
          name="sym_o_workspaces"
          size="56px"
          class="tk-empty-icon"
        />
        <div class="tk-empty-title">
          {{ t('Start with a workspace') }}
        </div>
        <div class="tk-empty-subtitle">
          {{ t('Workspace settings live in a workspace. Create one, or join a workspace with an invitation.') }}
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            :label="t('Create Workspace')"
            data-testid="workspace-onboarding-create"
            @click="showCreateWorkspace = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            :label="t('Join workspace')"
            data-testid="workspace-onboarding-join"
            @click="joinWorkspace"
          />
        </div>
      </div>
    </q-page>
    <create-workspace-dialog v-model="showCreateWorkspace" />
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import CreateWorkspaceDialog from 'src/components/CreateWorkspaceDialog.vue'
import { useRequireLogin } from 'src/composables/require-login'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'

useRequireLogin()

const workspaceStore = useWorkspaceStore()
const $q = useQuasar()
const router = useRouter()
const showCreateWorkspace = ref(false)
const listReady = computed(() => workspaceStore.workspacesStatus === 'success')

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
</script>

<style scoped>
.ws-guard {
  background-color: var(--tk-bg);
}
</style>
