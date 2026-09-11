import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import SectionHeader from '../../src/components/SectionHeader.vue'

describe('SectionHeader', () => {
  test('renders title and description', () => {
    const wrapper = mount(SectionHeader, {
      props: { title: '服务访问', description: '创建 OAuth 服务主体以访问 MCP 接口' },
    })
    expect(wrapper.find('.tk-section-header-title').text()).toBe('服务访问')
    expect(wrapper.find('.tk-section-header-desc').text()).toContain('OAuth 服务主体')
  })

  test('renders the accent icon only when provided', () => {
    const withIcon = mount(SectionHeader, {
      props: { icon: 'sym_o_key', title: '权限范围' },
    })
    expect(withIcon.find('[name="sym_o_key"]').exists()).toBe(true)

    const withoutIcon = mount(SectionHeader, { props: { title: '权限范围' } })
    expect(withoutIcon.find('.tk-section-header-icon').exists()).toBe(false)
  })

  test('renders the actions slot on the right', () => {
    const wrapper = mount(SectionHeader, {
      props: { icon: 'sym_o_link', title: '已连接智能体' },
      slots: { actions: '<button class="manage">管理</button>' },
    })
    expect(wrapper.find('.tk-section-header-actions').exists()).toBe(true)
    expect(wrapper.find('.manage').exists()).toBe(true)
  })
})
