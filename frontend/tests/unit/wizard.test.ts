/** Birth form unit tests — mobile rendering and draft persistence. */
import { beforeEach, describe, expect, it } from 'vitest'
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

async function mountForm() {
  setActivePinia(createPinia())
  const router = buildRouter()
  await router.push('/charts/new')
  await router.isReady()
  return mount(ChartNewWizard, { global: { plugins: [router] } })
}

describe('ChartNewWizard', () => {
  beforeEach(() => localStorage.clear())

  it('renders the redesigned birth form', async () => {
    const wrapper = await mountForm()
    expect(wrapper.text()).toContain('建立命盘')
    expect(wrapper.text()).toContain('真太阳时校正')
    expect(wrapper.text()).toContain('公历')
    expect(wrapper.find('[data-testid="submit"]').exists()).toBe(true)
    expect(wrapper.find('input[type="date"]').exists()).toBe(true)
    expect(wrapper.find('input[type="time"]').exists()).toBe(true)
  })

  it('persists a draft when birth information changes', async () => {
    const wrapper = await mountForm()
    const dateInput = wrapper.find('input[type="date"]')
    await dateInput.setValue('1995-12-22')
    await dateInput.trigger('change')
    const draft = localStorage.getItem('bazi:draft:birth')
    expect(draft).toBeTruthy()
    expect(JSON.parse(draft ?? '{}').birthDate).toBe('1995-12-22')
  })
})
