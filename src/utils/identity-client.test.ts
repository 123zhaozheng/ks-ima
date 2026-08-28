import { afterAll, describe, expect, mock, test } from 'bun:test'
import { GlobalRegistrator } from '@happy-dom/global-registrator'
import { identityClient } from './identity-client'

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
    const result = await identityClient.createServicePrincipal('w1', {
      displayName: 'CI',
      purpose: 'Automation',
      ownerUserId: 'u1',
      folderRootId: null,
      scopes: ['mcp:knowledge:read'],
      expiresAt: new Date(Date.now() + 86400000).toISOString(),
      rateLimit: 10,
      concurrencyLimit: 2,
      cidrAllowlist: [],
    })
    expect(result.data?.secret).toBe('one-time-secret')
    expect(JSON.stringify(localStorage)).not.toContain('one-time-secret')
    expect(JSON.stringify(sessionStorage)).not.toContain('one-time-secret')
    const call = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(call[0]).toBe('/api/v1/workspaces/w1/service-principals')
    expect(new Headers(call[1].headers).get('X-CSRF-Token')).toBe('test-csrf')
  })
})
