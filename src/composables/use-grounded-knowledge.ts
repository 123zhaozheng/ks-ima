import { computed, onScopeDispose, ref, watch } from 'vue'
import type { InjectionKey } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import type { components } from 'src/api/generated/schema'
import { groundedClient } from 'src/api/grounded-client'

type Citation = components['schemas']['CitationResponse']
type Conversation = components['schemas']['ConversationDetail']
type SearchMode = 'keyword' | 'vector' | 'hybrid'

export type GroundedKnowledge = ReturnType<typeof useGroundedKnowledge>

/**
 * AppShell provides one shared instance so a stream started on the Ask home
 * keeps running after the router navigates to /ask/:conversationId.
 */
export const groundedKey: InjectionKey<GroundedKnowledge> = Symbol('grounded-knowledge')

export function useGroundedKnowledge(workspaceId: () => string | null) {
  const client = useQueryClient()
  const controller = ref<AbortController | null>(null)
  const answer = ref('')
  const citations = ref<Citation[]>([])
  const status = ref<'idle' | 'streaming' | 'completed' | 'knowledge_gap' | 'failed' | 'cancelled'>('idle')
  const conversationId = ref<string | null>(null)
  const messageId = ref<string | null>(null)
  const workspace = computed(workspaceId)
  const key = computed(() => ['grounded', 'workspace', workspace.value])

  const conversations = useQuery({
    queryKey: computed(() => [...key.value, 'conversations']),
    queryFn: ({ signal }) => groundedClient.conversations(workspace.value!, signal),
    enabled: computed(() => Boolean(workspace.value)),
  })

  const conversation = useQuery({
    queryKey: computed(() => [...key.value, 'conversation', conversationId.value]),
    queryFn: ({ signal }) => groundedClient.conversation(workspace.value!, conversationId.value!, signal),
    enabled: computed(() => Boolean(workspace.value && conversationId.value)),
  })

  function applyEvent(event: string, payload: Record<string, unknown>) {
    if (typeof payload.conversationId === 'string') conversationId.value = payload.conversationId
    if (typeof payload.messageId === 'string') messageId.value = payload.messageId
    if (event === 'citations' && Array.isArray(payload.citations)) citations.value = payload.citations as Citation[]
    if (event === 'delta' && typeof payload.delta === 'string') answer.value += payload.delta
    if (event === 'completed') status.value = 'completed'
    if (event === 'knowledge_gap') {
      status.value = 'knowledge_gap'
      answer.value = typeof payload.answer === 'string' ? payload.answer : ''
    }
    if (event === 'cancelled') status.value = 'cancelled'
    if (event === 'error') status.value = 'failed'
  }

  function cancel() {
    controller.value?.abort()
    controller.value = null
    if (status.value === 'streaming') status.value = 'cancelled'
  }

  async function stream(run: (signal: AbortSignal) => Promise<void>) {
    cancel()
    answer.value = ''
    citations.value = []
    messageId.value = null
    status.value = 'streaming'
    const next = new AbortController()
    controller.value = next
    try {
      await run(next.signal)
    } catch (error) {
      status.value = next.signal.aborted ? 'cancelled' : 'failed'
      throw error
    } finally {
      if (controller.value === next) controller.value = null
      await client.invalidateQueries({ queryKey: [...key.value, 'conversations'] })
      if (conversationId.value) await client.invalidateQueries({ queryKey: [...key.value, 'conversation', conversationId.value] })
    }
  }

  async function ask(question: string) {
    if (!workspace.value) return
    await stream(signal => groundedClient.ask(workspace.value!, { question, conversationId: conversationId.value }, signal, applyEvent))
  }

  async function retry(message: Conversation['messages'][number]) {
    if (!workspace.value || !conversationId.value || message.role !== 'user') return
    await stream(signal => groundedClient.retry(workspace.value!, conversationId.value!, message.id, message.version, signal, applyEvent))
  }

  async function search(query: string, mode: SearchMode, signal?: AbortSignal) {
    if (!workspace.value) return null
    return groundedClient.search(workspace.value, query, { mode, signal })
  }

  async function rename(title: string, version: number) {
    if (!workspace.value || !conversationId.value) return
    await groundedClient.updateConversation(workspace.value, conversationId.value, { title, expectedVersion: version })
    await client.invalidateQueries({ queryKey: [...key.value, 'conversations'] })
  }

  async function archive(version: number, archived: boolean) {
    if (!workspace.value || !conversationId.value) return
    await groundedClient.updateConversation(workspace.value, conversationId.value, { archived, expectedVersion: version })
    await client.invalidateQueries({ queryKey: [...key.value, 'conversations'] })
  }

  async function remove(version: number) {
    if (!workspace.value || !conversationId.value) return
    await groundedClient.deleteConversation(workspace.value, conversationId.value, version)
    conversationId.value = null
    await client.invalidateQueries({ queryKey: [...key.value, 'conversations'] })
  }

  function resetForWorkspaceSwitch(previous: string | null) {
    cancel()
    if (previous) {
      client.cancelQueries({ queryKey: ['grounded', 'workspace', previous] })
      client.removeQueries({ queryKey: ['grounded', 'workspace', previous] })
    }
    conversationId.value = null
    messageId.value = null
  }

  watch(workspace, (next, previous) => {
    if (previous && previous !== next) resetForWorkspaceSwitch(previous)
  })

  onScopeDispose(cancel)
  return { answer, archive, ask, cancel, citations, conversation, conversationId, conversations, messageId, remove, rename, resetForWorkspaceSwitch, retry, search, status }
}
