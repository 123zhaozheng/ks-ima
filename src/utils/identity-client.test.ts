import { afterAll, describe, expect, mock, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { IMAApiError, imaClient } from '../api/ima-client'
import { identityClient, session } from './identity-client'

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.href : input.url
}

const originalFetch = globalThis.fetch
GlobalRegistrator.register()
afterAll(() => { globalThis.fetch = originalFetch; GlobalRegistrator.unregister() })

describe('identity client', () => {
  test('adds CSRF token to unsafe generated API requests', async () => {
    document.cookie = 'ima_csrf=test-csrf'
    const fetchMock = mock(() => Promise.resolve(new Response(JSON.stringify({ changed: true }), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    await identityClient.changePassword({ currentPassword: 'old', password: 'new-password-123' })
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    const request = call[1]
    expect(new Headers(request.headers).get('X-CSRF-Token')).toBe('test-csrf')
  })

  test('returns typed error responses without leaking response internals', async () => {
    globalThis.fetch = mock(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Denied', code: 'IDENTITY_ERROR' }), { status: 403 }))) as unknown as typeof fetch
    const result = await identityClient.updateProfile({ displayName: 'Denied' })
    expect(result.error).toEqual({ code: 'IDENTITY_ERROR', message: 'Denied' })
    expect(result.data).toBeUndefined()
  })

  test('service credential stays in the one response and is never persisted', async () => {
    localStorage.clear(); sessionStorage.clear()
    const payload = { secret: 'one-time-secret', credential: { id: 'c1' }, principal: { id: 'p1' } }
    const fetchMock = mock(() => Promise.resolve(new Response(JSON.stringify(payload), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const result = await identityClient.createServicePrincipal({
      displayName: 'CI',
      purpose: 'Automation',
      ownerUserId: 'u1',
      scopes: ['mcp:knowledge-bases:read'],
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      rateLimit: 10,
      concurrencyLimit: 2,
      cidrAllowlist: [],
    })
    expect(result.data?.secret).toBe('one-time-secret')
    expect(JSON.stringify(localStorage)).not.toContain('one-time-secret')
    expect(JSON.stringify(sessionStorage)).not.toContain('one-time-secret')
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/service-principals')
    expect(new Headers(call[1].headers).get('X-CSRF-Token')).toBe('test-csrf')
  })

  test('re-checks the session on 401 and clears it when expired', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'u1' } as never } }
    const fetchMock = mock(() => Promise.resolve(
      new Response(JSON.stringify({ detail: 'Authentication is required', code: 'HTTP_401' }), { status: 401 }),
    ))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    await identityClient.profile()
    await new Promise(resolve => setTimeout(resolve, 0))
    const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL][]
    expect(calls.some(call => requestUrl(call[0]).includes('/auth/session'))).toBe(true)
    expect(session.value.data).toBeNull()
  })

  test('keeps a still-valid session when the 401 only demands recent auth', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'u1' } as never } }
    globalThis.fetch = mock((input: RequestInfo | URL) => Promise.resolve(
      requestUrl(input).includes('/auth/session')
        ? new Response(JSON.stringify({ id: 'u1' }), { status: 200 })
        : new Response(JSON.stringify({ detail: 'Recent authentication is required', code: 'HTTP_401' }), { status: 401 }),
    )) as unknown as typeof fetch
    await identityClient.profile()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(session.value.data?.user.id).toBe('u1')
  })

  test('concurrent 401 responses share one session re-check', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'u1' } as never } }
    const fetchMock = mock(() => Promise.resolve(
      new Response(JSON.stringify({ detail: 'Authentication is required', code: 'HTTP_401' }), { status: 401 }),
    ))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    await Promise.all([identityClient.profile(), identityClient.listSessions()])
    await new Promise(resolve => setTimeout(resolve, 0))
    const calls = fetchMock.mock.calls as unknown as [RequestInfo | URL][]
    expect(calls.filter(call => requestUrl(call[0]).includes('/auth/session'))).toHaveLength(1)
    expect(session.value.data).toBeNull()
  })

  test('ima client 401 re-checks the session as well', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'u1' } as never } }
    globalThis.fetch = mock((input: RequestInfo | URL) => Promise.resolve(
      requestUrl(input).includes('/auth/session')
        ? new Response(JSON.stringify({ detail: 'Authentication is required' }), { status: 401 })
        : new Response(JSON.stringify({ detail: 'Authentication is required', code: 'HTTP_401' }), { status: 401 }),
    )) as unknown as typeof fetch
    let thrown: unknown
    try {
      await imaClient.request('/api/v1/conversations')
    } catch (error) {
      thrown = error
    }
    expect(thrown).toBeInstanceOf(IMAApiError)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(session.value.data).toBeNull()
  })
})
