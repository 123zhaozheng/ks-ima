<template>
  <div
    flex="~ col"
    view-styles
  >
    <common-toolbar>
      <q-btn
        v-if="$route.params.type === 'chat'"
        flat
        dense
        round
        icon="sym_o_arrow_back"
        :title="t('All files')"
        :to="workspaceStore.id ? `/folder/${workspaceStore.id}` : '/'"
      />
      <q-toolbar-title text-lg>
        {{ $route.params.type === 'chat' ? t('Ask') : entityName(entity) }}
      </q-toolbar-title>
      <q-badge v-if="$route.params.type === 'chat'" class="q-ml-auto" color="primary">{{ t('Platform-managed capability') }}</q-badge>
    </common-toolbar>
    <div
      grow
      bg-sur
      of-y-auto
      ref="scrollContainer"
      pos-relative
      @scroll="onScroll"
    >
      <template
        v-for="[parent, current] of pairs(chain)"
        :key="current"
      >
        <message-item
          class="message-item"
          :data-message-id="current"
          v-if="messageMap[current]"
          :model-value="chat.msgRoute[parent] + 1"
          :message="messageMap[current]"
          :child-num="chat.msgTree[parent].length"
          :scroll-container
          @update:model-value="switchChain(parent, $event - 1)"
          @edit="edit(parent)"
          @regenerate="regenerate(parent)"
          @delete-branch="deleteBranch(parent)"
          @rendered="streamingTask && lockBottom()"
          @quote="quote"
          :inputing="current === chain.at(-1)"
          :dense="position !== 'full' || $q.screen.lt.md"
          p-4
        />
      </template>
      <div
        v-if="isEmptyAsk"
        text-on-sur-var
        text-center
        py-12
        px-6
      >
        {{ t('Ask about files in this knowledge base.') }}
      </div>
    </div>
    <div
      pos-relative
      v-if="perfsStore.perfs.chatScrollBtns"
    >
      <div
        pos-absolute
        top--1
        right-1
        flex="~ col"
        text-sec
        translate-y="-100%"
        z-1
      >
        <q-btn
          flat
          round
          dense
          icon="sym_o_first_page"
          rotate-90
          @click="scroll('top')"
        />
        <q-btn
          flat
          round
          dense
          icon="sym_o_keyboard_arrow_up"
          @click="scroll('up')"
        />
        <q-btn
          flat
          round
          dense
          icon="sym_o_keyboard_arrow_down"
          @click="scroll('down')"
        />
        <q-btn
          flat
          round
          dense
          icon="sym_o_last_page"
          rotate-90
          @click="scroll('bottom')"
        />
      </div>
      <message-input
        :message="getMessageAt(-1)!"
        :parent-id="chat.id"
        :input-types="['image/*']"
        :plugins
        :placeholder="t('Ask about your files…')"
        @send="send"
        v-slot="{ empty }"
      >
        <q-space />
        <div
          v-if="usage"
          my-2
          mx-2
        >
          <q-icon
            name="sym_o_generating_tokens"
            size="24px"
          />
          <code
            v-if="$q.screen.gt.xs"
            bg-sur-c-high
            px-2
            py-1
          >{{ usage.inputTokens }}+{{ usage.outputTokens }}</code>
          <q-tooltip>
            {{ t('Last Message Token Consumption') }}<br>
            {{ t('Input') }}: {{ usage.inputTokens }}, {{ t('Output') }}: {{ usage.outputTokens }}
          </q-tooltip>
        </div>
        <abortable-btn
          :loading="!!streamingTask"
          :disable="empty && !streamingTask"
          @click="send"
          @abort="abort"
          :label="t('Send')"
          icon="sym_o_send"
        />
      </message-input>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useUiStateStore } from 'src/stores/ui-state'
