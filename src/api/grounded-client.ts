import type { components } from 'src/api/generated/schema'
import { IMAApiError, imaClient } from './ima-client'
import { authenticatedFetch } from 'src/utils/identity-client'

type AskRequest = Omit<components['schemas']['AskRequest'], 'agent'> & { agent?: boolean }
type AskScope = components['schemas']['AskScope']
type Citation = components['schemas']['CitationResponse']
type Conversation = components['schemas']['ConversationDetail']
type ConversationPage = components['schemas']['ConversationPage']
type ConversationPatch = components['schemas']['ConversationPatchRequest']
type ConversationResponse = components['schemas']['ConversationResponse']
type SearchResponse = components['schemas']['SearchResponse']
type VectorIndex = components['schemas']['VectorIndexResponse']
type SearchOptions = { mode?: 'keyword' | 'vector' | 'hybrid', topK?: number, threshold?: number, folderId?: string, signal?: AbortSignal }

type StreamHandler = (event: string, payload: Record<string, unknown>) => void

const path = (value: string | number) => encodeURIComponent(String(value))

type ProblemDetails = components['schemas']['ProblemDetails']

async function toProblem(response: Response): Promise<ProblemDetails> {
  const problem = await response.json().catch(() => null) as ProblemDetails | null
  if (problem && typeof problem === 'object' && 'status' in problem) return problem
  return {
    type: 'about:blank',
    title: 'Request failed',
    status: response.status,
    detail: '',
    code: '',
    correlationId: '',
  }
}

function streamRequest(url: string, body: Record<string, unknown>, signal: AbortSignal, onEvent: StreamHandler) {
  return async () => {
    const headers = new Headers({ Accept: 'text/event-stream', 'Content-Type': 'application/json' })
    const response = await authenticatedFetch(url, { method: 'POST', headers, body: JSON.stringify(body), signal })
    if (!response.ok || !response.body) throw new IMAApiError(await toProblem(response))
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let pending = ''

    const dispatch = (frame: string) => {
      const event = frame.match(/^event:\s*(.+)$/m)?.[1]?.trim()
      const data = frame.match(/^data:\s*(.+)$/m)?.[1]?.trim()
      if (!event || !data) return
      try {
        onEvent(event, JSON.parse(data) as Record<string, unknown>)
      } catch {
        // Ignore a malformed upstream frame; the terminal error frame owns
        // the user-visible failure state and raw gateway text never renders.
      }
    }

    const drain = (flush = false) => {
      while (true) {
        const separator = pending.match(/\r?\n\r?\n/)
        if (!separator || separator.index === undefined) break
        dispatch(pending.slice(0, separator.index))
        pending = pending.slice(separator.index + separator[0].length)
      }
      if (flush && pending.trim()) {
        dispatch(pending)
        pending = ''
      }
    }

    while (true) {
      const next = await reader.read()
      if (next.done) break
      pending += decoder.decode(next.value, { stream: true })
      drain()
    }
    pending += decoder.decode()
    drain(true)
  }
}

export const groundedClient = {
  search: (kbId: string, query: string, options: SearchOptions = {}) => {
    const parameters = new URLSearchParams({ query, mode: options.mode ?? 'keyword' })
    if (options.topK) parameters.set('topK', String(options.topK))
    if (options.threshold !== undefined) parameters.set('threshold', String(options.threshold))
    if (options.folderId) parameters.set('folderId', options.folderId)
    return imaClient.request<SearchResponse>(`/api/v1/knowledge-bases/${path(kbId)}/search?${parameters}`, { signal: options.signal })
  },
  buildIndex: (kbId: string) => imaClient.request<VectorIndex>(`/api/v1/knowledge-bases/${path(kbId)}/search-indexes/build`, { method: 'POST' }),
  // User-level history: every conversation the user can see, across all
  // knowledge bases. Each item carries its owning knowledge base.
  conversations: (signal?: AbortSignal) => imaClient.request<ConversationPage>('/api/v1/conversations', { signal }),
  conversation: (kbId: string, conversationId: string, signal?: AbortSignal) => imaClient.request<Conversation>(`/api/v1/knowledge-bases/${path(kbId)}/conversations/${path(conversationId)}`, { signal }),
  updateConversation: (kbId: string, conversationId: string, body: ConversationPatch) => imaClient.request<ConversationResponse>(`/api/v1/knowledge-bases/${path(kbId)}/conversations/${path(conversationId)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteConversation: (kbId: string, conversationId: string, expectedVersion: number) => imaClient.request<void>(`/api/v1/knowledge-bases/${path(kbId)}/conversations/${path(conversationId)}?expectedVersion=${path(expectedVersion)}`, { method: 'DELETE' }),
  citation: (kbId: string, messageId: string, ordinal: number, signal?: AbortSignal) => imaClient.request<Citation>(`/api/v1/knowledge-bases/${path(kbId)}/messages/${path(messageId)}/citations/${path(ordinal)}`, { signal }),
  // Keep the transport's omission/default semantics intact. The Ask
  // composable opts into the agent loop explicitly; other callers can still
  // exercise the compatibility path with no agent field or agent=false.
  ask: (kbId: string, request: AskRequest, signal: AbortSignal, onEvent: StreamHandler) => streamRequest(`/api/v1/knowledge-bases/${path(kbId)}/ask`, { ...request }, signal, onEvent)(),
  retry: (kbId: string, conversationId: string, messageId: string, expectedVersion: number, scope: AskScope | null | undefined, signal: AbortSignal, onEvent: StreamHandler, agent = false) => streamRequest(`/api/v1/knowledge-bases/${path(kbId)}/conversations/${path(conversationId)}/retry`, { messageId, expectedVersion, agent, ...(scope ? { scope } : {}) }, signal, onEvent)(),
}
