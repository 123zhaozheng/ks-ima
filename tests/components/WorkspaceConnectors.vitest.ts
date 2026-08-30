import { mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { nextTick, reactive } from 'vue'
import WorkspaceConnectors from '../../src/pages/WorkspaceConnectors.vue'

const workspaceState = reactive({ id: 'w1' as string | null })
const principal = { id: 'p1', workspaceId: 'w1', folderRootId: null, displayName: 'Indexer', purpose: 'Nightly indexing', ownerUserId: 'u1', scopes: ['mcp:knowledge:read'], state: 'active', expiresAt: '2030-01-01T00:00:00Z', rateLimit: 10, concurrencyLimit: 2, cidrAllowlist: [] }
const credential = { id: 'c1', principalId: 'p1', credentialId: 'key1', secretPrefix: 'mcpsc_', expiresAt: '2030-01-01T00:00:00Z', createdAt: '', revokedAt: null, lastUsedAt: null }
vi.mock('src/stores/workspace', () => ({ useWorkspaceStore: () => workspaceState }))
vi.mock('quasar', () => ({
  copyToClipboard: vi.fn(),
  useQuasar: () => ({ notify: vi.fn() }),
}))

function response(url: string, role = 'workspace_admin') {
  if (url.endsWith('/oauth/grants')) return []
  if (url.endsWith('/workspaces/w1/service-principals')) return [principal]
  if (url.endsWith('/workspaces/w1/service-principals/p1')) return { ...principal, credentials: [credential] }
  if (url.endsWith('/workspaces/w1')) return { id: 'w1', name: 'Workspace', role, isActive: true, createdAt: '', updatedAt: '' }
  return {}
}

describe('WorkspaceConnectors service access', () => {
  test('renders safe principal metadata and admin controls without legacy keys', async () => {
    globalThis.fetch = vi.fn((input) => Promise.resolve(new Response(JSON.stringify(response(String(input))), { status: 200 }))) as unknown as typeof fetch
    const wrapper = mount(WorkspaceConnectors)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Indexer')
    expect(wrapper.text()).toContain('Nightly indexing')
    expect(wrapper.text()).toContain('Create service principal')
    expect(wrapper.text()).not.toContain('Legacy connectors')
    expect(wrapper.text()).not.toContain('ima_')
    expect(wrapper.text()).not.toContain('one-time-secret')
  })

  test('viewer receives guidance but no mutation controls', async () => {
    const fetchMock = vi.fn((input) => Promise.resolve(new Response(JSON.stringify(response(String(input), 'viewer')), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(WorkspaceConnectors)
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('/mcp')
    expect(wrapper.text()).not.toContain('Create service principal')
    expect(wrapper.find('button[title="Revoke"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.every(call => !String(call[0]).endsWith('/service-principals'))).toBe(true)
  })

  test('one-time secret disappears when dismissed', async () => {
    globalThis.fetch = vi.fn((input) => Promise.resolve(new Response(JSON.stringify(response(String(input))), { status: 200 }))) as unknown as typeof fetch
    const wrapper = mount(WorkspaceConnectors)
    await new Promise(resolve => setTimeout(resolve, 0))
    const vm = wrapper.vm as unknown as { oneTime: unknown }
    vm.oneTime = {
      secret: 'one-time-secret',
      credential: { id: 'c1', principalId: 'p1', credentialId: 'key1', secretPrefix: 'mcpsc_', expiresAt: '2030-01-01T00:00:00Z', createdAt: '', revokedAt: null, lastUsedAt: null },
      principal: response('/api/v1/workspaces/w1/service-principals')[0],
    }
    await nextTick()
    expect(wrapper.text()).toContain('one-time-secret')
    vm.oneTime = null
    await nextTick()
    expect(wrapper.text()).not.toContain('one-time-secret')
  })

  test('workspace change clears an undisposed one-time secret', async () => {
    globalThis.fetch = vi.fn((input) => Promise.resolve(new Response(JSON.stringify(response(String(input))), { status: 200 }))) as unknown as typeof fetch
    const wrapper = mount(WorkspaceConnectors)
    const vm = wrapper.vm as unknown as { oneTime: unknown }
    vm.oneTime = { secret: 'workspace-a-secret' }
    workspaceState.id = 'w2'
    await nextTick()
    expect(vm.oneTime).toBeNull()
    expect(wrapper.text()).not.toContain('workspace-a-secret')
    workspaceState.id = 'w1'
  })

  test('revokes the selected credential through the typed endpoint', async () => {
    const requests: Array<{ url: string, method?: string }> = []
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      requests.push({ url, method: init?.method })
      return Promise.resolve(new Response(JSON.stringify(response(url)), { status: 200 }))
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(WorkspaceConnectors)
    await new Promise(resolve => setTimeout(resolve, 0))
    await wrapper.find('button[title="Revoke credential"]').trigger('click')
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(requests.some(request =>
      request.url.endsWith('/workspaces/w1/service-principals/p1/credentials/key1') &&
      request.method === 'DELETE',
    )).toBe(true)
  })
})
