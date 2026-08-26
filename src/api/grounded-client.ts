import type { components } from 'src/api/generated/schema'
import { imaClient } from './ima-client'

type AskRequest = components['schemas']['AskRequest']
type Citation = components['schemas']['CitationResponse']
type Conversation = components['schemas']['ConversationDetail']
type ConversationPage = components['schemas']['ConversationPage']
type ConversationPatch = components['schemas']['ConversationPatchRequest']
type ConversationResponse = components['schemas']['ConversationResponse']
type SearchResponse = components['schemas']['SearchResponse']
type VectorIndex = components['schemas']['VectorIndexResponse']
type SearchOptions = { mode?: 'keyword' | 'vector' | 'hybrid', topK?: number, threshold?: number, folderId?: string, tagId?: string, signal?: AbortSignal }

type StreamHandler = (event: string, payload: Record<string, unknown>) => void

const path = (value: string | number) => encodeURIComponent(String(value))

function streamRequest(url: string, body: Record<string, unknown>, signal: AbortSignal, onEvent: StreamHandler) {
  return async () => {
    const headers = new Headers({ Accept: 'text/event-stream', 'Content-Type': 'application/json' })
    const csrf = document.cookie.split('; ').find(value => value.startsWith('ima_csrf='))?.split('=').slice(1).join('=')
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
    const response = await fetch(url, { method: 'POST', credentials: 'include', headers, body: JSON.stringify(body), signal })
    if (!response.ok || !response.body) throw new Error('Grounded Ask is unavailable')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let pending = ''
    while (true) {
      const next = await reader.read()
      if (next.done) break
      pending += decoder.decode(next.value, { stream: true })
      const frames = pending.split('\n\n')
      pending = frames.pop() ?? ''
      for (const frame of frames) {
        const event = frame.match(/^event: (.+)$/m)?.[1]
        const data = frame.match(/^data: (.+)$/m)?.[1]
        if (event && data) onEvent(event, JSON.parse(data) as Record<string, unknown>)
      }
    }
  }
}

export const groundedClient = {
  search: (workspaceId: string, query: string, options: SearchOptions = {}) => {
    const parameters = new URLSearchParams({ query, mode: options.mode ?? 'keyword' })
    if (options.topK) parameters.set('topK', String(options.topK))
    if (options.threshold !== undefined) parameters.set('threshold', String(options.threshold))
    if (options.folderId) parameters.set('folderId', options.folderId)
    if (options.tagId) parameters.set('tagId', options.tagId)
    return imaClient.request<SearchResponse>(`/api/v1/workspaces/${path(workspaceId)}/search?${parameters}`, { signal: options.signal })
  },
  buildIndex: (workspaceId: string) => imaClient.request<VectorIndex>(`/api/v1/workspaces/${path(workspaceId)}/search-indexes/build`, { method: 'POST' }),
  conversations: (workspaceId: string, signal?: AbortSignal) => imaClient.request<ConversationPage>(`/api/v1/workspaces/${path(workspaceId)}/conversations`, { signal }),
  conversation: (workspaceId: string, conversationId: string, signal?: AbortSignal) => imaClient.request<Conversation>(`/api/v1/workspaces/${path(workspaceId)}/conversations/${path(conversationId)}`, { signal }),
  updateConversation: (workspaceId: string, conversationId: string, body: ConversationPatch) => imaClient.request<ConversationResponse>(`/api/v1/workspaces/${path(workspaceId)}/conversations/${path(conversationId)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteConversation: (workspaceId: string, conversationId: string, expectedVersion: number) => imaClient.request<void>(`/api/v1/workspaces/${path(workspaceId)}/conversations/${path(conversationId)}?expectedVersion=${path(expectedVersion)}`, { method: 'DELETE' }),
  citation: (workspaceId: string, messageId: string, ordinal: number, signal?: AbortSignal) => imaClient.request<Citation>(`/api/v1/workspaces/${path(workspaceId)}/messages/${path(messageId)}/citations/${path(ordinal)}`, { signal }),
  ask: (workspaceId: string, request: AskRequest, signal: AbortSignal, onEvent: StreamHandler) => streamRequest(`/api/v1/workspaces/${path(workspaceId)}/ask`, request, signal, onEvent)(),
  retry: (workspaceId: string, conversationId: string, messageId: string, expectedVersion: number, signal: AbortSignal, onEvent: StreamHandler) => streamRequest(`/api/v1/workspaces/${path(workspaceId)}/conversations/${path(conversationId)}/retry`, { messageId, expectedVersion }, signal, onEvent)(),
}
