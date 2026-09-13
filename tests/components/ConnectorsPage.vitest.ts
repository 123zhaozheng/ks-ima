import { flushPromises, mount } from '@vue/test-utils'
import type * as Quasar from 'quasar'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import ConnectorsPage from 'src/pages/ConnectorsPage.vue'
import { identityClient, revalidateSession, session } from 'src/utils/identity-client'

vi.mock('quasar', async importOriginal => {
  const actual = await importOriginal<typeof Quasar>()
  return { ...actual, Notify: { create: () => '' }, copyToClipboard: () => Promise.resolve() }
})
vi.mock('src/stores/knowledge-base', () => ({
  useKbStore: () => ({ kbsStatus: 'loading', kbs: [] }),
}))
const { replaceMock } = vi.hoisted(() => ({ replaceMock: vi.fn() }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: replaceMock }),
  useRoute: () => ({ fullPath: '/connectors' }),
}))
vi.mock('src/utils/identity-client', async () => {
  // A real ref so the useRequireLogin watcher reacts to session changes.
  const { ref } = await import('vue')
  return {
    session: ref({ isPending: false, error: null, data: { user: { id: 'me' } } }),
    revalidateSession: vi.fn(() => Promise.resolve()),
    identityClient: {
      listConnectedOAuthGrants: vi.fn(),
      listServicePrincipals: vi.fn(),
      getServicePrincipal: vi.fn(),
      createServicePrincipal: vi.fn(),
      revokeServicePrincipal: vi.fn(),
      revokeConnectedOAuthGrant: vi.fn(),
    },
  }
})

/*
 * The connectors page reduces the old service-principal form to one click:
 * a fixed-payload key creation, a paste-ready MCP config block for two
 * client shapes, and a flat revocable key list.
 */

// Clicking the stubbed toggle always switches to the Claude Desktop shape.
const stubs = {
  'q-btn-toggle': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template:
      '<button data-testid="client-toggle" @click="$emit(\'update:modelValue\', \'claude\')">toggle</button>',
  },
}

const principal = {
  id: 'p-1',
  displayName: 'MCP 配置 2026-09-13 10:00',
  purpose: '连接器页面一键生成',
  ownerUserId: 'me',
  scopes: [
    'mcp:knowledge-bases:read',
    'mcp:knowledge:read',
    'mcp:knowledge:search',
    'mcp:knowledge:write',
  ],
  state: 'active',
  expiresAt: '2026-12-12T00:00:00Z',
  rateLimit: 300,
  concurrencyLimit: 10,
  cidrAllowlist: [],
}

const credential = {
  id: 'c-1',
  principalId: 'p-1',
  credentialId: 'key-1',
  secretPrefix: 'mcpsc_abc',
  expiresAt: '2099-01-01T00:00:00Z',
  createdAt: '2026-09-13T00:00:00Z',
  revokedAt: null,
  lastUsedAt: null,
}

function mountPage() {
  const dialog = vi.fn(() => ({ onOk: () => ({ onCancel: () => undefined }), onCancel: () => undefined }))
  return mount(ConnectorsPage, {
    global: { stubs, provide: { _q_: { notify: vi.fn(), dialog } } },
  })
}

async function generate(wrapper: Awaited<ReturnType<typeof mountPage>>, secret: string) {
  vi.mocked(identityClient.createServicePrincipal).mockResolvedValue({
    data: { secret, credential, principal },
  })
  await wrapper.find('button[data-testid="connectors-generate"]').trigger('click')
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(revalidateSession).mockImplementation(() => Promise.resolve())
  session.value = { isPending: false, error: null, data: { user: { id: 'me' } } } as never
  vi.mocked(identityClient.listConnectedOAuthGrants).mockResolvedValue({ data: [] })
  vi.mocked(identityClient.listServicePrincipals).mockResolvedValue({ data: [principal] })
  vi.mocked(identityClient.getServicePrincipal).mockResolvedValue({
    data: { ...principal, credentials: [credential] },
  })
})

