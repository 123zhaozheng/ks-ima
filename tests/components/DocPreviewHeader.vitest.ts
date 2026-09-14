import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { shallowRef } from 'vue'
import DocPreview from '../../src/components/DocPreview.vue'

const state = vi.hoisted(() => ({
  document: null as { value: Record<string, unknown> | null } | null,
  preview: vi.fn(),
  download: vi.fn(),
  renderAsync: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('src/stores/ask-context', () => ({ useAskContextStore: () => ({ askAboutDocument: vi.fn() }) }))
vi.mock('src/utils/markdown', () => ({ renderMarkdown: () => '' }))
vi.mock('src/components/PdfPreview.vue', () => ({
  default: { template: '<div data-testid="pdf-preview-stub" />' },
}))
vi.mock('src/api/knowledge-client', () => ({
  knowledgeClient: {
    preview: state.preview,
    download: state.download,
    restoreVersion: vi.fn(),
  },
}))
vi.mock('docx-preview', () => ({ renderAsync: state.renderAsync }))
vi.mock('src/composables/use-knowledge', () => ({
  useKnowledgeDocument: () => ({
    data: state.document!,
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

state.document = shallowRef<Record<string, unknown> | null>(null)

// QMenu teleports its content and stays closed, so stub it to render its slot
// inline and make the overflow items assertable.
const stubs = {
  'q-menu': { template: '<div><slot /></div>' },
  'q-spinner': { template: '<span />' },
  'q-linear-progress': { template: '<span />' },
}
const mountedPreviews: ReturnType<typeof mount>[] = []

function fileDocument() {
  return {
    id: 'doc-1',
    kind: 'file',
    title: 'doc.txt',
    fileState: 'ready',
    version: 1,
    currentContentVersion: 1,
    mimeType: 'text/plain',
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
  const wrapper = mount(DocPreview, {
    props: { documentId: 'doc-1', ...props },
    global: { stubs },
  })
  mountedPreviews.push(wrapper)
  return wrapper
}

describe('DocPreview header actions', () => {
  beforeEach(() => {
    state.document!.value = fileDocument()
    state.preview.mockReset()
    state.preview.mockResolvedValue({ url: 'https://preview.test/doc-1' })
    state.download.mockReset()
    state.download.mockResolvedValue({ url: 'https://download.test/doc-1' })
    state.renderAsync.mockReset()
  })

  afterEach(() => {
    mountedPreviews.splice(0).forEach(wrapper => wrapper.unmount())
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
    state.document!.value = noteDocument()
    const wrapper = mountPreview()

    expect(wrapper.text()).toContain('编辑')
    expect(wrapper.text()).not.toContain('替换')
    expect(wrapper.find('[data-testid="doc-delete-button"]').exists()).toBe(true)
  })

  test('requests a preview when a warm-cache document is available at mount', async () => {
    mountPreview()

    await flushPromises()

    expect(state.preview).toHaveBeenCalledWith('doc-1', expect.any(AbortSignal))
  })

  test('does not let a late response for the previous document overwrite the current preview', async () => {
    let resolveFirst: (value: { url: string }) => void = () => undefined
    let resolveSecond: (value: { url: string }) => void = () => undefined
    state.preview.mockImplementation((documentId: string) => new Promise(resolve => {
      if (documentId === 'doc-a') resolveFirst = resolve
      else resolveSecond = resolve
    }))
    state.document!.value = { ...fileDocument(), id: 'doc-a', title: 'a.txt' }
    const wrapper = mountPreview({ documentId: 'doc-a' })
    await flushPromises()

    state.document!.value = { ...fileDocument(), id: 'doc-b', title: 'b.txt' }
    await wrapper.setProps({ documentId: 'doc-b' })
    await flushPromises()
    resolveSecond({ url: 'https://preview.test/doc-b' })
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe('https://preview.test/doc-b')

    resolveFirst({ url: 'https://preview.test/doc-a' })
    await flushPromises()
    expect(wrapper.get('iframe').attributes('src')).toBe('https://preview.test/doc-b')
  })

  test('shows an error state when Office rendering fails', async () => {
    state.document!.value = {
      ...fileDocument(),
      id: 'office-1',
      title: 'report.docx',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }
    state.download.mockRejectedValue(new Error('download failed'))
    const wrapper = mountPreview({ documentId: 'office-1' })

    await flushPromises()

    expect(wrapper.text()).toContain('预览加载失败')
    expect(wrapper.find('[data-testid="doc-preview-retry"]').exists()).toBe(true)
  })

  test('drops a late Office render without touching the current document host', async () => {
    const originalFetch = globalThis.fetch
    const pendingRenders: Array<{ host: HTMLElement, resolve: () => void }> = []
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      arrayBuffer: () => Promise.resolve(new ArrayBuffer(0)),
    })) as unknown as typeof fetch
    state.download.mockImplementation((documentId: string) => Promise.resolve({ url: documentId }))
    state.renderAsync.mockImplementation((_bytes: ArrayBuffer, host: HTMLElement) => new Promise<void>(resolve => {
      pendingRenders.push({ host, resolve })
    }))
    state.document!.value = {
      ...fileDocument(),
      id: 'office-a',
      title: 'a.docx',
      mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    }
    const wrapper = mountPreview({ documentId: 'office-a' })

    try {
      await flushPromises()
      expect(pendingRenders).toHaveLength(1)

      state.document!.value = {
        ...fileDocument(),
        id: 'office-b',
        title: 'b.docx',
        mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      }
      await wrapper.setProps({ documentId: 'office-b' })
      await flushPromises()
      expect(pendingRenders).toHaveLength(2)

      pendingRenders[1].host.textContent = 'current document'
      pendingRenders[1].resolve()
      await flushPromises()
      expect(wrapper.get('.doc-preview-office-host').text()).toBe('current document')

      pendingRenders[0].host.textContent = 'stale document'
      pendingRenders[0].resolve()
      await flushPromises()
      expect(wrapper.get('.doc-preview-office-host').text()).toBe('current document')
      expect(wrapper.text()).not.toContain('stale document')
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})
