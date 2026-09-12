<template>
  <div
    class="ask-composer"
    data-testid="ask-composer"
  >
    <q-input
      ref="inputRef"
      v-model="question"
      type="textarea"
      autogrow
      borderless
      :placeholder="placeholderText"
      class="ask-composer-input"
      input-class="ask-composer-textarea"
      :disable="busy"
      @keydown="onKeydown"
    />
    <div class="ask-composer-bar">
      <template v-if="mode === 'home' && kbId">
        <q-chip
          v-if="askContext.hasDocumentScope"
          dense
          removable
          color="primary"
          text-color="white"
          class="ask-composer-scope"
          data-testid="ask-scope-chip"
          title="仅针对此文档提问"
          @remove="askContext.clearDocumentScope()"
        >
          {{ askContext.documentTitle }}
        </q-chip>
        <q-btn
          v-else
          flat
          dense
          no-caps
          icon="sym_o_folder"
          :label="scopeLabel"
          class="ask-composer-scope"
          data-testid="ask-scope-chip"
        >
          <q-menu v-model="scopeMenuOpen">
            <folder-picker-list
              :kb-id="kbId"
              :selected-id="folderScope?.id ?? null"
              @select="pickScope"
            />
          </q-menu>
        </q-btn>
      </template>
      <!-- Conversation scope is pinned by the server at creation; the chip is
           display-only so follow-ups visibly stay in scope. -->
      <q-chip
        v-else-if="mode === 'conversation' && scope"
        dense
        color="primary"
        text-color="white"
        class="ask-composer-scope"
        data-testid="ask-scope-chip"
        title="本对话限定在此范围提问"
      >
        {{ scope.title || '限定范围' }}
      </q-chip>
      <!-- Model picker slot: stays empty until a gateway can be configured. -->
      <slot name="model" />
      <q-space />
      <q-btn
        v-if="busy"
        flat
        dense
        icon="sym_o_stop_circle"
        label="停止"
        data-testid="ask-stop"
        @click="emit('stop')"
      />
      <q-btn
        round
        color="primary"
        icon="sym_o_send"
        :disable="!canSend"
        data-testid="ask-send"
        @click="send"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { QInput } from 'quasar'
import type { components } from 'src/api/generated/schema'
import FolderPickerList from 'src/components/FolderPickerList.vue'
import type { PickedFolder } from 'src/components/folder-picker-list'
import { useAskContextStore } from 'src/stores/ask-context'

type ConversationScope = components['schemas']['ConversationScope']
type AskScope = components['schemas']['AskScope']

const props = withDefaults(defineProps<{
  mode?: 'home' | 'conversation'
  busy?: boolean
  kbId?: string
  placeholder?: string
  scope?: ConversationScope | null
}>(), {
  mode: 'home',
  busy: false,
  kbId: '',
  placeholder: undefined,
  scope: null,
})

const emit = defineEmits<{
  submit: [question: string, scope: AskScope | null]
  stop: []
}>()

const askContext = useAskContextStore()

const question = ref('')
const folderScope = ref<PickedFolder | null>(null)
const scopeMenuOpen = ref(false)
const inputRef = ref<InstanceType<typeof QInput>>()

const placeholderText = computed(() => props.placeholder ?? '询问关于你知识库的任何问题')
const scopeLabel = computed(() => folderScope.value?.title ?? '整个知识库')
// A question without a knowledge base can never be answered; block the submit.
const canSend = computed(() => Boolean(question.value.trim()) && !props.busy && (props.mode === 'conversation' || Boolean(props.kbId)))

function pickScope(folder: PickedFolder | null) {
  folderScope.value = folder
  scopeMenuOpen.value = false
}

function submitScope(): AskScope | null {
  // Conversation scope is pinned server-side; echo it for the mismatch guard.
  if (props.mode === 'conversation') {
    if (props.scope?.folderId) return { folderId: props.scope.folderId }
    if (props.scope?.documentId) return { documentId: props.scope.documentId }
    return null
  }
  if (askContext.hasDocumentScope && askContext.documentId) return { documentId: askContext.documentId }
  return folderScope.value ? { folderId: folderScope.value.id } : null
}

function send() {
  if (!canSend.value) return
  const text = question.value.trim()
  question.value = ''
  const scope = submitScope()
  // Document prefill from the knowledge pane is a one-shot scope hint.
  if (askContext.hasDocumentScope) askContext.clearDocumentScope()
  emit('submit', text, scope)
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== 'Enter') return
  // Enter sends, Shift+Enter keeps the newline, Ctrl/Meta+Enter also sends.
  if (event.shiftKey) return
  event.preventDefault()
  send()
}

function setText(text: string) {
  question.value = text
  focus()
}

function focus() {
  inputRef.value?.focus?.()
}

defineExpose({ focus, scope: folderScope, setText })
</script>

<style scoped>
.ask-composer {
  background-color: var(--tk-surface-white);
  border: 1px solid var(--tk-border);
  border-radius: 20px;
  box-shadow: var(--tk-shadow-md);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-3);
  transition: box-shadow var(--tk-dur) var(--tk-ease), border-color var(--tk-dur) var(--tk-ease);
}

.ask-composer:focus-within {
  border-color: rgba(0, 0, 0, 0.16);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06), 0 12px 32px rgba(0, 0, 0, 0.1);
}

.ask-composer-input {
  font-size: 16px;
}

.ask-composer-bar {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-2);
}

.ask-composer-scope {
  max-width: 240px;
}
</style>
