import { mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import UpdateSettingsDialog from '../../src/admin/components/UpdateSettingsDialog.vue'

const Stub = defineComponent({ template: '<div><slot /></div>' })


describe('UpdateSettingsDialog', () => {
  test('shows SMTP unavailable state from typed platform settings', async () => {
    globalThis.fetch = vi.fn((input: RequestInfo | URL) => String(input).includes('/admin/settings') ? Promise.resolve(new Response(JSON.stringify({ allowRegistration: false, smtpEnabled: false, sessionIdleSeconds: 86400, sessionAbsoluteSeconds: 2592000, recentAuthSeconds: 900, updatedAt: new Date().toISOString() }), { status: 200 })) : Promise.resolve(new Response('{}', { status: 200 }))) as unknown as typeof fetch
    const wrapper = mount(UpdateSettingsDialog, { global: { stubs: { 'q-dialog': Stub, 'q-card': Stub, 'q-card-section': Stub, 'q-card-actions': Stub, 'q-toggle': Stub, 'q-input': Stub, 'q-banner': Stub, 'q-btn': Stub } } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('SMTP delivery')
  })
})
