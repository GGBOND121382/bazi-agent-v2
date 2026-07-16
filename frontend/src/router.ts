import { createRouter, createWebHistory } from 'vue-router'
import LandingPage from '@/pages/LandingPage.vue'
import ChartNewWizard from '@/pages/ChartNewWizard.vue'
import ChartOverviewPage from '@/pages/ChartOverviewPage.vue'
import TemporalPage from '@/pages/TemporalPage.vue'
import ReportReadPage from '@/pages/ReportReadPage.vue'
import AnalysisProgressPage from '@/pages/AnalysisProgressPage.vue'
import HistoryPage from '@/pages/HistoryPage.vue'
import SettingsPage from '@/pages/SettingsPage.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: LandingPage },
    { path: '/charts/new', name: 'chart-new', component: ChartNewWizard },
    { path: '/charts/:chartId', name: 'chart-overview', component: ChartOverviewPage, props: true },
    { path: '/charts/:chartId/temporal', name: 'temporal', component: TemporalPage, props: true },
    { path: '/reports/:reportId', name: 'report-read', component: ReportReadPage, props: true },
    { path: '/reports/:reportId/print', name: 'report-print', component: ReportReadPage, props: (route) => ({ reportId: route.params.reportId, printMode: true }) },
    { path: '/jobs/:jobId', name: 'analysis-progress', component: AnalysisProgressPage, props: true },
    { path: '/history', name: 'history', component: HistoryPage },
    { path: '/settings', name: 'settings', component: SettingsPage },
  ],
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, behavior: 'smooth' }
    return { top: 0 }
  },
})
