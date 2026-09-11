import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import StatusBadge from '../../src/components/StatusBadge.vue'

describe('StatusBadge', () => {
  test('renders the 12px label with the tone class', () => {
    const wrapper = mount(StatusBadge, { props: { tone: 'success', label: '已就绪' } })
    expect(wrapper.text()).toContain('已就绪')
    expect(wrapper.find('.tk-status-badge--success').exists()).toBe(true)
    expect(wrapper.find('.tk-status-badge-dot').exists()).toBe(false)
  })

  test('shows a dot when requested', () => {
    const wrapper = mount(StatusBadge, { props: { tone: 'success', label: '已就绪', dot: true } })
    expect(wrapper.find('.tk-status-badge-dot').exists()).toBe(true)
  })

  test('shows a 14px icon instead of the dot when given', () => {
    const wrapper = mount(StatusBadge, {
      props: { tone: 'warning', label: '处理中', icon: 'sym_o_schedule' },
    })
    expect(wrapper.find('.tk-status-badge-dot').exists()).toBe(false)
    expect(wrapper.find('[name="sym_o_schedule"]').exists()).toBe(true)
  })

  test('supports the muted tone (tertiary text color)', () => {
    const wrapper = mount(StatusBadge, { props: { tone: 'muted', label: '只读' } })
    expect(wrapper.find('.tk-status-badge--muted').exists()).toBe(true)
    expect(wrapper.text()).toContain('只读')
  })
})
