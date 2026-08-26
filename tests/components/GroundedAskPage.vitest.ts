import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import GroundedAskPage from 'src/pages/GroundedAskPage.vue'

const mocks = await vi.hoisted(async () => {
  const { ref } = await import('vue')
  return {
    search: vi.fn(),
    ask: vi.fn(),
    cancel: vi.fn(),
    workspaceId: 'workspace-1',
    answer: ref(''),
    citations: ref<Array<Record<string, unknown>>>([]),
    status: ref<'idle' | 'streaming' | 'completed' | 'knowledge_gap' | 'failed' | 'cancelled'>('idle'),
  }
})

vi.mock('src/api/grounded-client', () => ({
  groundedClient: { search: mocks.search },
}))
vi.mock('src/stores/workspace', () => ({
  useWorkspaceStore: () => ({ id: mocks.workspaceId }),
}))
vi.mock('src/composables/use-grounded-knowledge', () => ({
  useGroundedKnowledge: () => ({
    answer: mocks.answer,
    ask: mocks.ask,
    cancel: mocks.cancel,
    citations: mocks.citations,
    status: mocks.status,
  }),
}))

const stubs = {
  'q-page': { template: '<main><slot /></main>' },
  'q-input': {
    props: { modelValue: String, label: String, loading: Boolean, disable: Boolean },
    emits: ['update:modelValue', 'keyup'],
    template: '<textarea :aria-label="label" :value="modelValue" :disabled="disable" @input="$emit(\'update:modelValue\', $event.target.value)" @keyup="$emit(\'keyup\', $event)" />',
  },
  'q-btn': {
    props: { label: String, ariaLabel: String, loading: Boolean },
    emits: ['click'],
    template: '<button :aria-label="ariaLabel || label" @click="$emit(\'click\')"><slot />{{ label }}</button>',
  },
  'q-banner': { template: '<div role="status"><slot /></div>' },
  'q-list': { template: '<div><slot /></div>' },
  'q-item': { template: '<a><slot /></a>' },
  'q-item-section': { template: '<span><slot /></span>' },
  'q-item-label': { template: '<span><slot /></span>' },
}

function mountPage(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: width })
  return mount(GroundedAskPage, { global: { stubs } })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.answer.value = ''
  mocks.citations.value = []
  mocks.status.value = 'idle'
  mocks.search.mockResolvedValue({
    items: [{ documentId: 'document-1', chunkOrdinal: 0, title: 'Policy', quote: 'Policy source' }],
  })
  mocks.ask.mockImplementation(async () => {
    mocks.status.value = 'streaming'
    mocks.citations.value = [{ documentId: 'document-1', chunkOrdinal: 0, rank: 1, quote: 'Policy source' }]
    mocks.answer.value = 'Grounded answer'
    mocks.status.value = 'completed'
  })
  mocks.cancel.mockImplementation(() => { mocks.status.value = 'cancelled' })
})

describe('GroundedAskPage', () => {
  test('renders target search results and citation-backed progressive answer on desktop', async () => {
    const wrapper = mountPage(1280)
    const [search, ask] = wrapper.findAll('textarea')
    await search.setValue('policy')
    await search.trigger('keyup.enter')
    await vi.waitFor(() => expect(mocks.search).toHaveBeenCalledWith('workspace-1', 'policy'))
    expect(wrapper.text()).toContain('Policy source')

    await ask.setValue('What is the policy?')
    await ask.trigger('keyup', { key: 'Enter', ctrlKey: true })
    await vi.waitFor(() => expect(mocks.ask).toHaveBeenCalledWith('What is the policy?'))
    expect(wrapper.text()).toContain('Grounded answer')
    expect(wrapper.text()).toContain('Source 1')
    expect(wrapper.findAll('section')).toHaveLength(2)
    expect(wrapper.findAll('section')[0].classes()).toContain('col-md-6')
  })

  test('exposes cancellation and no-hit state without horizontal mobile layout changes', async () => {
    const wrapper = mountPage(390)
    mocks.status.value = 'streaming'
    await wrapper.vm.$nextTick()
    await wrapper.get('button[aria-label="Cancel Ask"]').trigger('click')
    expect(mocks.cancel).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('Ask was cancelled.')

    mocks.status.value = 'idle'
    mocks.search.mockResolvedValueOnce({ items: [] })
    await wrapper.findAll('textarea')[0].setValue('missing')
    await wrapper.findAll('textarea')[0].trigger('keyup.enter')
    await vi.waitFor(() => expect(wrapper.text()).toContain('No accessible knowledge matched this search.'))
    expect(wrapper.findAll('section').every(section => section.classes().includes('col-12'))).toBe(true)
  })
})
