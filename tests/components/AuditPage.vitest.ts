import { mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import AuditPage from '../../src/admin/pages/AuditPage.vue'

const Stub = defineComponent({ template: '<div><slot /></div>' })


describe('AuditPage', () => {
  test('renders the read-only audit table with typed events', async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) => Promise.resolve(new Response(JSON.stringify({ items: [{ id: 1, action: 'user.created', result: 'success', metadata: {}, createdAt: new Date().toISOString() }] }), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(AuditPage, { global: { stubs: { 'q-page-container': Stub, 'q-page': Stub, 'q-table': Stub, 'q-select': Stub, 'q-btn': Stub, 'q-badge': Stub } } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.exists()).toBe(true)
    expect(fetchMock).toHaveBeenCalled()
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/admin/audit-events?limit=100')
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ credentials: 'include' })
  })
})
