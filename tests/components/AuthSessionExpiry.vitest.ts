import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { groundedClient } from 'src/api/grounded-client'
import { imaClient } from 'src/api/ima-client'
import { identityClient, session, type IdentityUser } from 'src/utils/identity-client'

const sessionUser: IdentityUser = {
  id: 'user-1',
  email: 'user@example.com',
  displayName: 'Test User',
  isActive: true,
  platformRoles: [],
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input
  return input instanceof URL ? input.href : input.url
}

async function waitForSessionData(expected: unknown) {
  await vi.waitFor(() => expect(session.value.data).toEqual(expected))
}

describe('session expiry handling', () => {
  beforeEach(() => {
    session.value = { isPending: false, error: null, data: { user: sessionUser } }
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('revalidates and clears the session for an SSE 401', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input)
      return Promise.resolve(url.includes('/auth/session')
        ? jsonResponse({ detail: 'Authentication is required' }, 401)
        : jsonResponse({ detail: 'Authentication is required', code: 'HTTP_401' }, 401))
    }))

    await expect(groundedClient.ask('kb-1', { question: 'hello' }, new AbortController().signal, vi.fn()))
      .rejects.toMatchObject({ name: 'IMAApiError' })
    await waitForSessionData(null)
  })

  it('revalidates and clears the session for a system-info 401', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input)
      return Promise.resolve(url.includes('/auth/session')
        ? jsonResponse({ detail: 'Authentication is required' }, 401)
        : jsonResponse({ detail: 'Authentication is required', code: 'HTTP_401' }, 401))
    }))

    await expect(imaClient.getSystemInfo()).rejects.toMatchObject({ name: 'IMAApiError' })
    await waitForSessionData(null)
  })

  // The first router import compiles the lazy admin shell; under the full
  // parallel suite that cold import can exceed Vitest's five-second default.
  it('redirects unauthenticated protected routes and preserves the target', async () => {
    vi.stubGlobal('__QUASAR_SSR_SERVER__', false)
    vi.stubGlobal('__QUASAR_SSR_CLIENT__', true)
    vi.stubGlobal('__QUASAR_SSR_PWA__', false)
    vi.stubGlobal('__QUASAR_SSR__', false)
    vi.stubGlobal('__QUASAR_VERSION__', '2.16.0')
    const { default: router } = await import('src/router')
    session.value = { isPending: false, error: null, data: null }

    await router.push('/admin/audit?tab=events')

    expect(router.currentRoute.value.path).toBe('/auth/sign-in')
    expect(router.currentRoute.value.query.redirect).toBe('/admin/audit?tab=events')
  }, 15000)

  it('keeps a valid session after a recent-auth 401', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const url = requestUrl(input)
      return Promise.resolve(url.includes('/auth/session')
        ? jsonResponse(sessionUser)
        : jsonResponse({ detail: 'Recent authentication is required', code: 'HTTP_401' }, 401))
    }))

    const result = await identityClient.profile()
    expect(result.error?.code).toBe('HTTP_401')
    await waitForSessionData({ user: sessionUser })
  })
})

export {}
