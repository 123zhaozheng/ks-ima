import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'

const state = vi.hoisted(() => ({
  document: null as Record<string, unknown> | null,
  jobs: [] as Array<Record<string, unknown>>,
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
  useKnowledgeIngestion: () => ({
    data: {
      value: state.jobs.length
        ? { documentId: 'doc-1', version: 1, objectState: 'verified', jobs: state.jobs }
        : undefined,
    },
    refetch: vi.fn(),
  }),
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

function job(stage: string, status: string) {
  return { stage, status, completedUnits: 0, totalUnits: 1, errorCode: null, updatedAt: '2026-01-01T00:00:00Z' }
}

function fileDocument(fileState: string) {
  return {
    id: 'doc-1',
    kind: 'file',
    title: 'doc.txt',
    fileState,
    version: 1,
    currentContentVersion: 1,
    folderId: 'folder-1',
    kbId: 'kb-1',
    lifecycle: 'active',
  }
}

function mountPreview() {
  return mount(DocPreview, { props: { documentId: 'doc-1' } })
}

function hasButton(wrapper: ReturnType<typeof mountPreview>, label: string) {
  return wrapper.findAll('button').some(button => button.text().includes(label))
}

describe('DocPreview ingestion banner', () => {
  beforeEach(() => {
    state.document = null
    state.jobs = []
  })

  test('renders Chinese stage and status while processing and exposes 取消', () => {
    state.document = fileDocument('pending')
    state.jobs = [job('embed', 'running')]
    const wrapper = mountPreview()
    const text = wrapper.text()

    expect(text).toContain('处理中')
    expect(text).toContain('向量化 · 处理中')
    expect(text).not.toContain('embed')
    expect(text).not.toContain('running')

    expect(hasButton(wrapper, '取消')).toBe(true)
    expect(hasButton(wrapper, '重试')).toBe(false)
  })

  test('renders a Chinese failure state and exposes 重试', () => {
    state.document = fileDocument('failed')
    state.jobs = [job('chunk', 'dead_letter')]
    const wrapper = mountPreview()
    const text = wrapper.text()

    expect(text).toContain('处理失败')
    expect(text).toContain('切分 · 处理失败')
    expect(text).not.toContain('dead_letter')

    expect(hasButton(wrapper, '重试')).toBe(true)
    expect(hasButton(wrapper, '取消')).toBe(false)
  })

  test('reports a ready document as searchable without listing jobs', () => {
    state.document = fileDocument('ready')
    state.jobs = [job('embed', 'succeeded')]
    const wrapper = mountPreview()
    const text = wrapper.text()

    expect(text).toContain('已就绪，可被检索')
    expect(text).not.toContain('向量化')
    expect(hasButton(wrapper, '取消')).toBe(false)
    expect(hasButton(wrapper, '重试')).toBe(false)
  })
})
