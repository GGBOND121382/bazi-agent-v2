<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ref } from 'vue'
import { useBaziClient } from '@/api'

const client = useBaziClient()
const queryClient = useQueryClient()
const editing = ref<Record<string, string>>({})
const { data, isLoading, isError, error } = useQuery({ queryKey: ['history'], queryFn: () => client.getHistory() })

async function saveNote(chartId: string, current: string) {
  await client.setChartNote(chartId, editing.value[chartId] ?? current)
  await queryClient.invalidateQueries({ queryKey: ['history'] })
}

async function remove(chartId: string) {
  await client.deleteChart(chartId)
  await queryClient.invalidateQueries({ queryKey: ['history'] })
}

async function reanalyse(chartId: string) {
  const job = await client.startAnalysis(chartId, ['重新分析命局结构'])
  window.location.assign(`/jobs/${job.job_id}`)
}
</script>

<template>
  <section aria-labelledby="history-title"><p class="eyebrow">本地匿名工作区</p><h1 id="history-title">历史记录</h1>
    <p v-if="isLoading">正在加载…</p><p v-else-if="isError" role="alert">{{ error?.message }}</p>
    <template v-else-if="data">
      <h2>命盘</h2><p v-if="!data.charts.length">暂无命盘。</p>
      <article v-for="chart in data.charts" :key="chart.chart_id" class="history-card">
        <div><strong>{{ chart.chart_id }}</strong><span>{{ chart.calculation_status }} · {{ chart.created_at }}</span></div>
        <label>匿名备注 <input v-model="editing[chart.chart_id]" :placeholder="chart.note || '添加备注'" maxlength="500" /></label>
        <button type="button" @click="saveNote(chart.chart_id, chart.note)">保存备注</button>
        <button type="button" @click="reanalyse(chart.chart_id)">重新分析</button>
        <button type="button" @click="remove(chart.chart_id)">删除</button>
      </article>
      <h2>报告</h2><ul><li v-for="report in data.reports" :key="report.report_id"><RouterLink :to="`/reports/${report.report_id}`">{{ report.title }}</RouterLink></li></ul>
    </template>
  </section>
</template>
