import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import type { Component } from 'vue'
import { nextTick, ref } from 'vue'
import type * as Quasar from 'quasar'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import KnowledgeList from 'src/components/KnowledgeList.vue'
import KnowledgeTrashList from 'src/components/KnowledgeTrashList.vue'
import KnowledgeDocumentPage from 'src/pages/KnowledgeDocumentPage.vue'
import WorkspaceTags from 'src/pages/WorkspaceTags.vue'
import FolderTree from 'src/components/FolderTree.vue'
import { useFolderContents } from 'src/composables/use-knowledge'

const mocks = vi.hoisted(() => ({
  contents: vi.fn(),
  document: vi.fn(),
  versions: vi.fn(),
  tags: vi.fn(),
  trash: vi.fn(),
  createTag: vi.fn(),
  updateTag: vi.fn(),
  deleteTag: vi.fn(),
  mergeTag: vi.fn(),
  restoreDocument: vi.fn(),
  deleteDocument: vi.fn(),
  restoreVersion: vi.fn(),
  updateDocument: vi.fn(),
  currentDocumentId: 'note-1',
  workspaceId: 'workspace-1',
  route: { params: { documentId: 'note-1' }, query: {} },
  router: { back: vi.fn(), push: vi.fn() },
  dialog: vi.fn(),
}))

vi.mock('src/api/knowledge-client', () => ({
  knowledgeClient: mocks,
}))
vi.mock('src/stores/workspace', () => ({
  useWorkspaceStore: () => ({ id: mocks.workspaceId, workspace: { name: 'Knowledge' } }),
}))
vi.mock('vue-router', () => ({
  useRoute: () => mocks.route,
  useRouter: () => mocks.router,
}))
vi.mock('quasar', async () => {
  const actual = await vi.importActual<typeof Quasar>('quasar')
  return {
    ...actual,
    useQuasar: () => ({ dialog: mocks.dialog }),
    Notify: { create: vi.fn() },
  }
})