describe('ConnectorsPage MCP 配置', () => {
  test('one click creates the key with the fixed payload and shows the HTTP config', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await generate(wrapper, 'mcpsc_secret-value-123')

    const payload = vi.mocked(identityClient.createServicePrincipal).mock.calls[0][0]
    expect(payload.purpose).toBe('连接器页面一键生成')
    expect(payload.ownerUserId).toBe('me')
    expect(payload.scopes).toEqual([
      'mcp:knowledge-bases:read',
      'mcp:knowledge:read',
      'mcp:knowledge:search',
      'mcp:knowledge:write',
    ])
    expect(payload.rateLimit).toBe(300)
    expect(payload.concurrencyLimit).toBe(10)
    expect(payload.cidrAllowlist).toEqual([])
    // Fixed 90-day expiry.
    expect(Date.parse(payload.expiresAt) - Date.now()).toBeGreaterThan(89 * 86400000)
    expect(payload.displayName).toContain('MCP 配置 ')

    const config = wrapper.get('[data-testid="connectors-config-json"]').text()
    expect(config).toContain('/mcp')
    expect(config).toContain('Bearer mcpsc_secret-value-123')
    // The list shows only the prefix, never the full secret.
    expect(wrapper.text()).toContain('mcpsc_abc')
  })

  test('switching to Claude Desktop shows the mcp-remote bridge form', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await generate(wrapper, 'mcpsc_secret-value-123')
    expect(wrapper.text()).not.toContain('mcp-remote')
    await wrapper.find('button[data-testid="client-toggle"]').trigger('click')
    await flushPromises()
    const config = wrapper.get('[data-testid="connectors-config-json"]').text()
    expect(config).toContain('mcp-remote')
    expect(config).toContain('Bearer mcpsc_secret-value-123')
  })

  test('key rows revoke through revokeServicePrincipal', async () => {
    vi.mocked(identityClient.revokeServicePrincipal).mockResolvedValue({ data: null })
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain('MCP 配置 2026-09-13 10:00')
    await wrapper.find('button[title="撤销"]').trigger('click')
    await flushPromises()
    expect(identityClient.revokeServicePrincipal).toHaveBeenCalledWith('p-1')
  })

  test('creation failure shows the error banner and keeps the generate button', async () => {
    vi.mocked(identityClient.createServicePrincipal).mockResolvedValue({
      data: undefined,
      error: { code: 'HTTP_429', message: 'rate' },
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('button[data-testid="connectors-generate"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('请求过于频繁，请稍后再试。')
    expect(wrapper.find('[data-testid="connectors-config-json"]').exists()).toBe(false)
    expect(wrapper.find('button[data-testid="connectors-generate"]').exists()).toBe(true)
  })

  test('recent-auth 401 asks for the password once and retries the creation', async () => {
    vi.mocked(identityClient.createServicePrincipal)
      .mockResolvedValueOnce({ error: { code: 'HTTP_401', message: 'Recent authentication is required' } })
      .mockResolvedValueOnce({ data: { secret: 'mcpsc_new-secret', credential, principal } })
    const dialog = vi.fn(() => ({
      onOk: (callback: (challenge?: string) => void) => {
        callback()
        return { onCancel: () => undefined }
      },
      onCancel: () => undefined,
    }))
    const wrapper = mount(ConnectorsPage, {
      global: { stubs, provide: { _q_: { notify: vi.fn(), dialog } } },
    })
    await flushPromises()
    await wrapper.find('button[data-testid="connectors-generate"]').trigger('click')
    await flushPromises()
    expect(dialog).toHaveBeenCalledTimes(1)
    expect(identityClient.createServicePrincipal).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="connectors-config-json"]').text()).toContain('Bearer mcpsc_new-secret')
  })

  test('dead-session 401 redirects to sign-in without opening the reauth dialog', async () => {
    vi.mocked(identityClient.createServicePrincipal).mockResolvedValue({
      error: { code: 'HTTP_401', message: 'Authentication is required' },
    })
    vi.mocked(revalidateSession).mockImplementation(() => {
      session.value = { isPending: false, error: null, data: null } as never
      return Promise.resolve()
    })
    const dialog = vi.fn(() => ({
      onOk: () => ({ onCancel: () => undefined }),
      onCancel: () => undefined,
    }))
    const wrapper = mount(ConnectorsPage, {
      global: { stubs, provide: { _q_: { notify: vi.fn(), dialog } } },
    })
    await flushPromises()
    await wrapper.find('button[data-testid="connectors-generate"]').trigger('click')
    await flushPromises()
    expect(dialog).not.toHaveBeenCalled()
    expect(replaceMock).toHaveBeenCalledWith({ path: '/auth/sign-in', query: { redirect: '/connectors' } })
    expect(wrapper.find('[data-testid="connectors-config-json"]').exists()).toBe(false)
  })
})
