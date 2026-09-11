import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import type * as Quasar from 'quasar'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import ConversationView from 'src/pages/ConversationView.vue'

/*
 * DOMPurify cannot run under happy-dom; same stub contract as
 * MarkdownRender.vitest.ts.
 */
const sanitize = vi.hoisted(() => vi.fn((html: string) => html
  .replace(/<script\b[\s\S]*?<\/script>/gi, '')
  .replace(/\son\w+="[^"]*"/gi, '')))

vi.mock('dompurify', () => ({ default: { sanitize } }))

const message = (partial: Record<string, unknown>) => ({
  id: 'msg',
  role: 'user',
  content: '',
  status: 'completed',
  sequence: 1,
  version: 1,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:00:00Z',
  completedAt: '2026-01-01T00:00:00Z',
  ...partial,
})

const loadedDetail = {
  id: 'conv-1',
  kbId: 'kb-1',
  title: 'Policy question',
  lifecycle: 'active',
  version: 3,
  createdAt: '2026-01-01T00:00:00Z',
  updatedAt: '2026-01-01T00:01:00Z',
  messages: [
    message({ id: 'msg-u1', role: 'user', content: 'What is the policy?', sequence: 1 }),
    message({ id: 'msg-a1', role: 'assistant', content: 'The policy is X [1].', sequence: 2 }),
  ],
}

const mocks = vi.hoisted(() => ({
  ask: vi.fn(),
  retry: vi.fn(),
  conversation: vi.fn(),
  conversations: vi.fn(),
  citation: vi.fn(),
  search: vi.fn(),
  updateConversation: vi.fn(),
  deleteConversation: vi.fn(),
  route: { params: { conversationId: 'conv-1' }, query: {} },
  router: { push: vi.fn(), replace: vi.fn() },
}))

vi.mock('src/api/grounded-client', () => ({
  groundedClient: {
    ask: mocks.ask,
    retry: mocks.retry,
    conversation: mocks.conversation,
    conversations: mocks.conversations,
    citation: mocks.citation,
    search: mocks.search,
    updateConversation: mocks.updateConversation,
    deleteConversation: mocks.deleteConversation,
    buildIndex: vi.fn(),
  },
}))
vi.mock('src/stores/knowledge-base', () => ({
  useKbStore: () => ({ id: 'kb-1' }),
}))
vi.mock('src/utils/identity-client', () => ({
  session: { value: { isPending: false, error: null, data: { user: { id: 'user-1' } } } },
}))
vi.mock('src/composables/require-login', () => ({ useRequireLogin: () => undefined }))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))
vi.mock('quasar', async () => {
  const actual = await vi.importActual<typeof Quasar>('quasar')
  return {
    ...actual,
    useQuasar: () => ({ dialog: vi.fn() }),
    Notify: { create: vi.fn() },
  }
})

const stubs = {
  // The conversation subject teleports into the shell TopBar; render it in
  // place so the title is part of the mounted output.
  teleport: true,
  'q-header': { template: '<div><slot /></div>' },
  'q-toolbar': { template: '<div><slot /></div>' },
  'q-toolbar-title': { template: '<div><slot /></div>' },
  'q-page-container': { template: '<div><slot /></div>' },
  'q-page': { props: ['styleFn'], template: '<div><slot /></div>' },
  'q-spinner': { template: '<div data-testid="spinner" />' },
  'q-icon': { template: '<span><slot /></span>' },
  'q-banner': { template: '<div><slot /><slot name="action" /></div>' },
  'q-dialog': { props: ['modelValue'], template: '<div v-if="modelValue"><slot /></div>' },
  'q-menu': { template: '<div><slot /></div>' },
  'q-input': {
    props: { modelValue: String, label: String, disable: Boolean, placeholder: String },
    template: '<textarea :value="modelValue" :disabled="disable" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'q-btn': {
    props: { label: String, disable: Boolean },
    template: '<button :disabled="disable"><slot />{{ label }}</button>',
  },
  'q-list': { template: '<div><slot /></div>' },
  'q-item': { template: '<div><slot /></div>' },
  'q-item-section': { template: '<div><slot /></div>' },
  'q-item-label': { template: '<div><slot /></div>' },
  'q-card': { template: '<div><slot /></div>' },
  'q-card-section': { template: '<div><slot /></div>' },
  'q-card-actions': { template: '<div><slot /></div>' },
  'q-space': { template: '<span />' },
  'q-chip': { template: '<span><slot /></span>' },
  'q-separator': { template: '<hr />' },
  'save-answer-dialog': { template: '<div />' },
  'doc-preview': {
    props: { documentId: String, highlight: String },
    template: '<div data-testid="doc-preview-stub">{{ documentId }}</div>',
  },
}

function mountView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return mount(ConversationView, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient }], createPinia()],
      stubs,
    },
  })
}

const citation1 = {
  rank: 1,
  quote: 'Policy source text',
  documentId: 'doc-1',
  documentVersion: 1,
  fileGeneration: null,
  chunkOrdinal: 0,
  chunkDigest: 'digest-1',
  score: 0.9,
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.route.params.conversationId = 'conv-1'
  mocks.conversation.mockResolvedValue(loadedDetail)
  // User-level history list: the conversation belongs to kb-1.
  mocks.conversations.mockResolvedValue({
    items: [{
      id: 'conv-1',
      kbId: 'kb-1',
      kbName: 'Team KB',
      title: 'Policy question',
      lifecycle: 'active',
      version: 3,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:01:00Z',
    }],
  })
  mocks.citation.mockImplementation((_kb: string, _messageId: string, rank: number) =>
    rank === 1 ? Promise.resolve(citation1) : Promise.reject(new Error('not found')))
  mocks.ask.mockResolvedValue(undefined)
  mocks.retry.mockResolvedValue(undefined)
})

describe('ConversationView', () => {
  test('renders the loaded thread with clickable citation marks', async () => {
    const wrapper = mountView()
    await vi.waitFor(() => expect(wrapper.text()).toContain('What is the policy?'))
    expect(wrapper.text()).toContain('Policy question')

    const mark = wrapper.find('[data-citation="1"]')
    expect(mark.exists()).toBe(true)
    expect(mark.attributes('data-testid')).toBe('citation-mark')

    await mark.trigger('click')
    // The citation is fetched from the conversation's owning knowledge base.
    await vi.waitFor(() => expect(mocks.citation).toHaveBeenCalledWith('kb-1', 'msg-a1', 1))
    await vi.waitFor(() => expect(wrapper.find('[data-testid="citation-pane"]').exists()).toBe(true))
    expect(wrapper.find('[data-testid="doc-preview-stub"]').text()).toBe('doc-1')
  })

  test('sends a follow-up through the grounded ask stream', async () => {
    const wrapper = mountView()
    await vi.waitFor(() => expect(wrapper.text()).toContain('What is the policy?'))

    const textarea = wrapper.get('textarea')
    await textarea.setValue('Follow up question')
    await textarea.trigger('keydown', { key: 'Enter' })

    await vi.waitFor(() => expect(mocks.ask).toHaveBeenCalledWith(
      'kb-1',
      { question: 'Follow up question', conversationId: 'conv-1' },
      expect.any(AbortSignal),
      expect.any(Function),
    ))
    // Optimistic user bubble shows while the stream is in flight.
    expect(wrapper.text()).toContain('Follow up question')
  })
})
