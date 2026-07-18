import { createRouter, createWebHistory } from 'vue-router'
import LandingPage from '@/pages/LandingPage.vue'
import ChartNewWizard from '@/pages/ChartNewWizard.vue'
import ChartOverviewPage from '@/pages/ChartOverviewPage.vue'
import TemporalPage from '@/pages/TemporalPage.vue'
import ChatPage from '@/pages/ChatPage.vue'
import ReportReadPage from '@/pages/ReportReadPage.vue'
import AnalysisProgressPage from '@/pages/AnalysisProgressPage.vue'
import HistoryPage from '@/pages/HistoryPage.vue'
import SettingsPage from '@/pages/SettingsPage.vue'
import LoginPage from '@/pages/LoginPage.vue'
import RegisterPage from '@/pages/RegisterPage.vue'
import AdminPage from '@/pages/AdminPage.vue'
import { useBaziClient } from '@/api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginPage, meta: { title: '登录', public: true } },
    { path: '/register', name: 'register', component: RegisterPage, meta: { title: '注册', public: true } },
    { path: '/admin', name: 'admin', component: AdminPage, meta: { title: '系统后台', admin: true } },
    { path: '/', name: 'home', component: LandingPage, meta: { title: '首页排盘' } },
    { path: '/charts/new', name: 'chart-new', component: ChartNewWizard, meta: { title: '新建命盘' } },
    { path: '/charts/:chartId', name: 'chart-overview', component: ChartOverviewPage, props: true, meta: { title: '基本排盘' } },
    { path: '/charts/:chartId/temporal', name: 'temporal', component: TemporalPage, props: true, meta: { title: '流运排盘' } },
    { path: '/charts/:chartId/chat', name: 'chart-chat', component: ChatPage, props: true, meta: { title: '运势问答' } },
    { path: '/reports/:reportId', name: 'report-read', component: ReportReadPage, props: true, meta: { title: '命理分析' } },
    { path: '/reports/:reportId/print', name: 'report-print', component: ReportReadPage, props: (route) => ({ reportId: route.params.reportId, printMode: true }), meta: { title: '分析报告' } },
    { path: '/jobs/:jobId', name: 'analysis-progress', component: AnalysisProgressPage, props: true, meta: { title: '生成分析' } },
    { path: '/history', name: 'history', component: HistoryPage, meta: { title: '用户列表' } },
    { path: '/settings', name: 'settings', component: SettingsPage, meta: { title: '设置' } },
  ],
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})


router.beforeEach(async (to) => {
  if (to.meta.public) return true
  const cached = sessionStorage.getItem('bazi:current-user')
  try {
    const user = cached ? JSON.parse(cached) : await useBaziClient().getCurrentUser()
    sessionStorage.setItem('bazi:current-user', JSON.stringify(user))
    if (to.meta.admin && user.role !== 'admin') return '/'
    return true
  } catch {
    sessionStorage.removeItem('bazi:current-user')
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

export default router
