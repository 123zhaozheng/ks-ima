import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { defineComponent } from 'vue'
import { fileStateView, jobStatusColor, jobStatusLabel, stageLabel } from 'src/utils/ingestion-status'

const state = vi.hoisted(() => ({
  items: [] as Array<Record<string, unknown>>,
}))

vi.mock('src/composables/use-knowledge', () => ({
  useFolderContents: () => ({
    data: { value: { items: state.items, nextCursor: null } },
    isFetching: { value: false },
    isLoading: { value: false },
    isError: { value: false },
    refetch: vi.fn(),
  }),
  useKnowledgeMutations: () => ({ deleteDocument: { mutateAsync: vi.fn() } }),
}))

import KnowledgeList from '../../src/components/KnowledgeList.vue'

const stubs = {
  'q-linear-progress': defineComponent({ template: '<div />' }),
  'q-menu': defineComponent({ template: '<div><slot /></div>' }),
}

function row(overrides: Record<string, unknown>) {
  return {
    id: overrides.id,
    kind: overrides.kind,
    title: overrides.title,
    lifecycle: 'active',
    orderKey: 1,
    version: 1,
    ...overrides,
  }
}

describe('ingestion status mapping', () => {
  test('maps file states to Chinese labels with token colors', () => {
    expect(fileStateView('pending')).toMatchObject({ tone: 'pending', label: '处理中', color: 'var(--tk-warning)' })
    expect(fileStateView('ready')).toMatchObject({ tone: 'ready', label: '已就绪', color: 'var(--tk-success)' })
    expect(fileStateView('failed')).toMatchObject({ tone: 'failed', label: '处理失败', color: 'var(--tk-danger)' })
  })

  test('falls back to the raw server value for unknown states', () => {
    expect(fileStateView('archived')).toMatchObject({ tone: 'unknown', label: 'archived' })
    expect(fileStateView(null)).toMatchObject({ tone: 'unknown', label: '' })
    expect(fileStateView(undefined)).toMatchObject({ tone: 'unknown', label: '' })
  })

  test('maps stages and job statuses, falling back to raw values', () => {
    expect(stageLabel('parse')).toBe('解析')
    expect(stageLabel('chunk')).toBe('切分')
    expect(stageLabel('embed')).toBe('向量化')
    expect(stageLabel('ocr')).toBe('ocr')

    expect(jobStatusLabel('queued')).toBe('排队中')
    expect(jobStatusLabel('running')).toBe('处理中')
    expect(jobStatusLabel('retryable')).toBe('重试中')
    expect(jobStatusLabel('blocked')).toBe('等待中')
    expect(jobStatusLabel('cancel_requested')).toBe('取消中')
    expect(jobStatusLabel('succeeded')).toBe('已完成')
    expect(jobStatusLabel('cancelled')).toBe('已取消')
    expect(jobStatusLabel('failed')).toBe('处理失败')
    expect(jobStatusLabel('dead_letter')).toBe('处理失败')
    expect(jobStatusLabel('weird')).toBe('weird')

    expect(jobStatusColor('succeeded')).toBe('var(--tk-success)')
    expect(jobStatusColor('failed')).toBe('var(--tk-danger)')
    expect(jobStatusColor('running')).toBe('var(--tk-accent)')
    expect(jobStatusColor('unknown')).toBe('var(--tk-text-tertiary)')
  })
})

describe('KnowledgeList ingestion status', () => {
  beforeEach(() => {
    state.items = [
      row({ id: 'folder-1', kind: 'folder', title: 'Folder' }),
      row({ id: 'file-pending', kind: 'file', title: 'a.txt', fileState: 'pending' }),
      row({ id: 'file-ready', kind: 'file', title: 'b.txt', fileState: 'ready' }),
      row({ id: 'file-failed', kind: 'file', title: 'c.txt', fileState: 'failed' }),
      row({ id: 'note-1', kind: 'note', title: 'Note' }),
    ]
  })

  test('renders Chinese labels, no lock icon, and keeps the row menu for pending files', () => {
    const wrapper = mount(KnowledgeList, { props: { folderId: 'folder-1' }, global: { stubs } })
    const text = wrapper.text()

    expect(text).toContain('处理中')
    expect(text).toContain('已就绪')
    expect(text).toContain('处理失败')
    expect(text).not.toContain('存储迁移待完成')
    expect(text).not.toContain('pending')
    expect(text).not.toContain('ready')
    expect(text).not.toContain('failed')

    expect(wrapper.find('[title="存储迁移完成前，文件操作不可用"]').exists()).toBe(false)
    expect(wrapper.find('[name="sym_o_lock"]').exists()).toBe(false)
    expect(wrapper.find('[name="sym_o_pending"]').exists()).toBe(true)
    expect(wrapper.find('[name="sym_o_task_alt"]').exists()).toBe(true)
    expect(wrapper.find('[name="sym_o_error"]').exists()).toBe(true)

    // Pending files must remain deletable (regression: the old lock branch hid the menu).
    const rows = wrapper.findAll('.kb-row')
    expect(rows).toHaveLength(5)
    expect(rows[1]!.find('.kb-row-menu').exists()).toBe(true)
    // Every non-folder row exposes the menu; the folder does not.
    expect(wrapper.findAll('.kb-row-menu')).toHaveLength(4)
  })

  test('falls back to the raw value for an unknown file state', () => {
    state.items = [row({ id: 'file-x', kind: 'file', title: 'x.txt', fileState: 'archived' })]
    const wrapper = mount(KnowledgeList, { props: { folderId: 'folder-1' }, global: { stubs } })
    expect(wrapper.text()).toContain('archived')
  })
})
