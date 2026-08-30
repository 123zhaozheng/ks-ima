<template>
  <q-page-container>
    <q-page
      flex
      flex-center
    >
      <div class="ask-home">
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
</template>

<script setup lang="ts">
import { inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Notify } from 'quasar'
import AskComposer from 'src/components/AskComposer.vue'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { useRequireLogin } from 'src/composables/require-login'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'

useRequireLogin()

const router = useRouter()
const workspaceStore = useWorkspaceStore()
// Shared instance from AppShell: the stream keeps running after we route to
// /ask/:conversationId below.
const grounded = inject(groundedKey) ?? useGroundedKnowledge(() => workspaceStore.id)

const composerRef = ref<InstanceType<typeof AskComposer>>()
const asking = ref(false)

// Curated example questions; clicking one fills the composer.
const hints = [
  t('Summarize the key points of the newest note'),
  t('What decisions were made in the latest meeting?'),
  t('List the open risks mentioned in project docs'),
]

function fillHint(hint: string) {
  composerRef.value?.setText(hint)
}

async function onSubmit(question: string) {
  if (asking.value) return
  if (!workspaceStore.id) {
    Notify.create({ type: 'warning', message: t('No workspace selected') })
    return
  }
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
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Ask failed') })
  } finally {
    asking.value = false
    stopWatch()
  }
}
</script>

<style scoped>
.ask-home {
  width: min(92vw, 720px);
}

.ask-home-name {
  font-size: 28px;
  font-weight: 600;
  color: var(--tk-text);
  margin-bottom: var(--tk-space-2);
}

.ask-home-greeting {
  font-size: 14px;
  color: var(--tk-text-secondary);
  margin-bottom: var(--tk-space-6);
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
  border-radius: 999px;
  background-color: var(--tk-bg);
  color: var(--tk-text-secondary);
  font-size: 13px;
  line-height: 1.4;
  padding: var(--tk-space-1) var(--tk-space-3);
  cursor: pointer;
}

.ask-home-hint:hover {
  border-color: var(--tk-accent);
  color: var(--tk-accent);
  background-color: var(--tk-accent-soft);
}

.ask-home-foot {
  margin-top: var(--tk-space-6);
  font-size: 13px;
  color: var(--tk-text-tertiary);
}
</style>
