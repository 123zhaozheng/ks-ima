<template>
  <q-header class="ask-home-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        data-testid="ask-home-menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ t('Ask') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page class="ask-home-page">
      <!-- Workspaces still loading: calm spinner instead of a flashing empty state. -->
      <q-spinner
        v-if="!listReady"
        color="primary"
        size="40px"
      />
      <!-- No workspace: honest onboarding with a way forward. -->
      <div
        v-else-if="!workspaceStore.id"
        class="tk-empty"
        data-testid="ask-home-onboarding"
      >
        <q-icon
          name="sym_o_forum"
          size="56px"
          class="tk-empty-icon"
        />
        <div class="tk-empty-title">
          {{ t('Start with a workspace') }}
        </div>
        <div class="tk-empty-subtitle">
          {{ t('Ask grounds every answer in a workspace knowledge base. Create one, or join a workspace with an invitation.') }}
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            :label="t('Create Workspace')"
            data-testid="ask-home-create-workspace"
            @click="showCreateWorkspace = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            :label="t('Join workspace')"
            data-testid="ask-home-join-workspace"
            @click="joinWorkspace"
          />
        </div>
      </div>
      <div
        v-else
        class="ask-home"
      >
        <div
          class="ask-home-name"
          text-center
        >
          Nya AI
        </div>
        <div
          class="ask-home-greeting"
          text-center
        >
          {{ t('Ask anything grounded in your knowledge base') }}
        </div>
        <ask-composer
          ref="composerRef"
          :workspace-id="workspaceStore.id ?? ''"
          :busy="asking"
          @submit="onSubmit"
        />
        <div
          class="ask-home-hints"
          data-testid="ask-hints"
        >
          <button
            v-for="hint in hints"
            :key="hint"
            type="button"
            class="ask-home-hint"
            data-testid="ask-hint"
            @click="fillHint(hint)"
          >
            {{ hint }}
          </button>
        </div>
        <div
          class="ask-home-foot"
          text-center
        >
          {{ t('Answers are grounded in your workspace knowledge base.') }}
        </div>
      </div>
    </q-page>
  </q-page-container>
  <create-workspace-dialog v-model="showCreateWorkspace" />
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Notify, useQuasar } from 'quasar'
import AskComposer from 'src/components/AskComposer.vue'
import CreateWorkspaceDialog from 'src/components/CreateWorkspaceDialog.vue'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { useRequireLogin } from 'src/composables/require-login'
import { useUiStateStore } from 'src/stores/ui-state'
import { useWorkspaceStore } from 'src/stores/workspace'
import { apiErrorMessage } from 'src/utils/api-error'
import { t } from 'src/utils/i18n'

useRequireLogin()

const router = useRouter()
const $q = useQuasar()
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()
// Shared instance from AppShell: the stream keeps running after we route to
// /ask/:conversationId below.
const grounded = inject(groundedKey) ?? useGroundedKnowledge(() => workspaceStore.id)

const composerRef = ref<InstanceType<typeof AskComposer>>()
const asking = ref(false)
const showCreateWorkspace = ref(false)
const listReady = computed(() => workspaceStore.workspacesStatus === 'success')

// Curated example questions; clicking one fills the composer.
const hints = [
  t('Summarize the key points of the newest note'),
  t('What decisions were made in the latest meeting?'),
  t('List the open risks mentioned in project docs'),
]

function fillHint(hint: string) {
  composerRef.value?.setText(hint)
}

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

async function onSubmit(question: string) {
  if (asking.value) return
  if (!workspaceStore.id) return
  asking.value = true
  let routed = false
  const stopWatch = watch(() => grounded.conversationId.value, id => {
    if (!id || routed) return
    routed = true
    stopWatch()
    router.push(`/ask/${id}`)
  }, { immediate: true })
  try {
    await grounded.ask(question)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Ask failed') })
  } finally {
    asking.value = false
    stopWatch()
  }
}
</script>

<style scoped>
.ask-home-header {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}

.ask-home-page {
  min-height: calc(100vh - 50px);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--tk-space-6) 0;
}

.ask-home {
  width: min(92vw, 720px);
}

.ask-home-name {
  font-size: 28px;
  font-weight: var(--tk-weight-semibold);
  letter-spacing: var(--tk-tracking-display);
  color: var(--tk-text);
  margin-bottom: var(--tk-space-2);
}

.ask-home-greeting {
  font-size: 15px;
  color: var(--tk-text-secondary);
  margin-bottom: var(--tk-space-8);
}

.ask-home-hints {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-5);
}

.ask-home-hint {
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius-pill);
  background-color: var(--tk-surface-white);
  color: var(--tk-text-secondary);
  font-size: 13px;
  line-height: 1.4;
  padding: var(--tk-space-1) var(--tk-space-3);
  cursor: pointer;
  transition: background-color var(--tk-dur) var(--tk-ease), color var(--tk-dur) var(--tk-ease);
}

.ask-home-hint:hover {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}

.ask-home-foot {
  margin-top: var(--tk-space-6);
  font-size: 13px;
  color: var(--tk-text-tertiary);
}
</style>
