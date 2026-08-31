import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import KbMembersPanel from 'src/components/KbMembersPanel.vue'
import KbShareLinksPanel from 'src/components/KbShareLinksPanel.vue'
import { identityClient, session } from 'src/utils/identity-client'

// The Notify/copy utilities need the installed Quasar plugin; stub them out
// while keeping the rest of quasar (useQuasar, components) real.
vi.mock('quasar', async importOriginal => {
  const actual = await importOriginal<typeof import('quasar')>()
  return { ...actual, Notify: { create: () => '' }, copyToClipboard: async () => undefined }
})

// The store pulls in vue-router; the panels only need its id fallback hook.
vi.mock('src/stores/knowledge-base', () => ({ useKbStore: () => ({ id: null }) }))
vi.mock('src/utils/identity-client', () => ({
  session: { value: { isPending: false, error: null, data: { user: { id: 'me' } } } },
  identityClient: {
    listKbMembers: vi.fn(),
    updateKbMemberRole: vi.fn(),
    removeKbMember: vi.fn(),
    leaveKnowledgeBase: vi.fn(),
    listKbShareLinks: vi.fn(),
    createKbShareLink: vi.fn(),
    revokeKbShareLink: vi.fn(),
  },
}))

const stubs = {
  'q-menu': { template: '<div><slot /></div>' },
  'q-avatar': { template: '<span><slot /></span>' },
  'q-btn-toggle': { template: '<div />' },
}

const vueQuery = [VueQueryPlugin, { queryClient: new QueryClient({ defaultOptions: { queries: { retry: false } } }) }] as [typeof VueQueryPlugin, { queryClient: QueryClient }]

function mountMembers(props: { kbId: string, isOwner: boolean }) {
  return mount(KbMembersPanel, { props, global: { plugins: [vueQuery], stubs } })
}

function mountLinks(props: { kbId: string }) {
  return mount(KbShareLinksPanel, { props, global: { plugins: [vueQuery], stubs } })
}

beforeEach(() => {
  vi.clearAllMocks()
  session.value = { isPending: false, error: null, data: { user: { id: 'me' } } } as never
})

describe('KbMembersPanel', () => {
  test('owner sees role badges and management menus, but not for themselves', async () => {
    vi.mocked(identityClient.listKbMembers).mockResolvedValue({
      data: [
        { kbId: 'kb1', userId: 'me', role: 'owner', state: 'active', version: 1, displayName: 'Me', email: 'me@test' },
        { kbId: 'kb1', userId: 'u2', role: 'editor', state: 'active', version: 2, displayName: 'Ed', email: 'ed@test' },
        { kbId: 'kb1', userId: 'u3', role: 'viewer', state: 'active', version: 3, displayName: 'Vera', email: 'vera@test' },
      ],
    })
    const wrapper = mountMembers({ kbId: 'kb1', isOwner: true })
    await flushPromises()
    expect(wrapper.text()).toContain('所有者')
    expect(wrapper.text()).toContain('编辑者')
    expect(wrapper.text()).toContain('浏览者')
    expect(wrapper.text()).toContain('你')
    // Only the two non-self members get management menus.
    expect(wrapper.findAll('[data-testid="kb-member-menu"]')).toHaveLength(2)
    // Owners never see the leave action.
    expect(wrapper.find('[data-testid="kb-leave"]').exists()).toBe(false)
  })

  test('non-owner members get a read-only list and a leave action', async () => {
    vi.mocked(identityClient.listKbMembers).mockResolvedValue({
      data: [
        { kbId: 'kb1', userId: 'owner-1', role: 'owner', state: 'active', version: 1, displayName: 'Olive', email: 'olive@test' },
        { kbId: 'kb1', userId: 'me', role: 'viewer', state: 'active', version: 2, displayName: 'Me', email: 'me@test' },
      ],
    })
    const wrapper = mountMembers({ kbId: 'kb1', isOwner: false })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="kb-member-menu"]')).toHaveLength(0)
    expect(wrapper.find('[data-testid="kb-leave"]').exists()).toBe(true)
  })
})

describe('KbShareLinksPanel', () => {
  test('lists links with state; only active links can be revoked', async () => {
    vi.mocked(identityClient.listKbShareLinks).mockResolvedValue({
      data: [
        { id: 'l1', kbId: 'kb1', role: 'viewer', createdAt: '2026-08-01T00:00:00Z', expiresAt: null, revokedAt: null },
        { id: 'l2', kbId: 'kb1', role: 'editor', createdAt: '2026-08-02T00:00:00Z', expiresAt: null, revokedAt: '2026-08-03T00:00:00Z' },
      ],
    })
    const wrapper = mountLinks({ kbId: 'kb1' })
    await flushPromises()
    expect(wrapper.text()).toContain('只读')
    expect(wrapper.text()).toContain('可编辑')
    expect(wrapper.text()).toContain('已撤销')
    expect(wrapper.text()).toContain('永不过期')
    expect(wrapper.findAll('[data-testid="share-link-revoke"]')).toHaveLength(1)
  })

  test('creates a viewer share link and shows the one-time URL', async () => {
    vi.mocked(identityClient.listKbShareLinks).mockResolvedValue({ data: [] })
    vi.mocked(identityClient.createKbShareLink).mockResolvedValue({
      data: { id: 'l3', kbId: 'kb1', role: 'viewer', url: 'https://ima.test/join/token-123', createdAt: '2026-08-31T00:00:00Z', expiresAt: null },
    })
    const wrapper = mountLinks({ kbId: 'kb1' })
    await flushPromises()
    await wrapper.find('[data-testid="share-link-create"]').trigger('click')
    await flushPromises()
    expect(identityClient.createKbShareLink).toHaveBeenCalledWith('kb1', { role: 'viewer', expiresInDays: null })
    const urlInput = wrapper.find('[data-testid="share-link-url"]')
    expect(urlInput.exists()).toBe(true)
    expect(urlInput.attributes('model-value')).toBe('https://ima.test/join/token-123')
    expect(wrapper.find('[data-testid="share-link-copy"]').exists()).toBe(true)
  })
})
