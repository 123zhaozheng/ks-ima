import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import AccountSecurity from '../../src/pages/AccountSecurity.vue'

const originalFetch = globalThis.fetch
const Stub = defineComponent({ template: '<div><slot /></div>' })
const ButtonStub = defineComponent({ props: { label: { type: String, default: '' } }, emits: ['click'], template: '<button @click="$emit(\'click\')">{{ label }}<slot /></button>' })

vi.mock('src/stores/ui-state', () => ({ useUiStateStore: () => ({ toggleMainDrawer: () => undefined }) }))

describe('AccountSecurity', () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.includes('/account/sessions')) return Promise.resolve(new Response(JSON.stringify([{ id: 's1', current: true, createdAt: new Date().toISOString(), lastActivityAt: new Date().toISOString(), expiresAt: new Date().toISOString(), userAgent: 'Test' }]), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ id: 'u1', email: 'u@test', displayName: 'User', platformRoles: [], isActive: true }), { status: 200 }))
    }) as unknown as typeof fetch
  })
  test('renders loading data and current session state', async () => {
    const wrapper = mount(AccountSecurity, { global: { stubs: { 'q-page-container': Stub, 'q-page': Stub, 'q-card': Stub, 'q-card-section': Stub, 'q-btn': ButtonStub, 'q-input': Stub, 'q-list': Stub, 'q-item': Stub, 'q-item-section': Stub, 'q-item-label': Stub, 'q-space': Stub, 'q-banner': Stub, 'q-badge': Stub } } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Active sessions')
    expect(wrapper.text()).toContain('Current')
  })
  test('renders an API error state', async () => {
    globalThis.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ detail: 'Expired' }), { status: 401 }))) as unknown as typeof fetch
    const wrapper = mount(AccountSecurity, { global: { stubs: { 'q-page-container': Stub, 'q-page': Stub, 'q-banner': Stub, 'q-card': Stub, 'q-card-section': Stub, 'q-btn': ButtonStub, 'q-input': Stub, 'q-list': Stub, 'q-item': Stub, 'q-item-section': Stub, 'q-item-label': Stub, 'q-space': Stub } } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Expired')
  })
  test('revoke-all control invokes the Python session endpoint', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      if (String(input).includes('/account/sessions')) return Promise.resolve(new Response(JSON.stringify([{ id: 's1', current: true, createdAt: new Date().toISOString(), lastActivityAt: new Date().toISOString(), expiresAt: new Date().toISOString(), userAgent: 'Test' }]), { status: 200 }))
      return Promise.resolve(new Response(JSON.stringify({ id: 'u1', email: 'u@test', displayName: 'User', platformRoles: [], isActive: true }), { status: 200 }))
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(AccountSecurity)
    await new Promise(resolve => setTimeout(resolve, 0))
    const revokeAll = wrapper.findAll('button').find(button => button.text() === 'Revoke all')
    expect(revokeAll).toBeDefined()
    await revokeAll!.trigger('click')
    expect(fetchMock.mock.calls.some(call => String(call[0]).includes('/account/sessions'))).toBe(true)
  })
})
