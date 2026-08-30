import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import { ref } from 'vue'
import WorkspaceOverview from '../../src/pages/WorkspaceOverview.vue'

const workspaceState = {
  id: ref<string | null>('workspace-1'),
  workspace: ref({ name: 'Knowledge' }),
  member: { role: 'workspace_admin' },
}

vi.mock('src/stores/workspace', () => ({ useWorkspaceStore: () => workspaceState }))
vi.mock('src/stores/ui-state', () => ({ useUiStateStore: () => ({ toggleMainDrawer: () => undefined }) }))
vi.mock('quasar', async () => {
  const actual = await vi.importActual<typeof import('quasar')>('quasar')
  return { ...actual, useQuasar: () => ({ dialog: vi.fn() }) }
})

const response = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }))
const uiStubs = {
  'q-tabs': { template: '<div><slot /></div>' },
  'q-tab': { props: { label: String }, template: '<div>{{ label }}</div>' },
  'q-tab-panels': { template: '<div><slot /></div>' },
  'q-tab-panel': { template: '<div><slot /></div>' },
  'q-icon': { template: '<span />' },
  'q-menu': { template: '<div><slot /></div>' },
  'q-btn': { props: { label: String }, template: '<button>{{ label }}<slot /></button>' },
}

describe('WorkspaceOverview', () => {
  beforeEach(() => {
    workspaceState.member = { role: 'workspace_admin' }
    globalThis.fetch = vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (/\/workspaces\/(?:workspace-1|%5Bobject%20Object%5D)(?:$|\?)/.test(path)) return response({ id: 'workspace-1', name: 'Knowledge', role: workspaceState.member.role, isActive: true })
      if (path.includes('/members')) return response([{ workspaceId: 'workspace-1', userId: 'user-1', displayName: 'Alice', email: 'alice@example.test', role: 'viewer', state: 'active', version: 1 }])
      if (path.includes('/groups')) return response([{ id: 'group-1', workspaceId: 'workspace-1', name: 'Readers', version: 1, memberCount: 1 }])
      if (path.includes('/folders')) return response([{ id: 'workspace-1', workspaceId: 'workspace-1', parentId: null, name: 'Knowledge', orderKey: 0, lifecycle: 'active', version: 1, isRoot: true, aclAnchorId: 'workspace-1' }])
      return response({})
    }) as unknown as typeof fetch
  })

  test('renders member, group, and directory permission surfaces for an administrator', async () => {
    const wrapper = mount(WorkspaceOverview, { global: { stubs: uiStubs } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(wrapper.text()).toContain('Workspace administration')
    expect((globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(call => String(call[0]).includes('/members'))).toBe(true)
    expect(wrapper.text()).toContain('Readers')
    expect(wrapper.text()).toContain('Directory permissions')
    expect(wrapper.text()).toContain('Add member')
  })

  test('hides mutation controls for a viewer while keeping readable workspace state', async () => {
    workspaceState.member = { role: 'viewer' }
    const wrapper = mount(WorkspaceOverview, { global: { stubs: uiStubs } })
    await new Promise(resolve => setTimeout(resolve, 0))
    expect((globalThis.fetch as unknown as ReturnType<typeof vi.fn>).mock.calls.some(call => String(call[0]).includes('/members'))).toBe(true)
    expect(wrapper.text()).not.toContain('Add member')
    expect(wrapper.text()).not.toContain('Create group')
  })
})
