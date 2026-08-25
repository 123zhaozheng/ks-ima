import { afterEach, beforeEach, expect, test } from 'bun:test'

const originalFetch = globalThis.fetch
const originalUrl = process.env.PYTHON_API_INTERNAL_URL
const originalToken = process.env.IMA_BRIDGE_TOKEN

beforeEach(() => {
  process.env.PYTHON_API_INTERNAL_URL = 'http://python.internal:8000'
  process.env.IMA_BRIDGE_TOKEN = 'bridge-secret'
})
afterEach(() => {
  globalThis.fetch = originalFetch
  if (originalUrl === undefined) delete process.env.PYTHON_API_INTERNAL_URL
  else process.env.PYTHON_API_INTERNAL_URL = originalUrl
  if (originalToken === undefined) delete process.env.IMA_BRIDGE_TOKEN
  else process.env.IMA_BRIDGE_TOKEN = originalToken
})

test('target resolution returns opaque binding metadata only', async () => {
  globalThis.fetch = ((_input, init) => {
    expect(init?.redirect).toBe('error')
    expect((init?.headers as Record<string, string>)['x-ima-bridge-token']).toBe('bridge-secret')
    return new Response(JSON.stringify({
      source: 'target',
      workflow: 'grounded_ask',
      profileId: 'p',
      profileVersion: 3,
      bindingId: 'binding',
    }), { status: 200, headers: { 'content-type': 'application/json' } })
  }) as unknown as typeof fetch
  const { resolveManagedStatus } = await import(`./model-governance?target=${Date.now()}`)
  const result = await resolveManagedStatus('workspace', 'grounded_ask', 'chat')
  expect(result).toMatchObject({ source: 'target', bindingId: 'binding' })
  expect(result).not.toHaveProperty('apiKey')
  expect(result).not.toHaveProperty('gatewayBaseUrl')
})

test('target denial is terminal while no assignment is the only legacy fallback signal', async () => {
  globalThis.fetch = (() => new Response(JSON.stringify({ source: 'denied', reason: 'UNAVAILABLE' }), { status: 200 })) as unknown as typeof fetch
  const { resolveManagedStatus } = await import(`./model-governance?denied=${Date.now()}`)
  expect(await resolveManagedStatus('workspace', 'grounded_ask', 'chat')).toMatchObject({ source: 'denied' })

  globalThis.fetch = (() => new Response(JSON.stringify({ source: 'denied', reason: 'NO_ASSIGNMENT' }), { status: 200 })) as unknown as typeof fetch
  const second = await import(`./model-governance?unmigrated=${Date.now()}`)
  expect(await second.resolveManagedStatus('workspace', 'grounded_ask', 'chat')).toMatchObject({ source: 'unmigrated' })
})

test('managed execution sends workflow/messages to Python and never receives gateway material', async () => {
  const calls: RequestInit[] = []
  globalThis.fetch = ((input, init) => {
    calls.push(init ?? {})
    const path = String(input)
    if (path.endsWith('/resolve')) {
      return Promise.resolve(new Response(JSON.stringify({ source: 'target', workflow: 'title_generation', bindingId: 'b1' }), { status: 200 }))
    }
    return Promise.resolve(new Response(JSON.stringify({ choices: [{ message: { content: 'A title' } }] }), { status: 200 }))
  }) as unknown as typeof fetch
  const { executeManagedChat } = await import(`./model-governance?execute=${Date.now()}`)
  const result = await executeManagedChat('workspace', 'title_generation', [{ role: 'user', content: 'hello' }])
  expect(result.kind).toBe('target')
  expect(await result.response?.json()).toMatchObject({ choices: [{ message: { content: 'A title' } }] })
  expect(calls).toHaveLength(2)
  expect(JSON.stringify(calls[1])).not.toContain('gatewaySecret')
  expect(JSON.stringify(calls[1])).not.toContain('gatewayBaseUrl')
})

test('model bridge rejects public Python origins before any request', async () => {
  process.env.PYTHON_API_INTERNAL_URL = 'https://public.example.invalid'
  let called = false
  globalThis.fetch = (() => {
    called = true
    return Promise.resolve(new Response('{}', { status: 200 }))
  }) as unknown as typeof fetch
  const { resolveManagedStatus } = await import(`./model-governance?private=${Date.now()}`)
  expect(await resolveManagedStatus('workspace', 'grounded_ask', 'chat')).toMatchObject({ source: 'denied', reason: 'BRIDGE_UNAVAILABLE' })
  expect(called).toBe(false)
})
