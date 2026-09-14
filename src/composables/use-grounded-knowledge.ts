import { computed, onScopeDispose, ref, watch } from 'vue'
import type { InjectionKey } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import type { components } from 'src/api/generated/schema'
import { groundedClient } from 'src/api/grounded-client'
import { session } from 'src/utils/identity-client'

type Citation = components['schemas']['CitationResponse']
type Conversation = components['schemas']['ConversationDetail']
type ConversationScope = components['schemas']['ConversationScope']
type AskScope = components['schemas']['AskScope']
type SearchMode = 'keyword' | 'vector' | 'hybrid'

export type AskToolCall = {
  name: string
  arguments: Record<string, unknown>
  hitCount: number
  round: number
}

export type GroundedKnowledge = ReturnType<typeof useGroundedKnowledge>

/**
 * AppShell provides one shared instance so a stream started on the Ask home
 * keeps running after the router navigates to /ask/:conversationId.
 */
export const groundedKey: InjectionKey<GroundedKnowledge> = Symbol('grounded-knowledge')

export function useGroundedKnowledge(kbId: () => string | null) {
  const client = useQueryClient()
  const controller = ref<AbortController | null>(null)
  const answer = ref('')
  const citations = ref<Citation[]>([])
  const toolCalls = ref<AskToolCall[]>([])
  const retrieving = ref(false)
  const status = ref<'idle' | 'streaming' | 'completed' | 'knowledge_gap' | 'failed' | 'cancelled'>('idle')
  const conversationId = ref<string | null>(null)
  const messageId = ref<string | null>(null)
  // Scope of the in-flight stream, for rendering scoped states before the
  // conversation detail reloads.
  const streamScope = ref<ConversationScope | null>(null)
  const kb = computed(kbId)
  let streamGeneration = 0

  // The server pins the scope on the conversation; strip the read-time title
  // before echoing it back in ask/retry request bodies.
  function requestScope(scope: ConversationScope | AskScope | null | undefined): AskScope | undefined {
    if (!scope) return undefined
    if (scope.folderId) return { folderId: scope.folderId }
    if (scope.documentId) return { documentId: scope.documentId }
    return undefined
  }

  // User-level history: one list across every knowledge base; each item carries
  // the knowledge base it belongs to.
  const conversations = useQuery({
    queryKey: ['grounded', 'conversations'],
    queryFn: ({ signal }) => groundedClient.conversations(signal),
    enabled: computed(() => Boolean(session.value.data?.user.id)),
  })

  // Single-conversation operations live under the owning knowledge base, so
  // resolve the conversation's kb from the user-level list.
  const conversationKbId = computed(() => {
    const item = conversations.data.value?.items.find(entry => entry.id === conversationId.value)
    return item?.kbId ?? kb.value ?? null
  })

  const conversation = useQuery({
    queryKey: computed(() => ['grounded', 'conversation', conversationKbId.value, conversationId.value]),
    queryFn: ({ signal }) => groundedClient.conversation(conversationKbId.value!, conversationId.value!, signal),
    enabled: computed(() => Boolean(conversationKbId.value && conversationId.value)),
  })

  function applyEvent(generation: number, event: string, payload: Record<string, unknown>) {
    if (generation !== streamGeneration) return
    if (typeof payload.conversationId === 'string') conversationId.value = payload.conversationId
    if (typeof payload.messageId === 'string') messageId.value = payload.messageId
    if (event === 'retrieving') retrieving.value = true
    if (event === 'tool_call') {
      const name = typeof payload.name === 'string' ? payload.name : '未知工具'
      const argumentsValue = payload.arguments ?? payload.argumentsSummary
      const args = argumentsValue && typeof argumentsValue === 'object' && !Array.isArray(argumentsValue)
        ? argumentsValue as Record<string, unknown>
        : {}
      toolCalls.value.push({
        name,
        arguments: args,
        hitCount: typeof payload.hitCount === 'number' ? payload.hitCount : 0,
        round: typeof payload.round === 'number' ? payload.round : 0,
      })
      retrieving.value = true
    }
    if (event === 'citations' && Array.isArray(payload.citations)) citations.value = payload.citations as Citation[]
    if (event === 'delta' && typeof payload.delta === 'string') {
      retrieving.value = false
      answer.value += payload.delta
    }
    if (event === 'completed') {
      retrieving.value = false
      status.value = 'completed'
    }
    if (event === 'knowledge_gap') {
      retrieving.value = false
      status.value = 'knowledge_gap'
      answer.value = typeof payload.answer === 'string' ? payload.answer : ''
    }
    if (event === 'cancelled') {
      retrieving.value = false
      status.value = 'cancelled'
    }
    if (event === 'error') {
      retrieving.value = false
      status.value = 'failed'
    }
  }

  function cancel() {
    streamGeneration += 1
    controller.value?.abort()
    controller.value = null
    retrieving.value = false
    if (status.value === 'streaming') status.value = 'cancelled'
  }

  async function stream(run: (signal: AbortSignal, onEvent: (event: string, payload: Record<string, unknown>) => void) => Promise<void>) {
    const generation = ++streamGeneration
    controller.value?.abort()
    controller.value = null
    answer.value = ''
    citations.value = []
    toolCalls.value = []
    retrieving.value = false
    messageId.value = null
    status.value = 'streaming'
    const next = new AbortController()
    controller.value = next
    const current = () => generation === streamGeneration
    try {
      await run(next.signal, (event, payload) => applyEvent(generation, event, payload))
    } catch (error) {
      if (!current()) return
      status.value = next.signal.aborted ? 'cancelled' : 'failed'
      throw error
    } finally {
      if (current()) {
        controller.value = null
        await client.invalidateQueries({ queryKey: ['grounded', 'conversations'] })
        if (current() && conversationId.value && conversationKbId.value) {
          await client.invalidateQueries({ queryKey: ['grounded', 'conversation', conversationKbId.value, conversationId.value] })
        }
      }
    }
  }

  async function ask(question: string, scope?: ConversationScope | AskScope | null) {
    if (!kb.value) return
    const requestedScope = requestScope(scope)
    streamScope.value = requestedScope ?? (conversationId.value ? (conversation.data.value?.scope ?? null) : null)
    await stream((signal, onEvent) => groundedClient.ask(kb.value!, { question, conversationId: conversationId.value, agent: true, ...(requestedScope ? { scope: requestedScope } : {}) }, signal, onEvent))
  }

  async function retry(message: Conversation['messages'][number], agent = false) {
    if (!conversationKbId.value || !conversationId.value || message.role !== 'user') return
    const scope = conversation.data.value?.scope ?? null
    streamScope.value = scope
    await stream((signal, onEvent) => groundedClient.retry(conversationKbId.value!, conversationId.value!, message.id, message.version, requestScope(scope), signal, onEvent, agent))
  }

  async function search(query: string, mode: SearchMode, signal?: AbortSignal) {
    if (!kb.value) return null
    return groundedClient.search(kb.value, query, { mode, signal })
  }

  async function rename(title: string, version: number) {
    if (!conversationKbId.value || !conversationId.value) return
    await groundedClient.updateConversation(conversationKbId.value, conversationId.value, { title, expectedVersion: version })
    await client.invalidateQueries({ queryKey: ['grounded', 'conversations'] })
  }

  async function archive(version: number, archived: boolean) {
    if (!conversationKbId.value || !conversationId.value) return
    await groundedClient.updateConversation(conversationKbId.value, conversationId.value, { archived, expectedVersion: version })
    await client.invalidateQueries({ queryKey: ['grounded', 'conversations'] })
  }

  async function remove(version: number) {
    if (!conversationKbId.value || !conversationId.value) return
    await groundedClient.deleteConversation(conversationKbId.value, conversationId.value, version)
    conversationId.value = null
    await client.invalidateQueries({ queryKey: ['grounded', 'conversations'] })
  }

  function resetForKbSwitch(previous: string | null) {
    cancel()
    if (previous) {
      client.cancelQueries({ queryKey: ['grounded', 'kb', previous] })
      client.removeQueries({ queryKey: ['grounded', 'kb', previous] })
    }
    client.cancelQueries({ queryKey: ['grounded', 'conversation'] })
    client.removeQueries({ queryKey: ['grounded', 'conversation'] })
    answer.value = ''
    citations.value = []
    toolCalls.value = []
    retrieving.value = false
    status.value = 'idle'
    conversationId.value = null
    messageId.value = null
    streamScope.value = null
  }

  watch(kb, (next, previous) => {
    if (previous && previous !== next) resetForKbSwitch(previous)
  })

  onScopeDispose(cancel)
  return { answer, archive, ask, cancel, citations, conversation, conversationId, conversationKbId, conversations, messageId, remove, rename, resetForKbSwitch, retrieving, retry, search, status, streamScope, toolCalls }
}