import type { Ref } from 'vue'
import { computed, inject, nextTick, toRef, useTemplateRef, watch, ref } from 'vue'
import { mutate } from 'src/utils/zero-session'
import { genId } from 'app/src-shared/utils/id'
import { pairs } from 'src/utils/functions'
import { t } from 'src/utils/i18n'
import { useChatRes } from 'src/composables/chat-res'
import { useQuasar } from 'quasar'
import type { FullChat } from 'app/src-shared/queries'
import { tasks } from 'src/utils/tasks'
import AbortableBtn from 'src/components/AbortableBtn.vue'
import { mutators } from 'app/src-shared/mutators'
import { useThisEntityConf } from 'src/composables/entity-conf'
import type { CompletionConfig } from 'src/services/stream-message'
import { streamChat } from 'src/services/stream-message'
import { generateChatTitle } from 'src/services/generate-chat-title'
import Mark from 'mark.js'
import type { LayoutPosition } from 'src/utils/types'
import { useRoute } from 'vue-router'
import { entityName } from 'src/utils/defaults'
import { usePlugins } from 'src/composables/plugins'
import { useWorkspaceStore } from 'src/stores/workspace'
import CommonToolbar from 'src/components/CommonToolbar.vue'
import MessageInput from 'src/components/MessageInput.vue'
import { usePerfsStore } from 'src/stores/perfs'
import { useChatScroll } from 'src/composables/chat-scroll'
import MessageItem from 'src/components/MessageItem.vue'
import { flush } from 'src/composables/state-proxy'
import { useQuote } from 'src/composables/quote'
import { useListenKey } from 'src/composables/listen-key'

const props = defineProps<{
  chat: FullChat
}>()

const position = inject<Ref<LayoutPosition>>('position')!

const { entity } = useThisEntityConf()

const pluginIds = computed(() => {
  const ids = props.chat.plugins
  if (ids && ids.length) return ids
  return ['workspace', 'mermaid']
})
const { plugins } = usePlugins(pluginIds)

const { getMessageAt, chain, messageMap } = useChatRes(toRef(props, 'chat'))

function switchChain(target: string, value: number) {
  mutate(mutators.switchChain({ entityId: props.chat.id, updates: { [target]: value } }))
}

async function edit(parent: string) {
  const { msgTree, msgRoute } = props.chat
  const { type, text, entities } = messageMap.value[msgTree[parent][msgRoute[parent]]]
  const id = genId()
  await mutate(mutators.appendMessage({
    entityId: props.chat.id,
    target: parent,
    props: { id, type: type as 'chat:user' | 'chat:assistant', text },
    entities: entities.map(entity => entity.id),
  })).client
}

const $q = useQuasar()
async function regenerate(parent: string) {
  const params = getStreamParams()
  if (!params) return
  await mutate(mutators.appendMessagePair({
    entityId: props.chat.id,
    target: parent,
    aProps: { id: genId(), assistantId: undefined, modelName: 'platform-managed', sentAt: Date.now() },
    uProps: { id: genId() },
  })).client
  stream(params)
}

async function deleteBranch(parent: string) {
  const branch = props.chat.msgRoute[parent]
  await mutate(mutators.deleteBranch({
    entityId: props.chat.id,
    parent,
    branch,
  })).client
}

const { chatScrollTops } = useUiStateStore()
function onScroll(ev: Event) {
  const container = ev.target as HTMLElement
  chatScrollTops.set(props.chat.id, container.scrollTop)
}
const scrollContainer = useTemplateRef('scrollContainer')
watch(() => props.chat.id, id => {
  nextTick(() => {
    scrollContainer.value?.scrollTo({ top: chatScrollTops.get(id) ?? 0 })
  })
})

const route = useRoute()
const isEmptyAsk = computed(() =>
  route.params.type === 'chat' &&
  Object.values(messageMap.value).every(m => !m.text?.trim()),
)

watch(route, async () => {
  const messageId = route.query.messageId
  const highlight = route.query.highlight

  if (typeof messageId !== 'string') return

  const { msgTree } = props.chat
  const parentMap = Object.entries(msgTree).reduce((acc, [parent, children]) => {
    children.forEach(child => { acc[child] = parent })
    return acc
  }, {} as Record<string, string>)

  if (!parentMap[messageId]) return

  const updates: Record<string, number> = {}
  let curr = messageId
  while (curr !== '$root') {
    const parent = parentMap[curr]
    updates[parent] = msgTree[parent].indexOf(curr)
    curr = parent
  }
  await mutate(mutators.switchChain({ entityId: props.chat.id, updates })).client
  await nextTick()

  const el = document.querySelector(`[data-message-id="${messageId}"]`)
  if (!el) return

  const instance = new Mark(el)
  instance.unmark()
  highlight && instance.mark(highlight)

  document.querySelector('mark')?.scrollIntoView({ block: 'center' })
}, { immediate: true })

