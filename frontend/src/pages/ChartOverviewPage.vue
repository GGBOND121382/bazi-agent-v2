<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuery } from '@tanstack/vue-query'
import chartOverviewMock from '@contracts/examples/chart_overview.mock.json'
import { ApiError, useBaziClient } from '@/api'
import type {
  ChartOverviewViewDTO,
  ChartResultDTO,
  DeterministicPillarDetail,
} from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const router = useRouter()
const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'
const analysisStarting = ref(false)
const analysisError = ref<string | null>(null)
const displayName = ref('命盘')

onMounted(() => {
  const raw = localStorage.getItem(`bazi:chart-meta:${props.chartId}`)
  if (!raw) return
  try {
    const meta = JSON.parse(raw) as { name?: string }
    displayName.value = meta.name?.trim() || '命盘'
  } catch {
    displayName.value = '命盘'
  }
})

const { data, error, isLoading, isError, isFetching, refetch } = useQuery<{
  overview: ChartOverviewViewDTO
  chart: ChartResultDTO | null
}>({
  queryKey: computed(() => ['chart-overview-full', props.chartId]),
  queryFn: async () => {
    if (useMocks) {
      return {
        overview: chartOverviewMock as unknown as ChartOverviewViewDTO,
        chart: null,
      }
    }
    const [overview, chart] = await Promise.all([
      client.getChartOverviewView(props.chartId),
      client.getChart(props.chartId),
    ])
    return { overview, chart }
  },
  staleTime: 60_000,
})

const overview = computed(() => data.value?.overview)
const chart = computed(() => data.value?.chart)
const details = computed(() => chart.value?.calendar.deterministic_details)
const basic = computed(() => details.value?.basic ?? {})
const detailByPosition = computed<Record<string, DeterministicPillarDetail>>(() => {
  const items = details.value?.pillars ?? []
  return Object.fromEntries(items.map((item) => [item.position, item]))
})
const fiveElements = computed(() => details.value?.five_elements ?? overview.value?.five_elements ?? [])
const birthplaceText = computed(() => {
  const value = basic.value.birthplace
  if (!value || typeof value !== 'object' || Array.isArray(value)) return '—'
  const place = value as Record<string, unknown>
  const names = [place.province, place.city].map(String).filter((item) => item && item !== 'undefined')
  const longitude = typeof place.longitude === 'number' ? `东经${place.longitude.toFixed(2)}°` : ''
  const latitude = typeof place.latitude === 'number' ? `北纬${place.latitude.toFixed(2)}°` : ''
  return [...new Set(names), latitude, longitude].filter(Boolean).join('　') || '—'
})
const voidSummary = computed(() => {
  const values = [detailByPosition.value.year?.void, detailByPosition.value.day?.void].filter(Boolean)
  return [...new Set(values)].join('　') || '—'
})

const apiErrorMessage = computed(() => {
  if (error.value instanceof ApiError) return `${error.value.detail.error_code}: ${error.value.detail.message_key}`
  return error.value?.message ?? null
})

const positionLabels: Record<string, string> = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' }
const positionOrder = ['year', 'month', 'day', 'hour'] as const
const stemClass: Record<string, string> = {
  甲: 'wood', 乙: 'wood', 丙: 'fire', 丁: 'fire', 戊: 'earth', 己: 'earth',
  庚: 'metal', 辛: 'metal', 壬: 'water', 癸: 'water',
}
const branchClass: Record<string, string> = {
  寅: 'wood', 卯: 'wood', 巳: 'fire', 午: 'fire', 辰: 'earth', 戌: 'earth',
  丑: 'earth', 未: 'earth', 申: 'metal', 酉: 'metal', 子: 'water', 亥: 'water',
}

function textValue(key: string): string {
  const value = basic.value[key]
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return '—'
}

function detail(position: string): DeterministicPillarDetail | undefined {
  return detailByPosition.value[position]
}

