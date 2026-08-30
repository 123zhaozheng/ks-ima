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
  workspaceId: 'workspace-1',
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
  contents: vi.fn(),
  document: vi.fn(),
  ingestion: vi.fn(),
  versions: vi.fn(),
  fileVersions: vi.fn(),
  createNote: vi.fn(),
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
vi.mock('src/api/knowledge-client', () => ({
  knowledgeClient: {
    contents: mocks.contents,
    document: mocks.document,
    ingestion: mocks.ingestion,
    versions: mocks.versions,
    fileVersions: mocks.fileVersions,
    createNote: mocks.createNote,
    download: vi.fn(),
    preview: vi.fn(),
  },
}))
vi.mock('src/stores/workspace', () => ({
  useWorkspaceStore: () => ({ id: 'workspace-1', workspace: { name: 'Workspace' } }),
}))
vi.mock('src/utils/identity-client', () => ({
  session: { value: { isPending: false, error: null, data: { user: { id: 'user-1' } } } },
}))
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
  'q-item': { template: '<div clickable><slot /></div>' },
  'q-item-section': { template: '<div><slot /></div>' },
  'q-item-label': { template: '<div><slot /></div>' },
  'q-card': { template: '<div><slot /></div>' },
  'q-card-section': { template: '<div><slot /></div>' },
  'q-card-actions': { template: '<div><slot /></div>' },
  'q-space': { template: '<span />' },
  'q-chip': { template: '<span><slot /></span>' },
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
  mocks.conversations.mockResolvedValue({ items: [] })
  mocks.citation.mockImplementation((_ws: string, _messageId: string, rank: number) =>
    Promise.resolve(rank === 1 ? citation1 : Promise.reject(new Error('not found'))))
  mocks.contents.mockResolvedValue({ items: [], nextCursor: undefined })
  mocks.document.mockResolvedValue({
    id: 'doc-1',
    workspaceId: 'workspace-1',
    folderId: 'folder-1',
    kind: 'note',
    title: 'Policy doc',
    markdown: 'Policy source text lives here.',
    version: 1,
    currentContentVersion: 1,
  })
  mocks.ingestion.mockResolvedValue({ jobs: [] })
  mocks.versions.mockResolvedValue([])
  mocks.fileVersions.mockResolvedValue({ items: [] })
  mocks.createNote.mockResolvedValue({ id: 'note-9', folderId: 'folder-9', title: 'Saved', version: 1 })
  mocks.retry.mockResolvedValue(undefined)
  mocks.ask.mockResolvedValue(undefined)
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
    await vi.waitFor(() => expect(mocks.citation).toHaveBeenCalledWith('workspace-1', 'msg-a1', 1))
    await vi.waitFor(() => expect(wrapper.find('[data-testid="citation-pane"]').exists()).toBe(true))
    // The preview renders the document title inside a q-input stub (textarea),
    // whose value is not part of .text().
    await vi.waitFor(() => expect(
      (wrapper.find('[data-testid="citation-pane"] textarea').element as HTMLTextAreaElement).value,
    ).toBe('Policy doc'))
  })

  test('streams a follow-up answer with citations, then hands over to the persisted thread', async () => {
    const wrapper = mountView()
    await vi.waitFor(() => expect(wrapper.text()).toContain('What is the policy?'))

    // Hold the post-stream conversation refetch so the live overlay stays up
    // while we assert on the streamed answer, then resolve it to verify the
    // handover to the persisted thread.
    let resolveConversation!: (value: unknown) => void
    const held = new Promise(resolve => { resolveConversation = resolve })
    mocks.conversation.mockImplementation(() => held)

    mocks.ask.mockImplementation(async (_ws: unknown, request: { question: string, conversationId?: string }, _signal: unknown, onEvent: (event: string, payload: Record<string, unknown>) => void) => {
      expect(request).toMatchObject({ question: 'Follow up question', conversationId: 'conv-1' })
      onEvent('conversation', { conversationId: 'conv-1', messageId: 'msg-a2' })
      onEvent('message', { conversationId: 'conv-1', messageId: 'msg-a2', status: 'pending' })
      // Yield so the component observes the streaming status in a flushed
      // tick, matching real SSE arrival timing.
      await new Promise(resolve => setTimeout(resolve, 0))
      onEvent('citations', { conversationId: 'conv-1', messageId: 'msg-a2', citations: [{ ...citation1, quote: 'Cited follow-up quote' }] })
      onEvent('delta', { conversationId: 'conv-1', messageId: 'msg-a2', delta: 'Follow-up answer citing [1].' })
      onEvent('completed', { conversationId: 'conv-1', messageId: 'msg-a2', status: 'completed' })
    })

    const textarea = wrapper.findAll('textarea')[0]
    await textarea.setValue('Follow up question')
    await textarea.trigger('keydown', { key: 'Enter' })

    await vi.waitFor(() => expect(wrapper.text()).toContain('Follow-up answer citing'))
    expect(wrapper.find('[data-citation="1"]').exists()).toBe(true)
    const source = wrapper.find('[data-testid="citation-source"]')
    expect(source.exists()).toBe(true)
    expect(source.text()).toContain('Cited follow-up quote')

    // The stream completion invalidates the conversation query; once the
    // persisted thread arrives the live overlay hands over to it.
    resolveConversation({
      ...loadedDetail,
      messages: [
        ...loadedDetail.messages,
        message({ id: 'msg-u2', role: 'user', content: 'Follow up question', sequence: 3 }),
        message({ id: 'msg-a2', role: 'assistant', content: 'Follow-up answer citing [1].', sequence: 4 }),
      ],
    })
    await vi.waitFor(() => expect(wrapper.text()).toContain('Follow up question'))
    await vi.waitFor(() => expect(wrapper.findAll('[data-testid="citation-source"]').length).toBe(0))
    expect(wrapper.text()).toContain('Follow-up answer citing')
  })

  test('shows an error card with retry for failed answers', async () => {
    mocks.conversation.mockResolvedValue({
      ...loadedDetail,
      messages: [
        message({ id: 'msg-u1', role: 'user', content: 'What is the policy?', sequence: 1 }),
        message({ id: 'msg-a1', role: 'assistant', content: '', status: 'failed', sequence: 2 }),
      ],
    })
    const wrapper = mountView()
    await vi.waitFor(() => expect(wrapper.text()).toContain('The answer failed to generate.'))
    const retry = wrapper.find('[data-testid="answer-retry"]')
    await retry.trigger('click')
    await vi.waitFor(() => expect(mocks.retry).toHaveBeenCalledWith(
      'workspace-1', 'conv-1', 'msg-u1', 1, expect.any(AbortSignal), expect.any(Function)))
  })

  test('renders knowledge gaps as a gentle notice', async () => {
    mocks.conversation.mockResolvedValue({
      ...loadedDetail,
      messages: [
        message({ id: 'msg-u1', role: 'user', content: 'Something unknown?', sequence: 1 }),
        message({ id: 'msg-a1', role: 'assistant', content: '', status: 'knowledge_gap', sequence: 2 }),
      ],
    })
    const wrapper = mountView()
    await vi.waitFor(() => expect(wrapper.text()).toContain('does not contain an answer'))
  })

  test('saves an answer as a note with a citations appendix', async () => {
    mocks.contents.mockResolvedValue({
      items: [{ id: 'folder-9', kind: 'folder', title: 'Notes', version: 1 }],
      nextCursor: undefined,
    })
    const wrapper = mountView()
    await vi.waitFor(() => expect(wrapper.text()).toContain('What is the policy?'))

    await wrapper.find('[data-testid="save-as-note"]').trigger('click')
    await vi.waitFor(() => expect(mocks.citation).toHaveBeenCalledWith('workspace-1', 'msg-a1', 1))
    await vi.waitFor(() => expect(wrapper.find('[data-testid="folder-picker"]').exists()).toBe(true))

    // Choose the folder in the dialog's picker, then confirm. The folder rows
    // load asynchronously from the contents endpoint.
    const folderRow = await vi.waitFor(() => {
      const row = wrapper.findAll('[clickable]').find(node => node.text().includes('Notes'))
      expect(row).toBeDefined()
      return row!
    })
    await folderRow.trigger('click')
    const confirm = wrapper.find('[data-testid="save-as-note-confirm"]')
    await confirm.trigger('click')

    await vi.waitFor(() => expect(mocks.createNote).toHaveBeenCalledWith('folder-9', expect.objectContaining({
      title: 'The policy is X [1].',
      markdown: expect.stringContaining('Policy source text'),
    })))
    expect(mocks.createNote.mock.calls[0][1].markdown).toContain('Sources')
  })
})
