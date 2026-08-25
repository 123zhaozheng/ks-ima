import { finish, start, update } from 'src/composables/state-proxy'
import { mutate } from 'src/utils/zero-session'
import type { FullChat } from 'app/src-shared/queries'
import { getChatChain } from 'src/utils/chat-tools'
import { withTask } from 'src/utils/tasks'
import { mutators } from 'app/src-shared/mutators'
import type { PluginTool, ToolResultItem } from 'app/src-shared/utils/types'
import { base64ToUint8Array } from 'app/src-shared/utils/functions'
import { upload } from 'src/utils/blob-cache'
import { genId } from 'app/src-shared/utils/id'

export type CompletionConfig = {
  contextNum?: number | null
  tools: Record<string, PluginTool[]>
}

type ChatMessage = { role: string, content?: string, tool_call_id?: string, tool_calls?: unknown[] }
type ToolCall = { id: string, name: string, arguments: string }
type ParsedResponse = { toolCalls: ToolCall[], usage?: { inputTokens: number, outputTokens: number }, warnings?: string[] }

function messagesFor(chat: FullChat, config: CompletionConfig): ChatMessage[] {
  const map = new Map(chat.messages.map(message => [message.id, message]))
  const chain = getChatChain(chat)
  const rows: ChatMessage[] = []
  for (const id of chain.slice(1, -2).slice(config.contextNum ? -config.contextNum : undefined)) {
    const message = map.get(id)
    if (!message?.text?.trim()) continue
    rows.push({ role: message.type === 'chat:assistant' ? 'assistant' : 'user', content: message.text })
  }
  return rows
}

function toolDefinitions(tools: CompletionConfig['tools']) {
  return Object.entries(tools).flatMap(([pluginId, entries]) => entries.map(tool => ({
    type: 'function',
    function: {
      name: `${pluginId}-${tool.name}`,
      description: tool.description,
      parameters: tool.inputSchema,
    },
  })))
}

function toolMap(tools: CompletionConfig['tools']) {
  return new Map<string, PluginTool>(Object.entries(tools).flatMap(([pluginId, entries]) => entries.map(tool => [`${pluginId}-${tool.name}`, tool] as [string, PluginTool])))
}

type ToolContent = { type: string, text?: string, data?: string, mimeType?: string, resource?: { uri?: string, text?: string, blob?: string, mimeType?: string }, uri?: string, name?: string }

async function storeToolBlobs(chatId: string, content: ToolContent[]): Promise<ToolResultItem[]> {
  const result: ToolResultItem[] = []
  for (const item of content) {
    if (item.type === 'text') {
      result.push({ type: 'text', text: item.text ?? '' })
      continue
    }
    const resource = item.resource
    if (resource?.text) {
      result.push({ type: 'text', text: resource.text })
      continue
    }
    const encoded = resource?.blob ?? item.data
    if (!encoded) {
      result.push({ type: 'text', text: resource?.uri ?? item.uri ?? item.name ?? '' })
      continue
    }
    const id = genId()
    const mimeType = resource?.mimeType ?? item.mimeType ?? 'application/octet-stream'
    const name = resource?.uri?.split('/').at(-1) ?? item.name ?? 'tool-result'
    const file = new File([base64ToUint8Array(encoded)], name, { type: mimeType })
    await mutate(mutators.createItem({ id, parentId: chatId, name, mimeType })).client
    upload(id, file, name)
    result.push({ type: 'blob', mimeType, itemId: id })
  }
  return result
}

async function executeToolCalls(
  chat: FullChat,
  messageId: string,
  calls: ToolCall[],
  tools: CompletionConfig['tools'],
): Promise<ChatMessage[]> {
  const available = toolMap(tools)
  const assistantCalls = calls.map(call => ({
    id: call.id,
    type: 'function',
    function: { name: call.name, arguments: call.arguments },
  }))
  const messages: ChatMessage[] = [{ role: 'assistant', tool_calls: assistantCalls }]
  for (const call of calls) {
    const tool = available.get(call.name)
    if (!tool) {
      messages.push({ role: 'tool', tool_call_id: call.id, content: JSON.stringify({ error: 'Tool is unavailable' }) })
      continue
    }
    let value: unknown
    try {
      value = await tool.execute(JSON.parse(call.arguments || '{}'))
      const content = value && typeof value === 'object' && 'content' in value && Array.isArray(value.content)
        ? await storeToolBlobs(chat.id, value.content as ToolContent[])
        : value
      messages.push({ role: 'tool', tool_call_id: call.id, content: JSON.stringify(content) })
    } catch (error) {
      messages.push({ role: 'tool', tool_call_id: call.id, content: JSON.stringify({ error: String(error) }) })
    }
  }
  return messages
}

