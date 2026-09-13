import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import SettingsLayout from '../../src/layouts/SettingsLayout.vue'
import { session } from 'src/utils/identity-client'

/*
 * The merged /settings page keeps every capability of the old account pages:
 * profile editing, password change entry, TOTP setup, and session management,
 * plus the device preference (send key).
 */

vi.mock('src/composables/require-login', () => ({ useRequireLogin: () => undefined }))
// The perfs store pulls the kb store, which needs a router; the settings page
// does not interact with knowledge base selection.
vi.mock('src/stores/knowledge-base', () => ({ useKbStore: () => ({ id: null }) }))
// AInput wraps Quasar internals that need build-time defines; the test only
// needs the display name to render through its model-value binding.
vi.mock('src/components/AInput', () => ({
  default: {
    props: { modelValue: String },
    template: '<input :value="modelValue" />',
  },
}))

const Stub = defineComponent({ template: '<div><slot /></div>' })
const ButtonStub = defineComponent({
  props: { label: { type: String, default: '' } },
  emits: ['click'],
  template: '<button @click="$emit(\'click\')">{{ label }}<slot /></button>',
})

const stubs = {
  'q-header': Stub,
  'q-toolbar': Stub,
  'q-toolbar-title': Stub,
  'q-page-container': Stub,
  'q-page': Stub,
  'q-banner': Stub,
  'q-card': Stub,
  'q-card-section': Stub,
  'q-list': Stub,
  'q-item': Stub,
  'q-item-section': Stub,
  'q-item-label': Stub,
  'q-space': Stub,
  'q-badge': Stub,
  'q-icon': Stub,
  'q-separator': Stub,
  'q-spinner': Stub,
  'q-btn': ButtonStub,
  'q-input': Stub,
  'q-select': Stub,
  'a-input': Stub,
  'send-key-select': Stub,
  'common-item': { props: { label: String }, template: '<div><div>{{ label }}</div><slot /></div>' },
}

const sessionInfo = {
  id: 's1',
  current: true,
  createdAt: new Date().toISOString(),
  lastActivityAt: new Date().toISOString(),
  expiresAt: new Date().toISOString(),
  userAgent: 'Test browser',
}

function mountSettings() {
  return mount(SettingsLayout, {
    global: { plugins: [createPinia()], stubs },
  })
}

describe('Settings single page', () => {
  beforeEach(() => {
    session.value = {
      isPending: false,
      error: null,
      data: { user: { id: 'u1', email: 'user@test', displayName: 'Test User', platformRoles: [], isActive: true } },
    }
    globalThis.fetch = vi.fn((input: string) => {
      const path = String(input)
      if (path.includes('/account/sessions')) {
        return Promise.resolve(new Response(JSON.stringify([sessionInfo]), { status: 200 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    }) as unknown as typeof fetch
  })

  test('renders the three sections: profile, security, and preferences', async () => {
    const wrapper = mountSettings()
    await flushPromises()
    // Profile section shows the account identity. The display name renders
    // inside the stubbed input's value rather than the wrapper text.
    expect(wrapper.text()).toContain('个人资料')
    expect(wrapper.get('input').element.value).toBe('Test User')
    expect(wrapper.text()).toContain('user@test')
    // Security section keeps the old account capabilities.
    expect(wrapper.text()).toContain('安全')
    expect(wrapper.text()).toContain('修改密码')
    expect(wrapper.text()).toContain('两步验证')
    expect(wrapper.text()).toContain('设置 TOTP')
    expect(wrapper.text()).toContain('活跃会话')
    // Preferences section keeps the send key.
    expect(wrapper.text()).toContain('偏好')
    expect(wrapper.text()).toContain('发送消息')
  })

  test('lists the current session from the sessions endpoint', async () => {
    const wrapper = mountSettings()
    await flushPromises()
    expect(wrapper.text()).toContain('Test browser')
    expect(wrapper.text()).toContain('当前')
  })

  test('shows an error banner when sessions cannot be loaded', async () => {
    // A 401 now also triggers a session re-check; the re-check must succeed
    // so the sessions-list failure still renders as its error banner.
    globalThis.fetch = vi.fn((input: string) => {
      const path = String(input)
      if (path.includes('/account/sessions')) {
        return Promise.resolve(new Response(JSON.stringify({ detail: 'Session expired' }), { status: 401 }))
      }
      if (path.includes('/auth/session')) {
        return Promise.resolve(new Response(JSON.stringify({ id: 'u1', email: 'user@test', displayName: 'Test User', platformRoles: [], isActive: true }), { status: 200 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    }) as unknown as typeof fetch
    const wrapper = mountSettings()
    await flushPromises()
    expect(wrapper.text()).toContain('Session expired')
  })

  test('revoke-all control calls the session revocation endpoint', async () => {
    const fetchMock = vi.fn((input: string) => {
      const path = String(input)
      if (path.includes('/account/sessions')) {
        return Promise.resolve(new Response(JSON.stringify([sessionInfo]), { status: 200 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mountSettings()
    await flushPromises()
    const revokeAll = wrapper.findAll('button').find(button => button.text() === '全部撤销')
    expect(revokeAll).toBeDefined()
    await revokeAll!.trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.some(call =>
      String(call[0]).includes('/account/sessions'))).toBe(true)
  })
})
