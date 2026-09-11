import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'

const state = vi.hoisted(() => ({
  document: null as Record<string, unknown> | null,
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('src/stores/ask-context', () => ({ useAskContextStore: () => ({ askAboutDocument: vi.fn() }) }))
vi.mock('src/utils/markdown', () => ({ renderMarkdown: () => '' }))
vi.mock('src/api/knowledge-client', () => ({
  knowledgeClient: {
    preview: vi.fn().mockRejectedValue(new Error('unsupported')),
    download: vi.fn(),
    restoreVersion: vi.fn(),
  },
}))
vi.mock('src/composables/use-knowledge', () => ({
  useKnowledgeDocument: () => ({
    data: { value: state.document },
    isLoading: { value: false },
    isError: { value: false },
    refetch: vi.fn(),
  }),
  useKnowledgeIngestion: () => ({ data: { value: undefined }, refetch: vi.fn() }),
  useKnowledgeVersions: () => ({ data: { value: [] } }),
  useFileVersions: () => ({ data: { value: { items: [] } }, refetch: vi.fn() }),
  useKnowledgeMutations: () => ({
    retryIngestion: { mutateAsync: vi.fn() },
    cancelIngestion: { mutateAsync: vi.fn() },
    deleteDocument: { mutateAsync: vi.fn() },
    updateDocument: { mutateAsync: vi.fn() },
    replaceFile: { mutateAsync: vi.fn() },
  }),
}))

import DocPreview from '../../src/components/DocPreview.vue'

// QMenu teleports its content and stays closed, so stub it to render its slot
// inline and make the overflow items assertable.
const stubs = { 'q-menu': { template: '<div><slot /></div>' } }

function fileDocument() {
  return {
    id: 'doc-1',
    kind: 'file',
    title: 'doc.txt',
    fileState: 'ready',
    version: 1,
    currentContentVersion: 1,
    folderId: 'folder-1',
    kbId: 'kb-1',
    lifecycle: 'active',
  }
}

function noteDocument() {
  return {
    id: 'doc-2',
    kind: 'note',
    title: 'note',
    fileState: null,
    version: 1,
    currentContentVersion: 1,
    folderId: 'folder-1',
    kbId: 'kb-1',
    lifecycle: 'active',
    markdown: '# hi',
  }
}

function mountPreview(props: Record<string, unknown> = {}) {
  return mount(DocPreview, {
    props: { documentId: 'doc-1', ...props },
    global: { stubs },
  })
}

describe('DocPreview header actions', () => {
  beforeEach(() => {
    state.document = fileDocument()
  })

  test('renders icon-only pinned actions with Chinese titles and no visible labels', () => {
    const wrapper = mountPreview()

    const close = wrapper.get('[data-testid="doc-close-button"]')
    const save = wrapper.get('[data-testid="doc-save-button"]')
    const ask = wrapper.get('[data-testid="doc-ask-button"]')
    const download = wrapper.get('[data-testid="doc-download-button"]')

    for (const button of [close, save, ask, download]) {
      expect(button.text()).toBe('')
    }
    expect(close.attributes('title')).toBe('关闭')
    expect(close.attributes('aria-label')).toBe('关闭')
    expect(save.attributes('title')).toBe('保存')
    expect(save.attributes('aria-label')).toBe('保存')
    expect(ask.attributes('title')).toBe('询问')
    expect(download.attributes('title')).toBe('下载')
    expect(wrapper.get('[data-testid="doc-more-button"]').attributes('title')).toBe('更多')
  })

  test('overflow menu holds replace, history, preview and delete for a file', () => {
    const wrapper = mountPreview()

    const menu = wrapper.text()
    expect(menu).toContain('替换')
    expect(menu).toContain('历史')
    expect(menu).toContain('预览')
    expect(menu).toContain('删除')
    // A file has no editor/preview mode toggle.
    expect(menu).not.toContain('编辑')
    expect(wrapper.find('[data-testid="doc-delete-button"]').exists()).toBe(true)
  })

  test('readonly hides write actions and keeps read-only menu items', () => {
    const wrapper = mountPreview({ readonly: true })

    expect(wrapper.find('[data-testid="doc-save-button"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="doc-delete-button"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('替换')
    expect(wrapper.text()).not.toContain('删除')
    expect(wrapper.find('[data-testid="doc-ask-button"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('历史')
    expect(wrapper.text()).toContain('预览')
  })

  test('note exposes an edit/preview toggle and no replace', () => {
    state.document = noteDocument()
    const wrapper = mountPreview()

    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).not.toContain('替换')
    expect(wrapper.find('[data-testid="doc-delete-button"]').exists()).toBe(true)
  })
})
