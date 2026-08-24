import type { Citation } from './retrieve'
import type { GatewayModel } from './models'

export const KNOWLEDGE_GAP_ANSWER = '知识库未收录相关内容。请补充文件后再问。'
const DEFAULT_TIMEOUT_MS = 20_000
type Fetcher = (input: string | URL | Request, init?: RequestInit) => Promise<Response>

function citationText(citations: Citation[]) {
  return citations.map((citation, index) =>
    `[${index + 1}] ${citation.path || citation.title || citation.entityId}\n${citation.quote}`,
  ).join('\n\n')
}

function citationFallback(citations: Citation[]) {
  return `模型服务暂不可用。以下是知识库检索到的相关原文：\n\n${citationText(citations)}`
}

function completionsUrl(baseURL: string) {
  return `${baseURL.replace(/\/$/, '')}/chat/completions`
}

export async function answerQuestion(
  question: string,
  citations: Citation[],
  gateway: GatewayModel | null,
  options: { timeoutMs?: number, fetch?: Fetcher } = {},
): Promise<{ answer: string, knowledgeGap: boolean }> {
  if (!citations.length) {
    return { answer: KNOWLEDGE_GAP_ANSWER, knowledgeGap: true }
  }
  if (!gateway) {
    return { answer: citationFallback(citations), knowledgeGap: false }
  }

  const fetcher: Fetcher = options.fetch ?? fetch
  const signal = AbortSignal.timeout(options.timeoutMs ?? DEFAULT_TIMEOUT_MS)
  const context = citationText(citations)
  try {
    const response = await fetcher(completionsUrl(gateway.baseURL), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(gateway.apiKey ? { Authorization: `Bearer ${gateway.apiKey}` } : {}),
      },
      signal,
      body: JSON.stringify({
        model: gateway.name,
        stream: false,
        temperature: 0.1,
        messages: [
          {
            role: 'system',
            content: '你是企业知识库助手。只能根据提供的知识库原文回答，不得补充原文中没有的事实。用 [1]、[2] 标注引用；证据不足时明确说明。',
          },
          {
            role: 'user',
            content: `问题：${question}\n\n知识库原文：\n${context}`,
          },
        ],
      }),
    })
    if (!response.ok) throw new Error(`Gateway returned ${response.status}`)
    const data = await response.json() as {
      choices?: Array<{ message?: { content?: string } }>
    }
    const answer = data.choices?.[0]?.message?.content?.trim()
    if (!answer) throw new Error('Gateway returned an empty answer')
    return { answer, knowledgeGap: false }
  } catch {
    return { answer: citationFallback(citations), knowledgeGap: false }
  }
}