function getStreamParams() {
  const config = getCompletionConfig()
  return { config }
}

async function send() {
  const params = getStreamParams()
  if (!params) return
  const { id } = props.chat
  const target = chain.value.at(-1)!
  flush(target)
  await mutate(mutators.appendMessagePair({
    entityId: id,
    target,
    aProps: { id: genId(), assistantId: undefined, modelName: 'platform-managed', sentAt: Date.now() },
    uProps: { id: genId() },
  })).client
  nextTick(() => {
    scroll('bottom')
  })
  const { promise } = stream(params)
  if (chain.value.length === 4 && perfsStore.perfs.autoGenChatTitle) {
    promise.then(generateTitle)
  }
}
async function generateTitle() {
  await generateChatTitle({ chat: props.chat, conf: {} }).catch(err => {
    console.error(err)
    $q.notify({
      message: t('Failed to generate chat title: {0}', err.message),
      color: 'negative',
    })
  })
}

const streamingTask = computed(() => tasks.find(t => t.id === chain.value.at(-2)! && t.status === 'running'))

const lockingBottom = ref(false)
const perfsStore = usePerfsStore()
function lockBottom() {
  lockingBottom.value && scroll('bottom', 'auto')
}
let lastScrollTop: number | null
function scrollListener() {
  const container = scrollContainer.value!
  if (container.scrollTop < lastScrollTop!) {
    lockingBottom.value = false
  }
  lastScrollTop = container.scrollTop
}
watch(lockingBottom, val => {
  if (!scrollContainer.value) return
  if (val) {
    lastScrollTop = scrollContainer.value.scrollTop
    scrollContainer.value.addEventListener('scroll', scrollListener)
  } else {
    lastScrollTop = null
    scrollContainer.value.removeEventListener('scroll', scrollListener)
  }
})
function stream(params: {
  config: CompletionConfig
}, preventLockBottom = false) {
  lockingBottom.value = perfsStore.perfs.streamingLockBottom && !preventLockBottom
  const task = streamChat({
    id: chain.value.at(-2)!,
    title: t('Chat Completion: {0}', entityName(entity.value)),
    link: `/chat/${props.chat.id}`,
  }, {
    chat: props.chat,
    ...params,
  })
  task.promise.finally(() => {
    lockingBottom.value = false
  })
  return task
}
function getCompletionConfig(): CompletionConfig {
  const tools = Object.fromEntries(Object.entries(plugins.value).map(([id, { tools }]) => [id, tools]))
  return {
    contextNum: 10,
    tools,
  }
}

function abort() {
  streamingTask.value?.abort()
}

const workspaceStore = useWorkspaceStore()

const usage = computed(() => getMessageAt(-2)?.usage)

const { getEls, itemInView, scroll } = useChatScroll(scrollContainer)

function regenerateCurr() {
  const { container, items } = getEls()
  const index = items.findIndex(
    (item, i) => itemInView(item, container) && getMessageAt(i + 1)?.type === 'chat:assistant',
  )
  if (index === -1) return
  regenerate(chain.value[index])
}
function editCurr() {
  const { container, items } = getEls()
  const index = items.findIndex(
    (item, i) => itemInView(item, container) && getMessageAt(i + 1)?.type === 'chat:user',
  )
  if (index === -1) return
  edit(chain.value[index])
}

const quote = useQuote(computed(() => getMessageAt(-1)!))

useListenKey(computed(() => perfsStore.perfs.regenerateCurrKey), regenerateCurr)
useListenKey(computed(() => perfsStore.perfs.editCurrKey), editCurr)
</script>
