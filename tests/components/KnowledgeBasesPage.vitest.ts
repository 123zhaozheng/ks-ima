import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import KnowledgeBasesPage from '../../src/admin/pages/KnowledgeBasesPage.vue'
import { session } from 'src/utils/identity-client'

const Stub = defineComponent({ template: '<div><slot /></div>' })
const TableStub = defineComponent({ props: { rows: { type: Array, default: () => [] } }, template: '<div><div v-for="row in rows" :key="row.id">{{ row.name }}</div><slot /></div>' })
const stubs = { 'q-page-container': Stub, 'q-page': Stub, 'q-input': Stub, 'q-btn': Stub, 'q-table': TableStub, 'q-td': Stub, 'q-banner': Stub }

function mockFetch(items: unknown[]) {
  const fetchMock = vi.fn((..._args: unknown[]) => Promise.resolve(new Response(JSON.stringify({ items, nextCursor: null }), { status: 200 })))
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return fetchMock
}

describe('KnowledgeBasesPage', () => {
  test('lists knowledge bases from the admin endpoint', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'super', email: 'super@test', displayName: 'Super', platformRoles: ['super_admin'], isActive: true } } }
    const fetchMock = mockFetch([
      { id: 'kb1', name: 'Engineering', isActive: true, createdAt: '2026-08-31T00:00:00Z', updatedAt: '2026-08-31T00:00:00Z' },
      { id: 'kb2', name: 'Archived Library', isActive: false, archivedAt: '2026-08-31T00:00:00Z', createdAt: '2026-08-30T00:00:00Z', updatedAt: '2026-08-31T00:00:00Z' },
    ])
    const wrapper = mount(KnowledgeBasesPage, { global: { stubs } })
    await flushPromises()
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain('/api/v1/admin/knowledge-bases')
    expect(wrapper.text()).toContain('Engineering')
    expect(wrapper.text()).toContain('Archived Library')
  })

  test('keeps management controls hidden without an admin role', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'auditor', email: 'auditor@test', displayName: 'Auditor', platformRoles: ['security_auditor'], isActive: true } } }
    mockFetch([])
    const wrapper = mount(KnowledgeBasesPage, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('New knowledge base')
    expect(wrapper.text()).not.toContain('Initial owner user ID')
  })
})
