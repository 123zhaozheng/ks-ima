import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import PaneEmptyState from '../../src/components/PaneEmptyState.vue'

describe('PaneEmptyState', () => {
  test('renders icon, title and description', () => {
    const wrapper = mount(PaneEmptyState, {
      props: {
        icon: 'sym_o_description_off',
        title: '暂不支持预览',
        description: '该文件已成功处理并可被检索，但当前格式无法在浏览器中预览。',
      },
    })
    expect(wrapper.find('[name="sym_o_description_off"]').exists()).toBe(true)
    expect(wrapper.find('.tk-pane-empty-title').text()).toBe('暂不支持预览')
    expect(wrapper.find('.tk-pane-empty-desc').text()).toContain('无法在浏览器中预览')
  })

  test('omits the description block when not provided', () => {
    const wrapper = mount(PaneEmptyState, {
      props: { icon: 'sym_o_draft', title: '暂无文件' },
    })
    expect(wrapper.find('.tk-pane-empty-title').text()).toBe('暂无文件')
    expect(wrapper.find('.tk-pane-empty-desc').exists()).toBe(false)
    expect(wrapper.find('.tk-pane-empty-actions').exists()).toBe(false)
  })

  test('renders the actions slot', () => {
    const wrapper = mount(PaneEmptyState, {
      props: { icon: 'sym_o_error', title: '预览加载失败' },
      slots: { actions: '<button class="retry">重试</button>' },
    })
    expect(wrapper.find('.tk-pane-empty-actions').exists()).toBe(true)
    expect(wrapper.find('.retry').exists()).toBe(true)
  })
})
