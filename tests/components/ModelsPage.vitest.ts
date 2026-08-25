import { mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import ModelsPage from '../../src/admin/pages/ModelsPage.vue'

const Stub = defineComponent({ template: '<div><slot /></div>' })
const TableStub = defineComponent({ props: { rows: { type: Array, default: () => [] } }, template: '<div><div v-for="row in rows" :key="row.id">{{ row.name || row.businessLabel || row.businessAlias }}</div><slot /></div>' })
const stubs = {
  'q-page-container': Stub, 'q-page': Stub, 'q-tabs': Stub, 'q-tab': Stub, 'q-tab-panels': Stub,
  'q-tab-panel': Stub, 'q-separator': Stub, 'q-banner': Stub, 'q-btn': Stub, 'q-card': Stub,
  'q-input': Stub, 'q-toggle': Stub, 'q-table': TableStub, 'q-td': Stub, 'q-badge': Stub,
  'q-list': Stub, 'q-item': Stub, 'q-item-section': Stub, 'q-item-label': Stub, 'q-select': Stub,
}

describe('ModelsPage', () => {
  test('renders governed gateway/model/profile data and does not expose credentials', async () => {
    const now = new Date().toISOString()
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      const body = path.includes('model-gateways')
        ? { items: [{ id: 'g1', name: 'Internal gateway', baseUrl: 'https://gateway.internal', enabled: true, allowedCapabilities: ['chat'], tlsMode: 'required', insecurePrivate: false, version: 1, secretPresent: true, health: [], createdAt: now, updatedAt: now }] }
        : path.includes('governed-models')
          ? { items: [{ id: 'm1', gatewayId: 'g1', businessLabel: 'Internal chat', capability: 'chat', enabled: true, validated: true, version: 1, createdAt: now, updatedAt: now }] }
          : { items: [{ id: 'p1', workflow: 'grounded_ask', businessAlias: 'Knowledge Q&A', description: 'Approved answers', lifecycle: 'active', currentVersion: 1, createdAt: now, updatedAt: now }] }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(ModelsPage, { global: { stubs } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Internal gateway')
    expect(wrapper.text()).toContain('Internal chat')
    expect(wrapper.text()).toContain('Knowledge Q&A')
    expect(wrapper.text()).not.toContain('secret')
    expect(fetchMock).toHaveBeenCalledTimes(4)
  })
})
