<template>
  <q-header class="cv-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title data-testid="conversation-title">
        {{ title }}
      </q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      class="cv-page"
      :style-fn="pageFhStyle"
    >
      <div
        class="cv-main"
        flex="~ col"
        min-h-0
        flex-1
      >
        <div
          ref="scrollRef"
          class="cv-scroll"
          data-testid="conversation-view"
          @click="onContentClick"
          @keydown.enter="onContentKeydown"
        >
          <div
            v-if="query.isError.value"
            class="cv-state"
          >
            <q-icon
              name="sym_o_cloud_off"
              size="40px"
            />
            <div>该对话加载失败。</div>
            <q-btn
              flat
              dense
              color="primary"
              label="重试"
              data-testid="conversation-reload"
              @click="query.refetch()"
            />
          </div>
          <div
            v-else-if="query.isLoading.value"
            class="cv-state"
          >
            <q-spinner color="primary" />
          </div>
          <div
            v-else
            class="cv-thread"
          >
            <template
              v-for="message in messages"
              :key="message.id"
            >
              <div
                v-if="message.role === 'user'"
                class="cv-row cv-row-user"
              >
                <div class="cv-bubble-user">
                  {{ message.content }}
                </div>
              </div>
              <div
                v-else
                class="cv-row cv-row-assistant"
              >
                <div
                  v-if="message.status === 'completed'"
                  class="cv-answer"
                  :data-message-id="message.id"
                >
                  <div
                    class="cv-answer-body md-body"
                    data-testid="assistant-answer"
                    v-html="answerHtml(message)"
                  />
                  <div class="cv-answer-actions">
                    <q-btn
                      flat
                      dense
                      icon="sym_o_note_add"
                      label="保存为笔记"
                      data-testid="save-as-note"
                      @click="openSaveNote(message, message.content, [])"
                    />
                  </div>
                </div>
                <div
                  v-else-if="message.status === 'knowledge_gap'"
                  class="cv-gap"
                >
                  <q-icon name="sym_o_search_off" />
                  <span>知识库中没有找到这个问题的答案。</span>
                </div>
                <div
                  v-else-if="message.status === 'failed' || message.status === 'cancelled'"
                  class="cv-error"
                >
                  <q-icon name="sym_o_error" />
                  <span>{{ message.status === 'cancelled' ? '回答已停止。' : '回答生成失败。' }}</span>
                  <q-btn
                    flat
                    dense
                    color="primary"
                    label="重试"
                    data-testid="answer-retry"
                    @click="retryAfter(message)"
                  />
                </div>
                <div
                  v-else
                  class="cv-pending"
                >
                  <q-spinner
                    size="18px"
                    color="primary"
                  />
                </div>
              </div>
            </template>
            <div
              v-if="pendingQuestion"
              class="cv-row cv-row-user"
            >
              <div class="cv-bubble-user">
                {{ pendingQuestion }}
              </div>
            </div>
            <div
              v-if="showLive"
              class="cv-row cv-row-assistant"
            >
              <div
                v-if="liveStatus === 'streaming'"
                class="cv-answer"
                data-live-answer
              >
                <div
                  class="cv-answer-body md-body"
                  data-testid="assistant-answer"
                  v-html="liveHtml"
                />
                <citation-sources
                  v-if="liveCitations.length"
                  :citations="liveCitations"
                  @open="openSource"
                />
              </div>
              <div
                v-else-if="liveStatus === 'completed'"
                class="cv-answer"
                data-live-answer
              >
                <div
                  class="cv-answer-body md-body"
                  data-testid="assistant-answer"
                  v-html="liveHtml"
                />
                <citation-sources
                  v-if="liveCitations.length"
                  :citations="liveCitations"
                  @open="openSource"
                />
                <div class="cv-answer-actions">
                  <q-btn
                    flat
                    dense
                    icon="sym_o_note_add"
                    label="保存为笔记"
                    data-testid="save-as-note"
                    @click="openSaveNote(null, grounded.answer.value, liveCitations)"
                  />
                </div>
              </div>
              <div
                v-else-if="liveStatus === 'knowledge_gap'"
                class="cv-gap"
              >
                <q-icon name="sym_o_search_off" />
                <span>知识库中没有找到这个问题的答案。</span>
              </div>
              <div
                v-else-if="liveStatus === 'failed' || liveStatus === 'cancelled'"
                class="cv-error"
              >
                <q-icon name="sym_o_error" />
                <span>{{ liveStatus === 'cancelled' ? '回答已停止。' : '回答生成失败。' }}</span>
                <q-btn
                  flat
                  dense
                  color="primary"
                  label="重试"
                  data-testid="answer-retry"
                  @click="retryLastUser"
                />
              </div>
            </div>
          </div>
        </div>
        <div class="cv-composer">
          <ask-composer
            mode="conversation"
            :busy="streaming"
            placeholder="在这个对话中继续追问"
            @submit="followUp"
            @stop="grounded.cancel()"
          />
        </div>
      </div>
      <aside
        v-if="citationPane"
        class="cv-pane"
        data-testid="citation-pane"
      >
        <doc-preview
          :document-id="citationPane.documentId"
          :highlight="citationPane.quote"
          @close="citationPane = null"
        />
      </aside>
    </q-page>
  </q-page-container>
  <save-answer-dialog
    v-model="showSave"
    :answer="saveAnswer"
    :citations="saveCitations"
    :kb-id="citationKbId ?? ''"
    @created="onNoteCreated"
  />
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, inject, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Notify } from 'quasar'
import AskComposer from 'src/components/AskComposer.vue'
import CitationSources from 'src/components/CitationSources.vue'
import DocPreview from 'src/components/DocPreview.vue'
import SaveAnswerDialog from 'src/components/SaveAnswerDialog.vue'
import { groundedClient } from 'src/api/grounded-client'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { useRequireLogin } from 'src/composables/require-login'
import { useKbStore } from 'src/stores/knowledge-base'
import { useUiStateStore } from 'src/stores/ui-state'
import { apiErrorMessage } from 'src/utils/api-error'
import { pageFhStyle } from 'src/utils/functions'
import { citationMarkerRanks, injectCitationMarks, renderMarkdown } from 'src/utils/markdown'

