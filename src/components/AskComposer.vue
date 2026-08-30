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
      <template v-if="mode === 'home'">
        <q-chip
          v-if="askContext.hasDocumentScope"
          dense
          removable
          color="primary"
          text-color="white"
          class="ask-composer-scope"
          data-testid="ask-scope-chip"
          :title="t('Asking about this document only')"
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
              :workspace-id="workspaceId"
              :selected-id="scope?.id ?? null"
              @select="pickScope"
            />
          </q-menu>
        </q-btn>
      </template>
      <!-- Model picker slot: stays empty until a gateway can be configured. -->
      <slot name="model" />
      <q-space />
      <q-btn
        v-if="busy"
        flat
        dense
        icon="sym_o_stop_circle"
        :label="t('Stop')"
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
import FolderPickerList from 'src/components/FolderPickerList.vue'
import type { PickedFolder } from 'src/components/folder-picker-list'
import { useAskContextStore } from 'src/stores/ask-context'
import { t } from 'src/utils/i18n'

const props = withDefaults(defineProps<{
  mode?: 'home' | 'conversation'
  busy?: boolean
  workspaceId?: string
  placeholder?: string
}>(), {
  mode: 'home',
  busy: false,
  workspaceId: '',
  placeholder: undefined,
})

const emit = defineEmits<{
  submit: [question: string]
  stop: []
}>()

const askContext = useAskContextStore()

const question = ref('')
const scope = ref<PickedFolder | null>(null)
const scopeMenuOpen = ref(false)
const inputRef = ref<InstanceType<typeof QInput>>()

const placeholderText = computed(() => props.placeholder ?? t('Ask anything about your knowledge base'))
const scopeLabel = computed(() => scope.value?.title ?? t('Whole workspace'))
const canSend = computed(() => Boolean(question.value.trim()) && !props.busy)

function pickScope(folder: PickedFolder | null) {
  scope.value = folder
  scopeMenuOpen.value = false
}

function send() {
  if (!canSend.value) return
  const text = question.value.trim()
  question.value = ''
  // Document prefill from the knowledge pane is a one-shot scope hint.
  if (askContext.hasDocumentScope) askContext.clearDocumentScope()
  emit('submit', text)
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

defineExpose({ focus, scope, setText })
</script>

<style scoped>
.ask-composer {
  background-color: var(--tk-bg);
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius-lg);
  box-shadow: var(--tk-shadow-md);
  padding: var(--tk-space-3) var(--tk-space-3) var(--tk-space-2);
}

.ask-composer:focus-within {
  border-color: var(--tk-accent);
}

.ask-composer-input {
  font-size: 15px;
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
