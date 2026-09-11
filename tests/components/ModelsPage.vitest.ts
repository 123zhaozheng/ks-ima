import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import ModelsPage from '../../src/admin/pages/ModelsPage.vue'
import { session } from 'src/utils/identity-client'

const Stub = defineComponent({ template: '<div><slot /></div>' })
const SelectStub = defineComponent({ props: ['modelValue', 'options', 'label'], emits: ['update:modelValue'], template: '<div />' })
const TableStub = defineComponent({
  props: ['rows', 'columns'],
  template: `<div class="table-stub">
    <div v-for="row in rows" :key="row.id" class="table-row">
      <slot v-if="columns.some(c => c.name === 'scene')" name="body-cell-scene" :col="{ name: 'scene' }" :row="row" />
      <slot v-if="columns.some(c => c.name === 'model')" name="body-cell-model" :col="{ name: 'model' }" :row="row" />
      <slot v-if="columns.some(c => c.name === 'status')" name="body-cell-status" :col="{ name: 'status' }" :row="row" />
      <slot v-if="columns.some(c => c.name === 'actions')" name="body-cell-actions" :col="{ name: 'actions' }" :row="row" />
    </div>
  </div>`,
})
const stubs = {
  'q-tabs': Stub,
  'q-tab': Stub,
  'q-tab-panels': Stub,
  'q-tab-panel': Stub,
  'q-select': SelectStub,
  'q-spinner': Stub,
  'q-table': TableStub,
}

const sceneDefaultsItems = [
  { workflow: 'grounded_ask', profileId: 'p1', profileVersion: 1, modelId: 'm-chat-1' },
  { workflow: 'title_generation', profileId: null, profileVersion: null, modelId: null },
  { workflow: 'summarization', profileId: null, profileVersion: null, modelId: null },
  { workflow: 'embedding', profileId: null, profileVersion: null, modelId: null },
  { workflow: 'reranking', profileId: null, profileVersion: null, modelId: null },
]

const governedModels = [{
  id: 'm-chat-1',
  gatewayId: 'g1',
  remoteName: 'gpt-4o',
  businessLabel: 'GPT-4o',
  capability: 'chat',
  enabled: true,
  validated: true,
  version: 1,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
}]

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

function routeFetch(putResponse: () => Response) {
  return vi.fn((input: unknown, init?: { method?: string, body?: string }) => {
    const url = String(input)
    const method = init?.method ?? 'GET'
    if (method === 'PUT' && url.includes('/admin/scene-defaults/')) return putResponse()
    if (url.includes('/admin/model-gateways')) return Promise.resolve(json({ items: [] }))
    if (url.includes('/admin/governed-models')) return Promise.resolve(json({ items: governedModels }))
    if (url.includes('/admin/capability-profiles')) return Promise.resolve(json({ items: [] }))
    if (url.includes('/admin/knowledge-bases')) return Promise.resolve(json({ items: [] }))
    if (url.includes('/admin/scene-defaults')) return Promise.resolve(json({ items: sceneDefaultsItems }))
    return Promise.resolve(json({}))
  })
}

function mountPage(notify: (message: string, color?: string) => void, fetchMock: ReturnType<typeof routeFetch>) {
  globalThis.fetch = fetchMock as unknown as typeof fetch
  return mount(ModelsPage, {
    global: { stubs, provide: { _q_: { notify, dialog: () => ({ onOk: () => undefined, onCancel: () => undefined }) } } },
  })
}

describe('ModelsPage scene defaults', () => {
  test('backfills scene defaults on load and saves the grounded_ask model', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'admin', email: 'admin@test', displayName: 'Admin', platformRoles: ['super_admin'], isActive: true } } }
    const notify = vi.fn()
    const fetchMock = routeFetch(() => json({ workflow: 'grounded_ask', profileId: 'p1', profileVersion: 1, modelId: 'm-chat-1' }))
    const wrapper = mountPage(notify, fetchMock)
    await flushPromises()
    expect(wrapper.text()).not.toContain('功能开发中')
    const saveButtons = wrapper.findAll('button').filter(button => button.text() === '保存')
    expect(saveButtons.length).toBeGreaterThanOrEqual(1)
    await saveButtons[0]!.trigger('click')
    await flushPromises()
    const putCall = fetchMock.mock.calls.find(([input, init]) => String(input).includes('/admin/scene-defaults/') && (init as { method?: string } | undefined)?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(String(putCall![0])).toContain('/admin/scene-defaults/grounded_ask')
    expect(JSON.parse(String((putCall![1] as { body: string }).body))).toEqual({ modelId: 'm-chat-1' })
    expect(notify).toHaveBeenCalledWith({ message: '已保存', color: 'positive' })
  })

  test('reports save failures through a negative toast', async () => {
    session.value = { isPending: false, error: null, data: { user: { id: 'admin', email: 'admin@test', displayName: 'Admin', platformRoles: ['super_admin'], isActive: true } } }
    const notify = vi.fn()
    const fetchMock = routeFetch(() => json({ code: 'MODEL_DISABLED', detail: 'Model is disabled' }, 422))
    const wrapper = mountPage(notify, fetchMock)
    await flushPromises()
    const saveButtons = wrapper.findAll('button').filter(button => button.text() === '保存')
    await saveButtons[0]!.trigger('click')
    await flushPromises()
    expect(notify).toHaveBeenCalledWith({ message: '保存失败：请稍后重试', color: 'negative' })
  })
})