type Message = components['schemas']['MessageResponse']
type Citation = components['schemas']['CitationResponse'] & { title?: string }

useRequireLogin()

const route = useRoute()
const kbStore = useKbStore()
const uiStateStore = useUiStateStore()

const grounded = inject(groundedKey) ?? useGroundedKnowledge(() => kbStore.id)

const conversationId = computed(() => {
  const value = route.params.conversationId
  return typeof value === 'string' ? value : ''
})

// Route param drives the shared composable, which owns the conversation query.
watch(conversationId, id => {
  if (id && grounded.conversationId.value !== id) grounded.conversationId.value = id
}, { immediate: true })

const query = grounded.conversation
const messages = computed(() => query.data.value?.messages ?? [])
const title = computed(() => query.data.value?.title ?? '提问')

// Citations and saved notes live in the knowledge base that owns this
// conversation, which may differ from the currently selected one.
const citationKbId = computed(() => grounded.conversationKbId.value ?? kbStore.id)

const liveStatus = computed(() => grounded.status.value)
const streaming = computed(() => liveStatus.value === 'streaming')
const liveCitations = computed(() => grounded.citations.value as Citation[])

// The page owns the live overlay only for streams it observed starting (or
// already streaming on mount, e.g. arriving from the Ask home).
const liveOwned = ref(false)
watch(conversationId, () => { liveOwned.value = false }, { immediate: true })
watch(liveStatus, status => {
  if (status === 'streaming') liveOwned.value = true
}, { immediate: true })

const liveActive = computed(() =>
  grounded.conversationId.value === conversationId.value && liveStatus.value !== 'idle')

// The server updates the streamed assistant message in place, so once the
// persisted thread's last message is that same message in a terminal state the
// overlay has been replaced by the loaded conversation.
const showLive = computed(() => {
  if (!liveActive.value || !liveOwned.value) return false
  const last = messages.value.at(-1)
  const persisted = Boolean(last?.role === 'assistant' &&
    ['completed', 'knowledge_gap', 'failed', 'cancelled'].includes(last.status) &&
    last.id === grounded.messageId.value)
  return !persisted
})

const liveHtml = computed(() =>
  injectCitationMarks(renderMarkdown(grounded.answer.value), liveCitations.value.map(citation => citation.rank)))

function answerHtml(message: Message): string {
  const ranks = citationMarkerRanks(message.content)
  return injectCitationMarks(renderMarkdown(message.content), ranks)
}

// Optimistic user bubble while the follow-up stream is in flight.
const pendingQuestion = ref('')
watch(messages, value => {
  if (pendingQuestion.value && value.some(message => message.role === 'user' && message.content === pendingQuestion.value)) {
    pendingQuestion.value = ''
  }
}, { immediate: true })

async function followUp(question: string) {
  pendingQuestion.value = question
  try {
    await grounded.ask(question)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '提问失败') })
  }
}

function retryAfter(message: Message) {
  const index = messages.value.findIndex(item => item.id === message.id)
  const user = [...messages.value.slice(0, index)].reverse().find(item => item.role === 'user')
  if (!user) return
  grounded.retry(user).catch(error => {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '重试失败') })
  })
}

function retryLastUser() {
  const user = [...messages.value].reverse().find(item => item.role === 'user')
  if (!user) return
  grounded.retry(user).catch(error => {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '重试失败') })
  })
}

// --- Citation pane -----------------------------------------------------------

const citationPane = ref<{ documentId: string, quote: string } | null>(null)

function openSource(citation: Citation) {
  citationPane.value = { documentId: citation.documentId, quote: citation.quote }
}

async function openCitation(mark: Element, rank: number) {
  if (mark.closest('[data-live-answer]')) {
    const citation = liveCitations.value.find(item => item.rank === rank)
    if (citation) openSource(citation)
    return
  }
  const messageId = mark.closest('[data-message-id]')?.getAttribute('data-message-id')
  if (!messageId || !citationKbId.value) return
  try {
    const citation = await groundedClient.citation(citationKbId.value, messageId, rank) as Citation
    openSource(citation)
  } catch {
    Notify.create({ type: 'negative', message: '引用不可用' })
  }
}

