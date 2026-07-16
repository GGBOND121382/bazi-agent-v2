<script setup lang="ts">
/**
 * Chart overview (F3 + I1 wiring). Reads the chart from the API and
 * displays the four 柱 + relations + 五行 + assumptions.
 *
 * Mock-data fast-path when VITE_USE_MOCKS=true: loads the example file
 * from contracts/examples/chart_overview.mock.json.
 */
import { computed } from 'vue'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import { useBaziClient, ApiError } from '@/api'
import type { ChartOverviewViewDTO } from '@/api'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const router = useRouter()
const analysisStarting = ref(false)
const analysisError = ref<string | null>(null)
const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'

const { data, error, isLoading, isError, isFetching, refetch } = useQuery<ChartOverviewViewDTO>({
  queryKey: computed(() => ['chart-overview', props.chartId]),
  queryFn: async () => {
    if (useMocks) {
      const url = new URL('@contracts/examples/chart_overview.mock.json', import.meta.url)
      const r = await fetch(url.href)
      return (await r.json()) as ChartOverviewViewDTO
    }
    return client.getChartOverviewView(props.chartId)
  },
  staleTime: 60_000,
})

const dataState = computed(() => {
  if (isLoading.value) return 'loading'
  if (isError.value) return 'error'
  if (isFetching.value) return 'stale'
  if (!data.value || data.value.pillars.length === 0) return 'empty'
  return 'partial'
})

const apiErrorMessage = computed(() => {
  if (error.value instanceof ApiError) {
    return `${error.value.detail.error_code}: ${error.value.detail.message_key}`
  }
  return error.value?.message ?? null
})

async function startAnalysis() {
  analysisStarting.value = true
  analysisError.value = null
  try {
    const job = await client.startAnalysis(props.chartId, ['命局结构与证据'])
    await router.push({ name: 'analysis-progress', params: { jobId: job.job_id } })
  } catch (cause) {
    analysisError.value = cause instanceof Error ? cause.message : '无法启动分析'
  } finally {
    analysisStarting.value = false
  }
}
</script>

<template>
  <section aria-labelledby="overview-title" :data-state="dataState">
    <h1 id="overview-title">命盘总览</h1>

    <p v-if="isLoading" data-state="loading">正在加载确定性事实…</p>
    <p v-else-if="isError" data-state="error" role="alert">
      无法加载命盘：{{ apiErrorMessage }}
      <button @click="refetch()">重试</button>
    </p>
    <p v-else-if="!data || data.pillars.length === 0" data-state="empty">尚无数据。</p>

    <template v-else>
      <table aria-label="四柱">
        <thead>
          <tr>
            <th>位置</th>
            <th>天干</th>
            <th>地支</th>
            <th>十神</th>
            <th>藏干</th>
            <th>纳音</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in data.pillars" :key="p.position">
            <td>{{ p.position }}</td>
            <td>{{ p.stem }}</td>
            <td>{{ p.branch }}</td>
            <td>{{ p.ten_god ?? '—' }}</td>
            <td>{{ p.hidden_stems.map((h) => h.stem).join(' ') }}</td>
            <td>{{ p.nayin ?? '—' }}</td>
          </tr>
        </tbody>
      </table>

      <h2>假设</h2>
      <ul>
        <li v-for="(a, i) in data.assumptions" :key="i">
          <strong>{{ a.label }}：</strong>{{ a.value }}
        </li>
      </ul>

      <h2>关系</h2>
      <ul v-if="data.relationships.length">
        <li v-for="(r, i) in data.relationships" :key="i">
          {{ r.label }}（{{ r.participants.join(' / ') }}）
        </li>
      </ul>
      <p v-else>未发现显著关系。</p>

      <div v-if="data.warnings.length">
        <strong>注意：</strong>
        <ul>
          <li v-for="(w, i) in data.warnings" :key="i">{{ w.message }}</li>
        </ul>
      </div>
      <div class="page-actions">
        <RouterLink :to="{ name: 'temporal', params: { chartId } }">查看流运</RouterLink>
        <button type="button" :disabled="analysisStarting" @click="startAnalysis">
          {{ analysisStarting ? '正在创建任务…' : '生成结构化分析' }}
        </button>
      </div>
      <p v-if="analysisError" data-state="error" role="alert">{{ analysisError }}</p>
    </template>
  </section>
</template>