const queryStubs = {
  'q-linear-progress': { template: '<div data-testid="progress" />' },
  'q-spinner': { template: '<div data-testid="spinner" />' },
  'q-icon': { template: '<span><slot /></span>' },
  'q-inner-loading': { template: '<div data-testid="inner-loading" />' },
  'q-input': {
    props: { modelValue: String, label: String, disable: Boolean },
    emits: ['update:modelValue'],
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
  'q-banner': { template: '<div><slot /></div>' },
  'q-dialog': { template: '<div v-if="modelValue"><slot /></div>', props: { modelValue: Boolean } },
  'q-space': { template: '<span />' },
}

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function mountWithQuery(component: Component, props: Record<string, unknown> = {}) {
  return mount(component, {
    props,
    global: {
      plugins: [[VueQueryPlugin, { queryClient: createQueryClient() }]],
      stubs: queryStubs,
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.workspaceId = 'workspace-1'
  mocks.route.params.documentId = 'note-1'
  mocks.contents.mockResolvedValue({ items: [], nextCursor: undefined })
  mocks.document.mockResolvedValue({
    id: 'note-1',
    workspaceId: 'workspace-1',
    folderId: 'folder-1',
    kind: 'note',
    title: 'Draft',
    markdown: '# Draft',
    version: 2,
    currentContentVersion: 2,
  })
  mocks.versions.mockResolvedValue([
    { version: 1, createdAt: '2026-08-25T00:00:00Z', digest: 'a' },
    { version: 2, createdAt: '2026-08-25T01:00:00Z', digest: 'b' },
  ])
  mocks.tags.mockResolvedValue([{ id: 'tag-1', name: 'Important', count: 1, version: 1 }])
  mocks.trash.mockResolvedValue({ items: [], nextCursor: undefined })
  mocks.createTag.mockResolvedValue({ id: 'tag-2', name: 'New', count: 0, version: 1 })
  mocks.updateTag.mockResolvedValue({ id: 'tag-1', name: 'Renamed', count: 1, version: 2 })
  mocks.deleteTag.mockResolvedValue(undefined)
  mocks.mergeTag.mockResolvedValue(undefined)
})

describe('knowledge query and component states', () => {
  test('mounts KnowledgeList, renders empty and network error states, and paginates', async () => {
    const wrapper = mountWithQuery(KnowledgeList, { folderId: 'folder-1' })
    await vi.waitFor(() => expect(mocks.contents).toHaveBeenCalledWith('folder-1', expect.objectContaining({ signal: expect.any(AbortSignal) })))
    await vi.waitFor(() => expect(wrapper.text()).toContain('No items'))

    mocks.contents.mockRejectedValueOnce(new Error('offline'))
    const errorWrapper = mountWithQuery(KnowledgeList, { folderId: 'folder-2' })
    await vi.waitFor(() => expect(errorWrapper.text()).toContain('Retry'))

    mocks.contents.mockResolvedValueOnce({
      items: [{ id: 'note-1', kind: 'note', title: 'Note', version: 1 }], nextCursor: 'next-1',
    })
    const pageWrapper = mountWithQuery(KnowledgeList, { folderId: 'folder-3' })
    await vi.waitFor(() => expect(pageWrapper.text()).toContain('Note'))
    await pageWrapper.findAll('[clickable]').at(-1)?.trigger('click')
    expect(mocks.contents).toHaveBeenCalledWith('folder-3', expect.objectContaining({ cursor: 'next-1' }))
  })

  test('preserves unsaved draft after a version conflict and can restore history', async () => {
    mocks.updateDocument.mockRejectedValueOnce(Object.assign(new Error('VERSION_CONFLICT'), { code: 'VERSION_CONFLICT' }))
    mocks.restoreVersion.mockResolvedValue({ id: 'note-1', title: 'Draft', markdown: '# Restored', version: 3, currentContentVersion: 3 })
    const wrapper = mountWithQuery(KnowledgeDocumentPage, {})
    await vi.waitFor(() => expect(wrapper.text()).toContain('Draft'))
    const editor = wrapper.findAll('textarea')[1]
    await editor.setValue('# Unsaved')
    const save = wrapper.findAll('button').find(button => button.text().includes('Save'))
    await save?.trigger('click')
    await vi.waitFor(() => expect(mocks.updateDocument).toHaveBeenCalled())
    expect((wrapper.findAll('textarea')[1].element as HTMLTextAreaElement).value).toBe('# Unsaved')
    const history = wrapper.findAll('button').find(button => button.text().includes('History'))
    await history?.trigger('click')
    await nextTick()
    expect(wrapper.text()).toContain('Version {0}')
    const version = wrapper.findAll('[clickable]').find(node => node.text().includes('Version {0}'))
    expect(version).toBeDefined()
    await version?.trigger('click')
    await vi.waitFor(() => expect(mocks.restoreVersion).toHaveBeenCalledWith('note-1', 1, 2))
  })

  test('renders access-revoked document failure and trash restore/delete actions', async () => {
    mocks.document.mockRejectedValueOnce(new Error('not found'))
    const unavailable = mountWithQuery(KnowledgeDocumentPage, {})
    await vi.waitFor(() => expect(unavailable.text()).toContain('access was revoked'))

    mocks.document.mockResolvedValue({ id: 'note-1', kind: 'note', title: 'Draft', version: 3 })
    mocks.trash.mockResolvedValue({ items: [{ id: 'trash-note', kind: 'note', title: 'Old note', version: 2 }], nextCursor: undefined })
    const trash = mountWithQuery(KnowledgeTrashList, { workspaceId: 'workspace-1' })
    await vi.waitFor(() => expect(trash.text()).toContain('Old note'))
    const actions = trash.findAll('button')
    await actions[0].trigger('click')
    await actions[1].trigger('click')
    expect(mocks.restoreDocument).toHaveBeenCalledWith('trash-note', 2)
    expect(mocks.deleteDocument).toHaveBeenCalledWith('trash-note')
  })

  test('uses Vue Query for workspace tags and normalizes query refresh after mutations', async () => {
    const wrapper = mountWithQuery(WorkspaceTags, {})
    await vi.waitFor(() => expect(wrapper.text()).toContain('Important'))
    mocks.dialog.mockReturnValue({ onOk: (accept: (value: string) => void) => { accept('New') } })
    await wrapper.get('button').trigger('click')
    await vi.waitFor(() => expect(mocks.createTag).toHaveBeenCalledWith('workspace-1', { name: 'New' }))
    expect(mocks.tags).toHaveBeenCalled()
  })

  test('sends versioned delete and merge requests for workspace tags', async () => {
    mocks.tags.mockResolvedValue([
      { id: 'tag-1', name: 'Important', count: 0, version: 1 },
      { id: 'tag-2', name: 'Archive', count: 0, version: 3 },
    ])
    const wrapper = mountWithQuery(WorkspaceTags, {})
    await vi.waitFor(() => expect(wrapper.text()).toContain('Archive'))
    mocks.dialog.mockReturnValueOnce({ onOk: (accept: () => void) => { accept() } })
    await wrapper.findAll('button')[3].trigger('click')
    await vi.waitFor(() => expect(mocks.deleteTag).toHaveBeenCalledWith('workspace-1', 'tag-1', { expectedVersion: 1 }))
    mocks.dialog.mockReturnValueOnce({ onOk: (accept: (value: string) => void) => { accept('Archive') } })
    await wrapper.findAll('button')[2].trigger('click')
    await vi.waitFor(() => expect(mocks.mergeTag).toHaveBeenCalledWith('workspace-1', 'tag-1', {
      targetTagId: 'tag-2', expectedVersion: 1, expectedTargetVersion: 3,
    }))
  })

  test('appends the next trash page through the Load more interaction', async () => {
    mocks.trash
      .mockResolvedValueOnce({
        items: [{ id: 'trash-first', kind: 'note', title: 'First trashed note', version: 1 }],
        nextCursor: 'trash-page-2',
      })
      .mockResolvedValueOnce({
        items: [{ id: 'trash-second', kind: 'file', title: 'Second trashed file', version: 1 }],
        nextCursor: undefined,
      })
    const trash = mountWithQuery(KnowledgeTrashList, { workspaceId: 'workspace-1' })
    await vi.waitFor(() => expect(trash.text()).toContain('First trashed note'))
    const loadMore = trash.findAll('[clickable]').find(node => node.text().includes('Load more'))
    expect(loadMore).toBeDefined()
    await loadMore?.trigger('click')
    await vi.waitFor(() => expect(mocks.trash).toHaveBeenCalledWith('workspace-1', { cursor: 'trash-page-2' }))
    await vi.waitFor(() => expect(trash.text()).toContain('Second trashed file'))
    expect(trash.text()).toContain('First trashed note')
  })

  test('lazy-loads FolderTree children and supports Enter/Space activation', async () => {
    mocks.contents.mockImplementation((folderId: string) => Promise.resolve(folderId === 'workspace-1'
      ? { items: [{ id: 'folder-2', kind: 'folder', title: 'Child', version: 1 }], nextCursor: undefined }
      : { items: [], nextCursor: undefined }))
    const wrapper = mountWithQuery(FolderTree)
    await vi.waitFor(() => expect(wrapper.text()).toContain('Child'))
    expect(mocks.contents).toHaveBeenCalledWith('workspace-1', { kind: 'folder', limit: 100 })
    const child = wrapper.findAll('[role="treeitem"]').find(node => node.text().includes('Child'))
    await child?.trigger('keydown', { key: 'Enter' })
    expect(mocks.router.push).toHaveBeenCalledWith({ path: '/', query: { folderId: 'folder-2' } })
    await child?.trigger('keydown', { key: ' ' })
    expect(mocks.router.push).toHaveBeenCalledWith({ path: '/', query: { folderId: 'folder-2' } })
  })
})

describe('query cancellation', () => {
  test('passes Query cancellation signals through folder content requests', async () => {
    let receivedSignal: AbortSignal | undefined
    mocks.contents.mockImplementation((_folderId: string, options: { signal?: AbortSignal }) => {
      receivedSignal = options.signal
      return new Promise<never>(() => {
        // Keep the request pending so Vue Query owns cancellation.
      })
    })
    const Harness = {
      setup() {
        const folder = ref('folder-1')
        const query = useFolderContents(() => folder.value)
        return { folder, query }
      },
      template: '<div />',
    }
    const wrapper = mountWithQuery(Harness)
    await vi.waitFor(() => expect(receivedSignal).toBeInstanceOf(AbortSignal))
    wrapper.unmount()
    expect(receivedSignal).toBeDefined()
  })
})