function onContentClick(event: MouseEvent) {
  const mark = (event.target as HTMLElement).closest('[data-citation]')
  if (mark) openCitation(mark, Number(mark.getAttribute('data-citation')))
}

function onContentKeydown(event: KeyboardEvent) {
  const mark = (event.target as HTMLElement).closest?.('[data-citation]')
  if (mark) openCitation(mark, Number(mark.getAttribute('data-citation')))
}

// --- Save as note ------------------------------------------------------------

const showSave = ref(false)
const saveAnswer = ref('')
const saveCitations = ref<Citation[]>([])
const citationCache = new Map<string, Citation[]>()

async function resolveCitations(message: Message, answer: string): Promise<Citation[]> {
  const cached = citationCache.get(message.id)
  if (cached) return cached
  if (!citationKbId.value) return []
  const ranks = citationMarkerRanks(answer)
  const settled = await Promise.allSettled(ranks.map(rank =>
    groundedClient.citation(citationKbId.value!, message.id, rank)))
  const resolved = settled.flatMap(item => item.status === 'fulfilled' ? [item.value as Citation] : [])
  citationCache.set(message.id, resolved)
  return resolved
}

async function openSaveNote(message: Message | null, answer: string, known: Citation[]) {
  saveAnswer.value = answer
  saveCitations.value = known.length > 0 ? known : (message ? await resolveCitations(message, answer) : [])
  showSave.value = true
}

function onNoteCreated() {
  // The note now lives in the chosen folder; the knowledge list picks it up.
}

// --- Scroll behavior ----------------------------------------------------------

const scrollRef = ref<HTMLElement>()

function scrollToBottom(force = false) {
  const el = scrollRef.value
  if (!el) return
  const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 160
  if (force || nearBottom) el.scrollTop = el.scrollHeight
}

watch(() => grounded.answer.value, () => scrollToBottom())
watch(messages, () => scrollToBottom())
onMounted(() => scrollToBottom(true))
</script>

<style scoped>
.cv-header {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}

.cv-page {
  display: flex;
}

.cv-main {
  flex: 1 1 0;
  min-width: 0;
}

.cv-scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  padding: var(--tk-space-5) var(--tk-space-5) var(--tk-space-3);
}

.cv-thread {
  max-width: 860px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-4);
}

.cv-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--tk-space-3);
  color: var(--tk-text-secondary);
}

.cv-row {
  display: flex;
}

.cv-row-user {
  justify-content: flex-end;
}

.cv-row-assistant {
  justify-content: flex-start;
}

.cv-bubble-user {
  max-width: 75%;
  background-color: var(--tk-accent-soft);
  color: var(--tk-text);
  border-radius: var(--tk-radius-lg);
  padding: var(--tk-space-2) var(--tk-space-3);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.cv-answer {
  max-width: 100%;
  min-width: 0;
  flex: 1 1 auto;
}

.cv-answer-body {
  background-color: var(--tk-surface);
  border-radius: var(--tk-radius-lg);
  padding: var(--tk-space-3) var(--tk-space-4);
}

.cv-answer-actions {
  display: flex;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-1);
}

.cv-gap {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  background-color: var(--tk-surface);
  color: var(--tk-text-secondary);
  border-radius: var(--tk-radius-lg);
  padding: var(--tk-space-3) var(--tk-space-4);
  font-size: 14px;
}

.cv-error {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  background-color: var(--tk-danger-soft);
  color: var(--tk-text);
  border-radius: var(--tk-radius-lg);
  padding: var(--tk-space-2) var(--tk-space-3);
  font-size: 14px;
}

.cv-pending {
  padding: var(--tk-space-2) var(--tk-space-3);
}

.cv-composer {
  padding: var(--tk-space-3) var(--tk-space-5) var(--tk-space-4);
  border-top: 1px solid var(--tk-border);
  background-color: var(--tk-bg);
}

.cv-composer > * {
  max-width: 860px;
  margin: 0 auto;
}

.cv-pane {
  flex: 0 0 42%;
  min-width: 380px;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid var(--tk-border);
  background-color: var(--tk-bg);
}
</style>

<style>
/* Citation marks live inside v-html output; keep selectors flat (Chrome 109). */
.citation-mark {
  display: inline-block;
  min-width: 16px;
  margin: 0 2px;
  padding: 0 4px;
  border-radius: var(--tk-radius-sm);
  background-color: var(--tk-accent-soft);
  color: var(--tk-accent);
  font-size: 11px;
  line-height: 16px;
  text-align: center;
  cursor: pointer;
  user-select: none;
}

.citation-mark:hover {
  background-color: var(--tk-accent);
  color: #ffffff;
}

.md-body mark {
  background-color: rgba(255, 213, 0, 0.4);
  color: inherit;
  border-radius: 2px;
  padding: 0 2px;
}
</style>
