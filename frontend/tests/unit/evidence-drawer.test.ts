import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EvidenceDrawer from '@/components/EvidenceDrawer.vue'

describe('EvidenceDrawer', () => {
  it('separates fact, rule and model layers without rendering HTML', () => {
    const wrapper = mount(EvidenceDrawer, {
      props: {
        open: true,
        items: [
          { id: 'f', layer: 'fact', title: '事实', detail: '<script>bad()</script>' },
          { id: 'r', layer: 'rule', title: '规则', detail: '审核规则' },
          { id: 'm', layer: 'model', title: '归纳', detail: '模型归纳' },
        ],
      },
    })
    expect(wrapper.findAll('.evidence-card')).toHaveLength(3)
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>bad()</script>')
  })
})