async function consumeResponse(response: Response, messageId: string, abortSignal: AbortSignal): Promise<ParsedResponse> {
  const contentType = response.headers.get('content-type') ?? ''
  const calls = new Map<number, ToolCall>()
  const warnings: string[] = []
  let text = ''
  let reasoning = ''
  let usage: ParsedResponse['usage']
  const push = (value: string) => { text += value; update(messageId, { text }) }
  const parsePart = (part: { choices?: Array<{ delta?: { content?: string, reasoning_content?: string, tool_calls?: Array<{ index?: number, id?: string, function?: { name?: string, arguments?: string } }> }, message?: { content?: string, tool_calls?: Array<{ id?: string, function?: { name?: string, arguments?: string } }> } }>, usage?: { prompt_tokens?: number, completion_tokens?: number }, warnings?: string[] }) => {
    const choice = part.choices?.[0]
    const content = choice?.delta?.content ?? choice?.message?.content
    if (content) push(content)
    const deltaReasoning = choice?.delta?.reasoning_content
    if (deltaReasoning) {
      reasoning += deltaReasoning
      update(messageId, { reasoning })
    }
    for (const call of choice?.delta?.tool_calls ?? []) {
      const index = call.index ?? 0
      const current = calls.get(index) ?? { id: call.id ?? genId(), name: '', arguments: '' }
      current.id = call.id ?? current.id
      current.name += call.function?.name ?? ''
      current.arguments += call.function?.arguments ?? ''
      calls.set(index, current)
    }
    for (const call of choice?.message?.tool_calls ?? []) calls.set(calls.size, { id: call.id ?? genId(), name: call.function?.name ?? '', arguments: call.function?.arguments ?? '' })
    if (part.usage) {
      usage = { inputTokens: part.usage.prompt_tokens ?? 0, outputTokens: part.usage.completion_tokens ?? 0 }
      update(messageId, { usage })
    }
    if (part.warnings) warnings.push(...part.warnings)
  }
  if (!contentType.includes('text/event-stream')) {
    parsePart(await response.json() as Parameters<typeof parsePart>[0])
  } else {
    if (!response.body) throw new Error('Model gateway returned no stream')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      if (abortSignal.aborted) { await reader.cancel(); throw new DOMException('Aborted', 'AbortError') }
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        const value = line.trim()
        if (!value.startsWith('data:') || value.slice(5).trim() === '[DONE]') continue
        try { parsePart(JSON.parse(value.slice(5).trim()) as Parameters<typeof parsePart>[0]) } catch { /* keepalive */ }
      }
    }
  }
  return { toolCalls: [...calls.values()], usage, warnings }
}

export const streamChat = withTask(async (
  { abortSignal },
  { chat, config }: { chat: FullChat, config: CompletionConfig },
) => {
  const messageId = getChatChain(chat).at(-2)!
  start(messageId, { reasoning: '', text: '' }, updates => mutate(mutators.updateAssistantMessage({ id: messageId, ...updates })), { type: 'throttle', wait: 2000 })
  const messages = messagesFor(chat, config)
  const definitions = toolDefinitions(config.tools)
  for (let step = 0; step < 5; step++) {
    const response = await fetch('/api/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Workspace-Id': chat.rootId },
      credentials: 'include',
      body: JSON.stringify({ stream: true, messages, tools: definitions.length ? definitions : undefined }),
      signal: abortSignal,
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as { error?: string }
      const error = payload.error ?? 'Managed model capability is unavailable'
      mutate(mutators.updateAssistantMessage({ id: messageId, error }))
      throw new Error(error)
    }
    const result = await consumeResponse(response, messageId, abortSignal)
    if (!result.toolCalls.length) {
      if (result.warnings?.length) await mutate(mutators.updateAssistantMessage({ id: messageId, warnings: result.warnings })).client
      finish(messageId)
      await mutate(mutators.updateAssistantMessage({ id: messageId })).client
      return
    }
    messages.push(...await executeToolCalls(chat, messageId, result.toolCalls, config.tools))
  }
  throw new Error('The managed tool loop exceeded its step limit')
})
