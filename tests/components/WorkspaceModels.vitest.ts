import { mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import WorkspaceModels from '../../src/pages/WorkspaceModels.vue'

const workspaceState = { id: 'w1' as string | null }
vi.mock('src/stores/workspace', () => ({ useWorkspaceStore: () => workspaceState }))

const Stub = defineComponent({ template: '<div><slot /></div>' })
const Item = defineComponent({ template: '<div><slot /></div>' })

describe('WorkspaceModels', () => {
  test('renders only safe business capabilities', async () => {
    const fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify([
      { workflow: 'grounded_ask', alias: 'Knowledge Q&A', description: 'Approved answers', version: 3, status: 'available', reason: null },
    ]), { status: 200 })))
    globalThis.fetch = fetchMock as unknown as typeof fetch
    const wrapper = mount(WorkspaceModels, {
      global: {
        stubs: { 'q-page-container': Stub, 'q-page': Stub, 'q-banner': Stub, 'q-btn': Stub, 'q-list': Stub, 'q-item': Item, 'q-item-section': Item, 'q-item-label': Item, 'q-icon': Stub, 'q-badge': Stub, 'q-inner-loading': Stub, 'q-spinner': Stub },
        plugins: [],
      },
    })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Knowledge Q&A')
    expect(wrapper.text()).not.toContain('gateway.internal')
    expect(wrapper.text()).not.toContain('secret')
  })
})
