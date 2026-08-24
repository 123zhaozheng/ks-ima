import { afterEach, describe, expect, test } from 'bun:test'
import type { Citation } from './retrieve'
import { answerQuestion, KNOWLEDGE_GAP_ANSWER } from './answer'

const citations: Citation[] = [{
  entityId: 'file-1',
  type: 'item',
  title: '员工手册.pdf',
  path: '人事/员工手册.pdf',
  quote: '年假为每年十天。',
  score: 0.9,
}]

let server: ReturnType<typeof Bun.serve> | undefined
afterEach(() => {
  server?.stop(true)
  server = undefined
})

describe('knowledge answer generation', () => {
  test('returns a fixed knowledge gap without calling a model', async () => {
    let called = false
    const result = await answerQuestion('不存在的问题', [], null, {
      fetch: () => {
        called = true
        return Promise.reject(new Error('must not be called'))
      },
    })
    expect(result).toEqual({ answer: KNOWLEDGE_GAP_ANSWER, knowledgeGap: true })
    expect(called).toBe(false)
  })

  test('calls an OpenAI-compatible intranet gateway with grounded context', async () => {
    let body: any
    let authorization: string | null = null
    server = Bun.serve({
      port: 0,
      async fetch(request) {
        body = await request.json()
        authorization = request.headers.get('authorization')
        return Response.json({
          choices: [{ message: { content: '员工每年有十天年假。[1]' } }],
        })
      },
    })
    const result = await answerQuestion('年假有几天？', citations, {
      name: 'intranet-chat',
      baseURL: `http://127.0.0.1:${server.port}/v1`,
      apiKey: 'secret',
    })
    expect(result).toEqual({ answer: '员工每年有十天年假。[1]', knowledgeGap: false })
    expect(String(authorization)).toBe('Bearer secret')
    expect(body.model).toBe('intranet-chat')
    expect(body.messages[1].content).toContain('年假为每年十天。')
  })

  test('falls back to citation text when the gateway fails', async () => {
    server = Bun.serve({
      port: 0,
      fetch: () => new Response('unavailable', { status: 503 }),
    })
    const result = await answerQuestion('年假有几天？', citations, {
      name: 'intranet-chat',
      baseURL: `http://127.0.0.1:${server.port}/v1`,
      apiKey: '',
    })
    expect(result.knowledgeGap).toBe(false)
    expect(result.answer).toContain('模型服务暂不可用')
    expect(result.answer).toContain('年假为每年十天。')
  })

  test('falls back to citation text when no chat model is configured', async () => {
    const result = await answerQuestion('年假有几天？', citations, null)
    expect(result).toEqual({
      answer: expect.stringContaining('年假为每年十天。'),
      knowledgeGap: false,
    })
  })

  test('aborts a slow gateway and returns grounded citations', async () => {
    server = Bun.serve({
      port: 0,
      async fetch() {
        await Bun.sleep(100)
        return Response.json({ choices: [{ message: { content: 'late' } }] })
      },
    })
    const result = await answerQuestion('年假有几天？', citations, {
      name: 'intranet-chat',
      baseURL: `http://127.0.0.1:${server.port}/v1`,
      apiKey: '',
    }, { timeoutMs: 10 })
    expect(result.answer).toContain('模型服务暂不可用')
    expect(result.answer).toContain('年假为每年十天。')
  })
})
