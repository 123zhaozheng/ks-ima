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
      <!-- Knowledge bases still loading: calm spinner instead of a flashing empty state. -->
      <q-spinner
        v-if="!listReady"
        color="primary"
        size="40px"
      />
      <!-- No knowledge base: minimal onboarding with a way forward. -->
      <div
        v-else-if="!kbStore.id"
        class="tk-empty"
        data-testid="ask-home-onboarding"
      >
        <q-icon
          name="sym_o_forum"
          size="56px"
          class="tk-empty-icon"
        />
        <div class="tk-empty-title">
          {{ t('Start with a knowledge base') }}
        </div>
        <div class="tk-empty-subtitle">
          {{ t('Ask grounds every answer in a knowledge base. Create one, or join with a share link.') }}
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            :label="t('Create knowledge base')"
            data-testid="ask-home-create-kb"
            @click="showCreateKb = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            :label="t('Join with a link')"
            data-testid="ask-home-join-kb"
            @click="joinWithLink"
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
          :kb-id="kbStore.id ?? ''"
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
          {{ t('Answers are grounded in your knowledge base.') }}
        </div>
      </div>
    </q-page>
  </q-page-container>
  <q-dialog
    v-model="showCreateKb"
    @hide="kbName = ''"
  >
    <q-card
      min-w="360px"
      data-testid="ask-home-create-kb-dialog"
    >
      <q-card-section class="text-h6">
        {{ t('Create knowledge base') }}
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="kbName"
          outlined
          autofocus
          :label="t('Knowledge base name')"
          data-testid="kb-name-input"
          @keyup.enter="createKb"
        />
        <div class="tk-caption q-mt-sm">
          {{ t('You will become the owner of the new knowledge base.') }}
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          :label="t('Cancel')"
        />
        <q-btn
          flat
          color="primary"
          :label="t('Create')"
          :loading="creating"
          :disable="!kbName.trim()"
          data-testid="kb-create-button"
          @click="createKb"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Notify, useQuasar } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import AskComposer from 'src/components/AskComposer.vue'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { useRequireLogin } from 'src/composables/require-login'
import { useKbStore } from 'src/stores/knowledge-base'
import { useUiStateStore } from 'src/stores/ui-state'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

useRequireLogin()

const router = useRouter()
const $q = useQuasar()
const queryClient = useQueryClient()
const kbStore = useKbStore()
const uiStateStore = useUiStateStore()
// Shared instance from AppShell: the stream keeps running after we route to
// /ask/:conversationId below.
const grounded = inject(groundedKey) ?? useGroundedKnowledge(() => kbStore.id)

const composerRef = ref<InstanceType<typeof AskComposer>>()
const asking = ref(false)
const showCreateKb = ref(false)
const kbName = ref('')
const creating = ref(false)
const listReady = computed(() => kbStore.kbsStatus === 'success')

// Curated example questions; clicking one fills the composer.
const hints = [
  t('Summarize the key points of the newest note'),
  t('What decisions were made in the latest meeting?'),
  t('List the open risks mentioned in project docs'),
]

function fillHint(hint: string) {
  composerRef.value?.setText(hint)
}

async function createKb() {
  const name = kbName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const { data, error } = await identityClient.createKnowledgeBase({ name })
    if (error || !data) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Knowledge base created') })
    showCreateKb.value = false
    // Membership list drives the switcher; refresh then select the new kb.
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    kbStore.switchKb(data.id)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
  } finally {
    creating.value = false
  }
}

function joinWithLink() {
  $q.dialog({
    title: t('Join knowledge base'),
    prompt: {
      model: '',
      label: t('Share link'),
    },
    cancel: true,
  }).onOk((link: string) => {
    const token = link.match(/\/join\/(.+)/)?.[1] ?? link.trim()
    token && router.push(`/join/${encodeURIComponent(token)}`)
  })
}

async function onSubmit(question: string) {
  if (asking.value) return
  // Asking requires a selected knowledge base; the composer blocks send
  // without one, and we guard again here.
  if (!kbStore.id) return
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
