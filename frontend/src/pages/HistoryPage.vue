<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useRouter } from 'vue-router'
import { useBaziClient } from '@/api'
import type { HistoryDTO } from '@/api/schema'
import { chartMetaKey, currentUserId } from '@/utils/user-context'

const client = useBaziClient()
const router = useRouter()
const queryClient = useQueryClient()
const userId = currentUserId()
const historyQueryKey = ['history', userId] as const
const editing = ref<Record<string, string>>({})
const search = ref('')
const filter = ref<'all' | 'male' | 'female'>('all')
const openMenu = ref<string | null>(null)
const { data, isLoading, isError, error } = useQuery<HistoryDTO>({
  queryKey: historyQueryKey,
  queryFn: () => client.getHistory(),
})

type ChartMeta = { name?: string; gender?: string; birthDate?: string; city?: string }
function metaFor(chartId: string): ChartMeta {
  const raw = localStorage.getItem(chartMetaKey(chartId))
  if (!raw) return {}
  try { return JSON.parse(raw) as ChartMeta } catch { return {} }
}

const visibleCharts = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  return (data.value?.charts ?? []).filter((chart) => {
    const meta = metaFor(chart.chart_id)
    const genderMatch = filter.value === 'all' || meta.gender === filter.value
    const keywordMatch = !keyword || [meta.name, meta.birthDate, meta.city, chart.note, chart.chart_id]
      .some((item) => String(item ?? '').toLowerCase().includes(keyword))
    return genderMatch && keywordMatch
  })
})

async function saveNote(chartId: string, current: string) {
  await client.setChartNote(chartId, editing.value[chartId] ?? current)
  openMenu.value = null
  await queryClient.invalidateQueries({ queryKey: historyQueryKey })
}

async function remove(chartId: string) {
  if (!window.confirm('确定删除这个命盘吗？')) return
  await client.deleteChart(chartId)
  localStorage.removeItem(chartMetaKey(chartId))
  await queryClient.invalidateQueries({ queryKey: historyQueryKey })
}

async function reanalyse(chartId: string) {
  const job = await client.startAnalysis(chartId, ['重新分析命局、事业财运、感情与流运'])
  await router.push({ name: 'analysis-progress', params: { jobId: job.job_id } })
}
</script>

<template>
  <section class="history-page" aria-labelledby="history-title">
    <header class="history-switcher">
      <button class="active" type="button">用户列表</button><button type="button" disabled>名人库</button><span class="vip-corner">VIP</span>
    </header>
    <h1 id="history-title" class="sr-only">用户列表</h1>

    <div class="search-bar card-surface">
      <span aria-hidden="true">⌕</span><input v-model="search" placeholder="请输入搜索内容" />
      <button type="button" @click="filter = filter === 'all' ? 'male' : filter === 'male' ? 'female' : 'all'">
        {{ filter === 'all' ? '筛选' : filter === 'male' ? '男' : '女' }}
      </button>
    </div>

    <div class="record-tabs">
      <button type="button" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
      <button type="button" :class="{ active: filter === 'male' }" @click="filter = 'male'">男</button>
      <button type="button" :class="{ active: filter === 'female' }" @click="filter = 'female'">女</button>
    </div>

    <p v-if="isLoading" class="state-card">正在加载命盘记录…</p>
    <p v-else-if="isError" class="state-card error-card" role="alert">{{ error?.message }}</p>
    <div v-else-if="!visibleCharts.length" class="empty-state card-surface">
      <span>☯</span><strong>暂无匹配命盘</strong><RouterLink to="/charts/new">新建第一个命盘</RouterLink>
    </div>

    <div v-else class="user-list">
      <article v-for="chart in visibleCharts" :key="chart.chart_id" class="user-list-item">
        <RouterLink class="user-main" :to="{ name: 'chart-overview', params: { chartId: chart.chart_id } }">
          <div>
            <strong>{{ metaFor(chart.chart_id).name || '未命名命盘' }} <small>{{ metaFor(chart.chart_id).gender === 'female' ? '女' : metaFor(chart.chart_id).gender === 'male' ? '男' : '' }}</small></strong>
            <span>阳历 {{ metaFor(chart.chart_id).birthDate || chart.created_at.slice(0, 10) }}</span>
            <em v-if="chart.note">{{ chart.note }}</em>
          </div>
          <div class="user-pillars">
            <span>{{ metaFor(chart.chart_id).city || '命盘' }}</span>
            <i>{{ chart.calculation_status === 'passed' ? '已排盘' : chart.calculation_status }}</i>
          </div>
          <div class="round-seal" aria-hidden="true">命</div>
        </RouterLink>
        <button class="more-button" type="button" aria-label="更多操作" @click="openMenu = openMenu === chart.chart_id ? null : chart.chart_id">⋮</button>
        <div v-if="openMenu === chart.chart_id" class="record-menu card-surface">
          <label>备注<input v-model="editing[chart.chart_id]" :placeholder="chart.note || '添加备注'" maxlength="500" /></label>
          <button type="button" @click="saveNote(chart.chart_id, chart.note)">保存备注</button>
          <button type="button" @click="reanalyse(chart.chart_id)">重新分析</button>
          <button type="button" class="danger-text" @click="remove(chart.chart_id)">删除命盘</button>
        </div>
      </article>
    </div>

    <RouterLink class="floating-add" to="/charts/new" aria-label="新增命盘">＋</RouterLink>

    <section v-if="data?.reports.length" class="recent-reports card-surface">
      <h2>最近报告</h2>
      <RouterLink v-for="report in data.reports.slice(0, 5)" :key="report.report_id" :to="`/reports/${report.report_id}`">
        <strong>{{ report.title }}</strong><span>{{ report.generated_at.slice(0, 10) }}</span>
      </RouterLink>
    </section>
  </section>
</template>
