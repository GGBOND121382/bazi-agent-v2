/**
 * Wizard unit tests — draft persistence + validation transitions.
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ChartNewWizard from '@/pages/ChartNewWizard.vue'

function buildRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/charts/new', component: ChartNewWizard, name: 'chart-new' },
      { path: '/charts/:chartId', component: { template: '<div />' }, name: 'chart-overview', props: true },
    ],
  })
}

describe('ChartNewWizard', () => {
  it('renders step 1 by default', async () => {
    setActivePinia(createPinia())
    const router = buildRouter()
    router.push('/charts/new')
    await router.isReady()
    const wrapper = mount(ChartNewWizard, { global: { plugins: [router] } })
    expect(wrapper.text()).toContain('第 1 / 4 步')
    expect(wrapper.find('fieldset legend').text()).toContain('身份')
  })

  it('persists a draft to localStorage on advance', async () => {
    setActivePinia(createPinia())
    localStorage.clear()
    const router = buildRouter()
    router.push('/charts/new')
    await router.isReady()
    const wrapper = mount(ChartNewWizard, { global: { plugins: [router] } })
    // Use the explicit testid button — submit semantics are harder to drive
    // through Vue Test Utils + happy-dom without a real form submit cycle.
    await wrapper.find('[data-testid="next"]').trigger('click')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('bazi:draft:birth')).toBeTruthy()
  })
})