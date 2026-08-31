import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, test, vi } from 'vitest'
import AskComposer from 'src/components/AskComposer.vue'

/*
 * The scope picker is exercised through a stubbed FolderPickerList that emits
 * selections the same way the real lazy tree does.
 */
vi.mock('src/components/FolderPickerList.vue', () => ({
  default: {
    props: { kbId: String, selectedId: String },
    emits: ['select'],
    template: `<div data-testid="folder-picker-stub">
      <button data-testid="pick-folder-a" @click="$emit('select', { id: 'folder-a', title: 'Folder A' })">Folder A</button>
      <button data-testid="pick-whole-kb" @click="$emit('select', null)">整个知识库</button>
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
  return mount(AskComposer, {
    props,
    global: { plugins: [pinia], stubs },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AskComposer', () => {
  test('defaults the scope chip to the whole knowledge base', () => {
    const wrapper = mountComposer({ kbId: 'kb-1' })
    const chip = wrapper.find('[data-testid="ask-scope-chip"]')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('整个知识库')
  })

  test('picks a folder scope from the picker and can return to the knowledge base', async () => {
    const wrapper = mountComposer({ kbId: 'kb-1' })
    await wrapper.find('[data-testid="pick-folder-a"]').trigger('click')
    expect(wrapper.find('[data-testid="ask-scope-chip"]').text()).toContain('Folder A')
    await wrapper.find('[data-testid="pick-whole-kb"]').trigger('click')
    expect(wrapper.find('[data-testid="ask-scope-chip"]').text()).toContain('整个知识库')
  })

  test('blocks sending in home mode without a selected knowledge base', async () => {
    const wrapper = mountComposer({ kbId: '' })
    // Without a knowledge base the scope control is hidden entirely.
    expect(wrapper.find('[data-testid="ask-scope-chip"]').exists()).toBe(false)
    const textarea = wrapper.get('textarea')
    await textarea.setValue('What is the policy?')
    const send = wrapper.find('[data-testid="ask-send"]')
    expect((send.element as HTMLButtonElement).disabled).toBe(true)
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  test('submits trimmed text on Enter and clears the textarea', async () => {
    const wrapper = mountComposer({ kbId: 'kb-1' })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('  What is the policy?  ')
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toEqual([['What is the policy?']])
    expect((textarea.element as HTMLTextAreaElement).value).toBe('')
  })

  test('Shift+Enter keeps the newline, Ctrl+Enter also submits', async () => {
    const wrapper = mountComposer({ kbId: 'kb-1' })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('line one')
    await textarea.trigger('keydown', { key: 'Enter', shiftKey: true })
    expect(wrapper.emitted('submit')).toBeUndefined()
    await textarea.trigger('keydown', { key: 'Enter', ctrlKey: true })
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  test('conversation mode can send without a knowledge base prop', async () => {
    const wrapper = mountComposer({ mode: 'conversation' })
    const textarea = wrapper.get('textarea')
    await textarea.setValue('Follow up')
    await textarea.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toEqual([['Follow up']])
  })
})