async function startAnalysis() {
  analysisStarting.value = true
  analysisError.value = null
  try {
    const job = await client.startAnalysis(props.chartId, [
      '命局结构、旺衰、格局与喜忌',
      '事业、财运、感情与性格',
      '大运流年关键阶段',
    ])
    await router.push({ name: 'analysis-progress', params: { jobId: job.job_id } })
  } catch (cause) {
    analysisError.value = cause instanceof Error ? cause.message : '无法启动分析'
  } finally {
    analysisStarting.value = false
  }
}
</script>

<template>
  <section class="chart-page" aria-labelledby="overview-title">
    <p v-if="isLoading" class="state-card">正在加载确定性命盘…</p>
    <div v-else-if="isError" class="state-card error-card" role="alert">
      <p>无法加载命盘：{{ apiErrorMessage }}</p><button type="button" @click="refetch()">重试</button>
    </div>
    <p v-else-if="!overview" class="state-card">尚无命盘数据。</p>

    <template v-else>
      <nav class="chart-tabs" aria-label="命盘内容导航">
        <a href="#basic-info">基本信息</a><a class="active" href="#basic-chart">基本排盘</a>
        <a href="#detail-chart">专业细盘</a><RouterLink :to="{ name: 'chart-chat', params: { chartId } }">断事问答</RouterLink>
      </nav>

      <header class="chart-identity-card">
        <div class="zodiac-seal" aria-hidden="true">命</div>
        <div><p class="eyebrow">确定性命盘</p><h1 id="overview-title">{{ displayName }}</h1>
          <p>{{ chart?.pillars.map((item) => item.ganzhi).join('　') ?? overview.pillars.map((item) => `${item.stem}${item.branch}`).join('　') }}</p>
        </div>
        <span v-if="isFetching" class="refresh-badge">更新中</span>
      </header>

      <section id="basic-info" class="info-panel card-surface">
        <div class="info-row"><span>公历</span><strong>{{ textValue('solar_datetime') }}</strong></div>
        <div class="info-row"><span>农历</span><strong>{{ textValue('lunar_date') }}</strong></div>
        <div class="info-row"><span>真太阳时</span><strong>{{ textValue('true_solar_time') }}</strong></div>
        <div class="info-row"><span>出生地区</span><strong>{{ birthplaceText }}</strong></div>
        <div class="info-row"><span>人元司令分野</span><strong>{{ textValue('ren_yuan_commander') }}</strong></div>
        <div class="info-row"><span>出生节气</span><strong>{{ textValue('birth_solar_terms') }}</strong></div>
        <div class="info-pair"><div><span>生肖</span><strong>{{ textValue('zodiac') }}</strong></div><div><span>星座</span><strong>{{ textValue('western_zodiac') }}</strong></div></div>
        <div class="info-pair"><div><span>星宿</span><strong>{{ textValue('lunar_mansion') }}</strong></div><div><span>命卦</span><strong>{{ textValue('ming_gua') }}</strong></div></div>
        <div class="info-pair"><div><span>胎元</span><strong>{{ textValue('tai_yuan') }} {{ textValue('tai_yuan_nayin') }}</strong></div><div><span>空亡</span><strong>{{ voidSummary }}</strong></div></div>
        <div class="info-pair"><div><span>命宫</span><strong>{{ textValue('ming_gong') }} {{ textValue('ming_gong_nayin') }}</strong></div><div><span>胎息</span><strong>{{ textValue('tai_xi') }} {{ textValue('tai_xi_nayin') }}</strong></div></div>
        <div class="info-row"><span>身宫</span><strong>{{ textValue('shen_gong') }} {{ textValue('shen_gong_nayin') }}</strong></div>
      </section>

      <section id="basic-chart" class="pillar-panel card-surface" aria-label="四柱排盘">
        <div class="pillar-grid pillar-header-row">
          <span>日期</span><strong v-for="position in positionOrder" :key="position">{{ positionLabels[position] }}</strong>
        </div>
        <div class="pillar-grid"><span>主星</span><strong v-for="position in positionOrder" :key="position">{{ detail(position)?.major_star || overview.pillars.find((item) => item.position === position)?.ten_god || '—' }}</strong></div>
        <div class="pillar-grid gan-row"><span>天干</span><strong v-for="position in positionOrder" :key="position" :class="stemClass[detail(position)?.stem || overview.pillars.find((item) => item.position === position)?.stem || '']">{{ detail(position)?.stem || overview.pillars.find((item) => item.position === position)?.stem }}</strong></div>
        <div class="pillar-grid zhi-row"><span>地支</span><strong v-for="position in positionOrder" :key="position" :class="branchClass[detail(position)?.branch || overview.pillars.find((item) => item.position === position)?.branch || '']">{{ detail(position)?.branch || overview.pillars.find((item) => item.position === position)?.branch }}</strong></div>
        <div class="pillar-grid multi-row"><span>藏干</span><div v-for="position in positionOrder" :key="position"><span v-for="item in detail(position)?.hidden_stems || overview.pillars.find((p) => p.position === position)?.hidden_stems || []" :key="item.stem">{{ item.stem }}<small>{{ item.ten_god }}</small></span></div></div>
        <div class="pillar-grid multi-row"><span>副星</span><div v-for="position in positionOrder" :key="position"><span v-for="item in detail(position)?.secondary_stars || []" :key="item">{{ item }}</span><span v-if="!detail(position)?.secondary_stars?.length">—</span></div></div>
        <div class="pillar-grid"><span>星运</span><strong v-for="position in positionOrder" :key="position">{{ detail(position)?.growth_stage || overview.pillars.find((item) => item.position === position)?.growth_stage || '—' }}</strong></div>
        <div class="pillar-grid"><span>自坐</span><strong v-for="position in positionOrder" :key="position">{{ detail(position)?.self_seat || '—' }}</strong></div>
        <div class="pillar-grid"><span>空亡</span><strong v-for="position in positionOrder" :key="position">{{ detail(position)?.void || '—' }}</strong></div>
        <div class="pillar-grid"><span>纳音</span><strong v-for="position in positionOrder" :key="position">{{ detail(position)?.nayin || overview.pillars.find((item) => item.position === position)?.nayin || '—' }}</strong></div>
        <div class="pillar-grid multi-row shensha-row"><span>神煞</span><div v-for="position in positionOrder" :key="position"><span v-for="item in detail(position)?.shensha || []" :key="item">{{ item }}</span><span v-if="!detail(position)?.shensha?.length">—</span></div></div>
      </section>

      <section id="detail-chart" class="analysis-facts-grid">
        <article class="card-surface five-element-panel">
          <header><h2>五行统计</h2><small>明见 + 藏干</small></header>
          <div v-for="item in fiveElements" :key="item.element" class="element-row">
            <span>{{ item.element }}</span><div><i :style="{ width: `${Math.min(100, ((item.total ?? item.explicit + item.hidden) / 8) * 100)}%` }"></i></div>
            <strong>{{ item.total ?? item.explicit + item.hidden }}</strong>
          </div>
        </article>
        <article class="card-surface relation-panel">
          <header><h2>干支关系</h2><small>由规则引擎计算</small></header>
          <p v-if="!overview.relationships.length">未检测到已配置规则中的显著关系。</p>
          <div v-for="relation in overview.relationships" :key="`${relation.rule_id}-${relation.participants.join('')}`" class="relation-chip">
            <strong>{{ relation.label }}</strong><span>{{ relation.participants.join(' · ') }}</span>
          </div>
        </article>
      </section>

      <div v-if="overview.warnings.length" class="warning-panel card-surface">
        <strong>排盘提示</strong><p v-for="item in overview.warnings" :key="item.message">{{ item.message }}</p>
      </div>

      <div class="chart-action-grid">
        <button class="full-primary-button" type="button" :disabled="analysisStarting" @click="startAnalysis">
          {{ analysisStarting ? '正在创建分析…' : '生成完整命理分析' }}
        </button>
        <RouterLink class="secondary-action" :to="{ name: 'temporal', params: { chartId } }">查看大运流年</RouterLink>
        <RouterLink class="secondary-action gold-action" :to="{ name: 'chart-chat', params: { chartId } }">继续询问年 / 月 / 日运势</RouterLink>
      </div>
      <p v-if="analysisError" class="inline-error" role="alert">{{ analysisError }}</p>
    </template>
  </section>
</template>
