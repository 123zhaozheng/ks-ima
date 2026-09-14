import { mount } from '@vue/test-utils'
import { describe, expect, test } from 'vitest'
import AskToolTrace from 'src/components/AskToolTrace.vue'

describe('AskToolTrace', () => {
  test('is collapsed by default and reveals bounded tool details on demand', async () => {
    const wrapper = mount(AskToolTrace, {
      props: {
        calls: [{
          name: 'search_knowledge',
          arguments: { query: 'policy' },
          hitCount: 2,
          round: 1,
        }],
      },
    })

    expect(wrapper.find('[data-testid="ask-tool-trace"]').exists()).toBe(true)
    expect(wrapper.find('.ask-tool-trace-list').exists()).toBe(false)
    await wrapper.find('.ask-tool-trace-toggle').trigger('click')
    expect(wrapper.find('.ask-tool-trace-list').text()).toContain('policy')
    expect(wrapper.find('.ask-tool-trace-toggle').attributes('aria-expanded')).toBe('true')
  })
})
