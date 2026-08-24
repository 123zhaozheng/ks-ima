import { mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import WorkspacesPage from '../../src/admin/pages/WorkspacesPage.vue'
import { session } from 'src/utils/identity-client'


const Stub = defineComponent({ template: '<div><slot /></div>' })
const InputStub = defineComponent({ props: { label: String }, template: '<label>{{ label }}</label>' })
const TableStub = defineComponent({ props: { rows: { type: Array, default: () => [] } }, template: '<div><div v-for="row in rows" :key="row.id">{{ row.name }}</div><slot /></div>' })
const stubs = { 'q-page-container': Stub, 'q-page': Stub, 'q-input': InputStub, 'q-btn': Stub, 'q-table': TableStub, 'q-td': Stub, 'q-banner': Stub }

describe('WorkspacesPage', () => {
  test('renders workspace registry rows from the Python API', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'admin', email: 'admin@example.com', displayName: 'Admin', platformRoles: ['platform_admin'], isActive: true } } }
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [{ id: 'w1', name: 'Knowledge', isActive: true, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }] }), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(WorkspacesPage, { global: { stubs } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Knowledge')
    expect(fetchMock).toHaveBeenCalled()
  })
  test('keeps a failed registry request in a rendered error-capable state', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Forbidden' }), { status: 403 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(WorkspacesPage, { global: { stubs } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Forbidden')
    expect(fetchMock).toHaveBeenCalled()
  })

  test('auditor can read rows without workspace mutation controls', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'auditor', email: 'auditor@example.com', displayName: 'Auditor', platformRoles: ['security_auditor'], isActive: true } } }
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [{ id: 'w2', name: 'Read only', isActive: true, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString() }] }), { status: 200 }))) as unknown as typeof fetch
    const wrapper = mount(WorkspacesPage, { global: { stubs } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Read only')
    expect(wrapper.text()).not.toContain('New workspace')
  })
})
