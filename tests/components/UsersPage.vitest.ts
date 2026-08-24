import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import { onMounted } from 'vue'
import UsersPage from '../../src/admin/pages/UsersPage.vue'
import { session } from 'src/utils/identity-client'

const Stub = defineComponent({ template: '<div><slot /></div>' })
const TableStub = defineComponent({ props: { rows: { type: Array, default: () => [] } }, emits: ['request'], setup: (_, context) => { onMounted(() => context.emit('request', { pagination: { sortBy: 'createdAt', descending: true, page: 1, rowsPerPage: 20 } })); return { requestServerInteraction: () => context.emit('request', { pagination: { sortBy: 'createdAt', descending: true, page: 1, rowsPerPage: 20 } }) } }, template: '<div><div v-for="row in rows" :key="row.id">{{ row.email }}</div><slot /></div>' })
const stubs = { 'q-page-container': Stub, 'q-page': Stub, 'q-input': Stub, 'q-btn': Stub, 'q-btn-dropdown': Stub, 'q-list': Stub, 'q-table': TableStub, 'q-td': Stub, 'q-menu': Stub, 'menu-item': Stub, 'q-banner': Stub, 'q-separator': Stub }

describe('UsersPage', () => {
  test('mounts the super-admin action surface with generated user rows', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'super', email: 'super@test', displayName: 'Super', platformRoles: ['super_admin'], isActive: true } } }
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [{ id: 'u1', email: 'user@test', displayName: 'User', platformRoles: [], isActive: true }], nextCursor: null }), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(UsersPage, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('user@test')
    expect(wrapper.text()).toContain('Super administrator role management enabled.')
  })

  test('mounts lower-role view without granting role controls', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'admin', email: 'admin@test', displayName: 'Admin', platformRoles: ['platform_admin'], isActive: true } } }
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ items: [{ id: 'u2', email: 'user@test', displayName: 'User', platformRoles: [], isActive: true }], nextCursor: null }), { status: 200 }))) as unknown as typeof fetch
    const wrapper = mount(UsersPage, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('user@test')
    expect(wrapper.text()).not.toContain('Super administrator role management enabled.')
  })
})
