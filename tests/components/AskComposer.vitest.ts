import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import AskComposer from 'src/components/AskComposer.vue'
import { useAskContextStore } from 'src/stores/ask-context'

/*
 * The scope picker is exercised through a stubbed FolderPickerList that emits
 * selections the same way the real lazy tree does.
 */
vi.mock('src/components/FolderPickerList.vue', () => ({
  default: {
    props: { workspaceId: String, selectedId: String },
    emits: ['select'],
    template: `<div data-testid="folder-picker-stub">
      <button data-testid="pick-folder-a" @click="$emit('select', { id: 'folder-a', title: 'Folder A' })">Folder A</button>
      <button data-testid="pick-whole-workspace" @click="$emit('select', null)">Whole workspace</button>
    </div>`,
  },
}))

const stubs = {
  'q-input': {
    props: { modelValue: String, disable: Boolean, placeholder: String },
    template: '<textarea :value="modelValue" :disabled="disable" :placeholder="placeholder" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'q-btn': {
    props: { label: String, disable: Boolean, icon: String },
    template: '<button :disabled="disable"><slot />{{ label }}</button>',
  },
  'q-chip': {
    template: '<span data-testid="scope-doc-chip"><slot /><button data-testid="chip-remove" @click="$emit(\'remove\')" /></span>',
  },
  'q-menu': { template: '<div><slot /></div>' },
  'q-space': { template: '<span />' },
  'q-icon': { template: '<span><slot /></span>' },
}

function mountComposer(props: Record<string, unknown> = {}) {
  const pinia = createPinia()
  const wrapper = mount(AskComposer, {
    props,
    global: { plugins: [pinia], stubs },
  })
  return { wrapper, pinia }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AskComposer', () => {
  test('defaults the scope chip to the whole workspace', () => {
    const { wrapper } = mountComposer({ workspaceId: 'workspace-1' })
    const chip = wrapper.find('[data-testid="ask-scope-chip"]')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('Whole workspace')
  })

  test('picks a folder scope from the picker and can return to the workspace', async () => {
    const { wrapper } = mountComposer({ workspaceId: 'workspace-1' })
    await wrapper.find('[data-testid="pick-folder-a"]').trigger('click')
    expect(wrapper.find('[data-testid="ask-scope-chip"]').text()).toContain('Folder A')
    await wrapper.find('[data-testid="pick-whole-workspace"]').trigger('click')
    expect(wrapper.find('[data-testid="ask-scope-chip"]').text()).toContain('Whole workspace')
  })

  test('submits trimmed text on Enter and clears the textarea', async () => {
    const { wrapper } = mountComposer({ workspaceId: 'workspace-1' })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('  What is the policy?  ')
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toEqual([['What is the policy?']])
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  test('Shift+Enter keeps the newline, Ctrl+Enter also submits', async () => {
    const { wrapper } = mountComposer({ workspaceId: 'workspace-1' })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('line one')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(wrapper.emitted('submit')).toBeUndefined()
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(wrapper.emitted('submit')).toEqual([['line one']])
  })

  test('does not submit while busy and hides the scope chip in conversation mode', async () => {
    const { wrapper } = mountComposer({ mode: 'conversation', busy: true })
    expect(wrapper.find('[data-testid="ask-scope-chip"]').exists()).toBe(false)
    const textarea = wrapper.get('textarea')
    await textarea.setValue('follow up')
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  test('shows the document prefill from the ask-context store and clears it on submit', async () => {
    const { wrapper } = mountComposer({ workspaceId: 'workspace-1' })
    const askContext = useAskContextStore()
    askContext.askAboutDocument('note-1', 'Draft note')
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="ask-scope-chip"]').text()).toContain('Draft note')

    const textarea = wrapper.get('textarea')
    await textarea.setValue('Tell me about it')
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toEqual([['Tell me about it']])
    expect(askContext.hasDocumentScope).toBe(false)
  })

  test('removing the document chip restores the folder scope picker', async () => {
    const { wrapper } = mountComposer({ workspaceId: 'workspace-1' })
    const askContext = useAskContextStore()
    askContext.askAboutDocument('note-1', 'Draft note')
    await wrapper.vm.$nextTick()
    await wrapper.find('[data-testid="chip-remove"]').trigger('click')
    expect(askContext.hasDocumentScope).toBe(false)
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[data-testid="ask-scope-chip"]').exists()).toBe(true)
  })
})
