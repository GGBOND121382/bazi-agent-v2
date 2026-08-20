<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import type {
  ChartOverviewViewDTO,
  ChartResultDTO,
  DeterministicPillarDetail,
  TemporalContextViewDTO,
  TemporalDayunDTO,
  TemporalMonthDTO,
  TemporalPillarDetailDTO,
  TemporalRelationDTO,
  TemporalShenshaDTO,
} from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const now = new Date()
const year = ref(now.getFullYear())
const selectedDate = ref(`${year.value}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`)
const selectedMonth = ref<number | null>(null)
const selectedDayunIndex = ref<number | null>(null)

watch(year, (value) => {
  const current = new Date(selectedDate.value)
  const month = Number.isNaN(current.getTime()) ? 6 : current.getMonth() + 1
  const day = Number.isNaN(current.getTime()) ? 15 : current.getDate()
  selectedDate.value = `${value}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  selectedMonth.value = null
})

const temporalQuery = useQuery<TemporalContextViewDTO>({
  queryKey: computed(() => ['temporal', props.chartId, year.value, selectedDate.value]),
  queryFn: () => client.getTemporalContext(props.chartId, year.value, selectedDate.value),
})
const chartQuery = useQuery<{ chart: ChartResultDTO; overview: ChartOverviewViewDTO }>({
  queryKey: computed(() => ['temporal-chart', props.chartId]),
  queryFn: async () => {
    const [chart, overview] = await Promise.all([
      client.getChart(props.chartId),
      client.getChartOverviewView(props.chartId),
    ])
    return { chart, overview }
  },
  staleTime: 60_000,
})

const data = temporalQuery.data
const chart = computed(() => chartQuery.data.value?.chart)
const overview = computed(() => chartQuery.data.value?.overview)
const isLoading = computed(() => temporalQuery.isLoading.value || chartQuery.isLoading.value)
const isError = computed(() => temporalQuery.isError.value || chartQuery.isError.value)
const errorMessage = computed(() => temporalQuery.error.value?.message ?? chartQuery.error.value?.message ?? '未知错误')
const activeDayun = computed(() => data.value?.active_dayun ?? null)
const displayLiunianYear = computed(() => data.value?.year.lichun_year ?? data.value?.year.year ?? year.value)
const selectedDayun = computed<TemporalDayunDTO | null>(() => {
  if (!data.value) return null
  return data.value.dayuns.find((item) => item.index === selectedDayunIndex.value)
    ?? data.value.active_dayun
    ?? data.value.dayuns[0]
    ?? null
})
const selected = computed<TemporalMonthDTO | null>(() => {
  if (!data.value) return null
  return data.value.months.find((item) => item.index === selectedMonth.value)
    ?? data.value.months.find((item) => selectedDate.value >= item.start_datetime.slice(0, 10)
      && selectedDate.value < item.end_datetime.slice(0, 10))
    ?? null
})
const qiyunText = computed(() => {
  const q = data.value?.qiyun
  if (!q) return '—'
  return `${q.start_years ?? 0}年${q.start_months ?? 0}月${q.start_days ?? 0}天${q.start_hours ?? 0}小时`
})
const natalDetails = computed<Record<string, DeterministicPillarDetail>>(() => {
  const items = chart.value?.calendar.deterministic_details?.pillars ?? []
  return Object.fromEntries(items.map((item) => [item.position, item]))
})

const elementOrder = ['木', '火', '土', '金', '水']
const positionOrder = ['year', 'month', 'day', 'hour'] as const
const positionLabels: Record<string, string> = {
  year: '年柱', month: '月柱', day: '日柱', hour: '时柱',
  natal_year: '原局年柱', natal_month: '原局月柱', natal_day: '原局日柱', natal_hour: '原局时柱',
  dayun: '大运', liunian: '流年', liuyue: '流月', liuri: '流日',
}
const stemClass: Record<string, string> = {
  甲: 'wood', 乙: 'wood', 丙: 'fire', 丁: 'fire', 戊: 'earth', 己: 'earth',
  庚: 'metal', 辛: 'metal', 壬: 'water', 癸: 'water',
}
const branchClass: Record<string, string> = {
  寅: 'wood', 卯: 'wood', 巳: 'fire', 午: 'fire', 辰: 'earth', 戌: 'earth',
  丑: 'earth', 未: 'earth', 申: 'metal', 酉: 'metal', 子: 'water', 亥: 'water',
}

type HiddenStem = { stem: string; ten_god?: string }
type ProfessionalColumn = {
  key: string
  label: string
  stem: string
  branch: string
  mainStar: string
  hiddenStems: HiddenStem[]
  secondaryStars: string[]
  growthStage: string
  selfSeat: string
  xunkong: string
  nayin: string
  shensha: string[]
}

function names(items?: TemporalShenshaDTO[]): string {
  return items?.map((item) => item.name).join('　') || '—'
}

function dateTimeLabel(value?: string): string {
  if (!value) return '—'
  return value.replace('T', ' ').replace(/\+.*$/, '')
}

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))]
}

function temporalColumn(key: string, label: string, item: TemporalPillarDetailDTO | null): ProfessionalColumn | null {
  if (!item) return null
  return {
    key,
    label,
    stem: item.stem,
    branch: item.branch,
    mainStar: item.stem_ten_god,
    hiddenStems: item.hidden_stems,
    secondaryStars: unique(item.hidden_stems.map((hidden) => hidden.ten_god)),
    growthStage: item.growth_stage,
    selfSeat: item.self_seat,
    xunkong: item.xunkong,
    nayin: item.nayin,
    shensha: item.shensha.map((entry) => entry.name),
  }
}

function natalColumn(position: typeof positionOrder[number]): ProfessionalColumn | null {
  const pillar = chart.value?.pillars.find((item) => item.position === position)
  if (!pillar) return null
  const detail = natalDetails.value[position]
  const hiddenStems = detail?.hidden_stems ?? pillar.hidden_stems ?? []
  return {
    key: position,
    label: positionLabels[position],
    stem: pillar.stem,
    branch: pillar.branch,
    mainStar: detail?.major_star ?? pillar.ten_god_of_stem ?? (position === 'day' ? '日主' : '—'),
    hiddenStems,
    secondaryStars: detail?.secondary_stars ?? unique(hiddenStems.map((item) => item.ten_god ?? '')),
    growthStage: detail?.growth_stage ?? '—',
    selfSeat: detail?.self_seat ?? '—',
    xunkong: detail?.void ?? '—',
    nayin: detail?.nayin ?? pillar.nayin ?? '—',
    shensha: detail?.shensha ?? [],
  }
}

const professionalColumns = computed<ProfessionalColumn[]>(() => {
  const columns = [
    temporalColumn('liunian', '流年', data.value?.year ?? null),
    temporalColumn('dayun', '大运', activeDayun.value),
    ...positionOrder.map((position) => natalColumn(position)),
  ]
  return columns.filter((item): item is ProfessionalColumn => item !== null)
})

function relationText(item: TemporalPillarDetailDTO): string {
  return item.relations.map((relation) => {
    const natalPositions = relation.natal_positions?.length
      ? relation.natal_positions.map((position) => positionLabels[position] ?? position).join('、')
      : relation.natal_position ? positionLabels[relation.natal_position] ?? relation.natal_position : '原局'
    return `${natalPositions}${relation.label}${relation.participants.join('')}`
  }).join('｜') || '—'
}

function participantLabel(relation: TemporalRelationDTO): string {
  if (relation.participant_positions?.length) {
    return relation.participant_positions
      .map((item) => `${positionLabels[item.position] ?? item.position} ${item.ganzhi}`)
      .join(' ↔ ')
  }
  return relation.participants.join(' ↔ ')
}

function attentionLabel(relation: TemporalRelationDTO): string {
  if (relation.attention === 'high_attention') return '重点结构'
  if (relation.attention === 'attention') return '需关注'
  return '结构关系'
}

function relationTextBy(item: TemporalPillarDetailDTO, kind: 'stem' | 'branch'): string {
  const matches = item.relations.filter((relation) => kind === 'stem'
    ? relation.type.startsWith('stem_')
    : !relation.type.startsWith('stem_'))
  return matches.map((relation) => {
    const natal = relation.natal_position ? positionLabels[relation.natal_position] ?? relation.natal_position : '原局'
    return `${natal}${relation.label}${relation.participants.join('')}`
  }).join('｜') || '—'
}

const natalRelationText = computed(() => overview.value?.relationships.map((relation) => `${relation.label} ${relation.participants.join('·')}`).join('｜') || '—')
</script>

<template>
  <section class="temporal-page" aria-labelledby="temporal-title">
    <nav class="chart-tabs" aria-label="命盘内容导航">
      <RouterLink :to="{ name: 'chart-overview', params: { chartId }, hash: '#basic-info' }">基本信息</RouterLink>
      <RouterLink :to="{ name: 'chart-overview', params: { chartId }, hash: '#basic-chart' }">基本排盘</RouterLink>
      <a class="active" href="#professional-table">专业细盘</a>
      <RouterLink :to="{ name: 'chart-chat', params: { chartId } }">断事问答</RouterLink>
    </nav>

    <header class="page-heading compact-heading">
      <p class="eyebrow">大运 → 流年 → 流月 → 流日</p>
      <h1 id="temporal-title">专业细盘</h1>
      <p>岁运与原局使用同一日主，逐层计算十神、藏干、星运、自坐、纳音、空亡、神煞及干支作用。</p>
    </header>

    <div class="year-picker card-surface">
      <button type="button" aria-label="上一年" @click="year--">‹</button>
      <label><span>查看年份</span><input v-model.number="year" type="number" min="1900" max="2200" /></label>
      <button type="button" aria-label="下一年" @click="year++">›</button>
    </div>

    <p v-if="isLoading" class="state-card">正在计算精确节气流运…</p>
    <p v-else-if="isError" class="state-card error-card" role="alert">{{ errorMessage }}</p>
    <template v-else-if="data && chart">
      <nav class="fortune-breadcrumb" aria-label="时间层级">
        <span v-for="(item, index) in data.breadcrumb" :key="item.level">
          <i v-if="index">›</i><small>{{ item.label }}</small><strong>{{ item.ganzhi ?? '—' }}</strong>
        </span>
      </nav>

      <section class="qiyun-card card-surface">
        <div><span>起运</span><strong>出生后 {{ qiyunText }}</strong><small>{{ data.qiyun?.direction === 'forward' ? '顺运' : '逆运' }} · {{ dateTimeLabel(data.qiyun?.start_datetime) }} 交运</small></div>
        <div v-if="activeDayun"><span>当前大运</span><strong>{{ activeDayun.ganzhi }} · {{ activeDayun.stem_ten_god }}</strong><small>{{ activeDayun.start_year }}—{{ activeDayun.end_year }}（{{ activeDayun.start_age }}—{{ activeDayun.end_age }}岁）</small></div>
        <div><span>当前流年</span><strong>{{ data.year.ganzhi }} · {{ data.year.stem_ten_god }}</strong><small>{{ data.year.age }}岁 · 小运 {{ data.year.xiaoyun ?? '—' }}</small></div>
      </section>


      <section class="card-surface temporal-interaction-card" aria-label="岁运交叉关系">
        <header>
          <div><p class="eyebrow">确定性岁运交互</p><h2>大运、流年、流月、流日交叉作用</h2></div>
          <small>重点 {{ data.interaction_summary.high_attention_count ?? 0 }} · 关注 {{ data.interaction_summary.attention_count ?? 0 }}</small>
        </header>
        <p class="interaction-note">{{ data.interaction_summary.note ?? '结构触发不直接等于吉凶结论。' }}</p>
        <div v-if="data.interactions.length" class="interaction-list">
          <article v-for="(relation, index) in data.interactions" :key="`${relation.rule_id}-${index}`" :class="`attention-${relation.attention ?? 'contextual'}`">
            <div><strong>{{ relation.label }}</strong><span>{{ attentionLabel(relation) }}</span></div>
            <p>{{ participantLabel(relation) }}</p>
            <small v-if="relation.basis?.length">依据：{{ relation.basis.join(' + ') }}</small>
          </article>
        </div>
        <p v-else class="state-inline">当前所选层级未检测到配置规则中的交叉关系。</p>
      </section>

      <section id="professional-table" class="card-surface professional-table-card" aria-label="流年大运与四柱专业排盘">
        <header><div><p class="eyebrow">同表对照</p><h2>{{ displayLiunianYear }} 流年、大运与原局四柱</h2></div><small>横向滚动可查看全部六柱</small></header>
        <div class="professional-scroll" tabindex="0" aria-label="流年大运与原局四柱横向表格">
          <div class="professional-grid professional-header-row">
            <span>日期</span><strong v-for="column in professionalColumns" :key="column.key">{{ column.label }}</strong>
          </div>
          <div class="professional-grid"><span>主星</span><strong v-for="column in professionalColumns" :key="column.key">{{ column.mainStar }}</strong></div>
          <div class="professional-grid gan-row"><span>天干</span><strong v-for="column in professionalColumns" :key="column.key" :class="stemClass[column.stem]">{{ column.stem }}</strong></div>
          <div class="professional-grid zhi-row"><span>地支</span><strong v-for="column in professionalColumns" :key="column.key" :class="branchClass[column.branch]">{{ column.branch }}</strong></div>
          <div class="professional-grid multi-row"><span>藏干</span><div v-for="column in professionalColumns" :key="column.key"><span v-for="hidden in column.hiddenStems" :key="`${hidden.stem}-${hidden.ten_god}`">{{ hidden.stem }}<small>{{ hidden.ten_god }}</small></span></div></div>
          <div class="professional-grid multi-row"><span>副星</span><div v-for="column in professionalColumns" :key="column.key"><span v-for="star in column.secondaryStars" :key="star">{{ star }}</span><span v-if="!column.secondaryStars.length">—</span></div></div>
          <div class="professional-grid"><span>星运</span><strong v-for="column in professionalColumns" :key="column.key">{{ column.growthStage }}</strong></div>
          <div class="professional-grid"><span>自坐</span><strong v-for="column in professionalColumns" :key="column.key">{{ column.selfSeat }}</strong></div>
          <div class="professional-grid"><span>空亡</span><strong v-for="column in professionalColumns" :key="column.key">{{ column.xunkong }}</strong></div>
          <div class="professional-grid"><span>纳音</span><strong v-for="column in professionalColumns" :key="column.key">{{ column.nayin }}</strong></div>
          <div class="professional-grid multi-row shensha-row"><span>神煞</span><div v-for="column in professionalColumns" :key="column.key"><span v-for="star in column.shensha" :key="star">{{ star }}</span><span v-if="!column.shensha.length">—</span></div></div>
        </div>
      </section>

      <section class="card-surface relation-map-card">
        <header><div><p class="eyebrow">智能干支图示</p><h2>岁运与原局作用</h2></div><small>不把见合直接判为合化</small></header>
        <dl>
          <div><dt>流年天干</dt><dd>{{ relationTextBy(data.year, 'stem') }}</dd></div>
          <div><dt>流年地支</dt><dd>{{ relationTextBy(data.year, 'branch') }}</dd></div>
          <div v-if="activeDayun"><dt>大运天干</dt><dd>{{ relationTextBy(activeDayun, 'stem') }}</dd></div>
          <div v-if="activeDayun"><dt>大运地支</dt><dd>{{ relationTextBy(activeDayun, 'branch') }}</dd></div>
          <div><dt>原局关系</dt><dd>{{ natalRelationText }}</dd></div>
        </dl>
      </section>

      <section class="card-surface timeline-section">
        <header><div><p class="eyebrow">十年一运</p><h2>大运十神与神煞</h2></div></header>
        <div class="horizontal-fortunes">
          <button v-for="item in data.dayuns" :key="item.index" type="button" :class="{ active: item.index === selectedDayun?.index }" @click="selectedDayunIndex = item.index">
            <small>{{ item.start_year }}</small><strong>{{ item.ganzhi }}</strong><span>{{ item.stem_ten_god }} / {{ item.branch_ten_god }}</span>
            <p>{{ names(item.shensha) }}</p>
          </button>
        </div>
      </section>

      <section v-if="selectedDayun" class="selected-month-panel card-surface temporal-detail-card">
        <header><div><span>已选大运</span><strong>{{ selectedDayun.ganzhi }} · {{ selectedDayun.stem_ten_god }}</strong><small>{{ selectedDayun.start_year }}—{{ selectedDayun.end_year }} · {{ selectedDayun.start_age }}—{{ selectedDayun.end_age }}岁</small></div></header>
        <dl><div><dt>藏干十神</dt><dd>{{ selectedDayun.hidden_stems.map((item) => `${item.stem}${item.ten_god}`).join('　') }}</dd></div><div><dt>星运 / 自坐</dt><dd>{{ selectedDayun.growth_stage }} / {{ selectedDayun.self_seat }}</dd></div><div><dt>纳音 / 空亡</dt><dd>{{ selectedDayun.nayin }} / {{ selectedDayun.xunkong }}</dd></div><div><dt>大运神煞</dt><dd>{{ names(selectedDayun.shensha) }}</dd></div><div><dt>原局作用</dt><dd>{{ relationText(selectedDayun) }}</dd></div></dl>
      </section>

      <section class="fortune-summary-grid">
        <article class="dark-fortune-card">
          <span>{{ displayLiunianYear }} 流年 · {{ data.year.age }}岁</span>
          <strong>{{ data.year.ganzhi }}</strong>
          <small>{{ data.year.stem_ten_god }} / {{ data.year.branch_ten_god }} · 小运 {{ data.year.xiaoyun ?? '—' }}</small>
          <p>{{ names(data.year.shensha) }}</p>
        </article>
        <article class="gold-fortune-card">
          <span>流年完整字段</span><strong>{{ data.year.growth_stage }} / {{ data.year.self_seat }}</strong><small>{{ data.year.nayin }} · 空亡 {{ data.year.xunkong }}</small>
          <p>{{ data.year.hidden_stems.map((item) => `${item.stem}${item.ten_god}`).join('　') }}</p>
        </article>
      </section>

      <section class="month-calendar card-surface">
        <header><div><p class="eyebrow">精确节气月</p><h2>流月十神与神煞</h2></div><RouterLink :to="{ name: 'chart-chat', params: { chartId }, query: { scope: 'year', date: `${year}-06-15` } }">问全年运势</RouterLink></header>
        <div class="month-grid-new enriched-months">
          <button v-for="month in data.months" :key="month.fact_id" type="button" :class="{ active: selected?.index === month.index }" @click="selectedMonth = month.index">
            <span>{{ month.label }} · {{ month.jie_name }}</span><strong>{{ month.ganzhi }}</strong><small>{{ month.stem_ten_god }} / {{ month.branch_ten_god }}</small><em>{{ names(month.shensha) }}</em>
          </button>
        </div>
      </section>

      <section v-if="selected" class="selected-month-panel card-surface temporal-detail-card">
        <header><div><span>已选流月</span><strong>{{ selected.ganzhi }} · {{ selected.stem_ten_god }}</strong><small>{{ dateTimeLabel(selected.start_datetime) }} 至 {{ dateTimeLabel(selected.end_datetime) }}</small></div>
          <RouterLink class="secondary-action gold-action" :to="{ name: 'chart-chat', params: { chartId }, query: { scope: 'month', date: selected.start_datetime.slice(0, 10) } }">分析本月事业、财运和感情</RouterLink>
        </header>
        <dl><div><dt>藏干十神</dt><dd>{{ selected.hidden_stems.map((item) => `${item.stem}${item.ten_god}`).join('　') }}</dd></div><div><dt>星运 / 自坐</dt><dd>{{ selected.growth_stage }} / {{ selected.self_seat }}</dd></div><div><dt>纳音 / 空亡</dt><dd>{{ selected.nayin }} / {{ selected.xunkong }}</dd></div><div><dt>流月神煞</dt><dd>{{ names(selected.shensha) }}</dd></div><div><dt>原局作用</dt><dd>{{ relationText(selected) }}</dd></div></dl>
      </section>

      <section class="card-surface day-picker-panel">
        <header><div><p class="eyebrow">逐日查询</p><h2>流日十神与神煞</h2></div><input v-model="selectedDate" type="date" aria-label="选择流日" :min="`${year}-01-01`" :max="`${year}-12-31`" /></header>
        <article v-if="data.selected_day" class="flow-day-card">
          <div><span>{{ data.selected_day.date }} · {{ data.selected_day.lunar_date }}</span><strong>{{ data.selected_day.ganzhi }}</strong><small>{{ data.selected_day.stem_ten_god }} / {{ data.selected_day.branch_ten_god }}</small></div>
          <dl><div><dt>藏干十神</dt><dd>{{ data.selected_day.hidden_stems.map((item) => `${item.stem}${item.ten_god}`).join('　') }}</dd></div><div><dt>星运 / 自坐</dt><dd>{{ data.selected_day.growth_stage }} / {{ data.selected_day.self_seat }}</dd></div><div><dt>纳音 / 空亡</dt><dd>{{ data.selected_day.nayin }} / {{ data.selected_day.xunkong }}</dd></div><div><dt>流日神煞</dt><dd>{{ names(data.selected_day.shensha) }}</dd></div><div><dt>原局作用</dt><dd>{{ relationText(data.selected_day) }}</dd></div></dl>
          <RouterLink class="secondary-action gold-action" :to="{ name: 'chart-chat', params: { chartId }, query: { scope: 'day', date: selectedDate } }">询问当天财运、事业与感情</RouterLink>
        </article>
      </section>

      <section class="shensha-groups">
        <article class="card-surface"><h2>四柱神煞</h2><p v-for="column in professionalColumns.slice(2)" :key="column.key"><strong>{{ column.stem }}{{ column.branch }}：</strong>{{ column.shensha.join('　') || '—' }}</p></article>
        <article class="card-surface"><h2>大运神煞</h2><p v-for="item in data.dayuns" :key="item.fact_id"><strong>{{ item.ganzhi }}：</strong>{{ names(item.shensha) }}</p></article>
        <article class="card-surface"><h2>流年神煞</h2><p><strong>{{ data.year.ganzhi }}：</strong>{{ names(data.year.shensha) }}</p></article>
      </section>

      <section class="card-surface seasonal-panel">
        <header><h2>月令五行旺相休囚死</h2><small>以原局月支为基础状态</small></header>
        <div><span v-for="element in elementOrder" :key="element"><strong>{{ element }}{{ data.seasonal_strength[element] ?? '—' }}</strong></span></div>
      </section>

      <RouterLink class="full-primary-button button-link" :to="{ name: 'chart-chat', params: { chartId } }">进入年 / 月 / 日运势问答</RouterLink>
    </template>
  </section>
</template>

<style scoped>

.temporal-interaction-card { padding: 18px; }
.temporal-interaction-card > header { display: flex; justify-content: space-between; gap: 14px; align-items: end; }
.interaction-note { color: var(--text-muted); line-height: 1.55; }
.interaction-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 10px; }
.interaction-list article { border: 1px solid var(--border-soft); border-radius: 14px; padding: 12px; display: grid; gap: 6px; }
.interaction-list article > div { display: flex; justify-content: space-between; gap: 8px; }
.interaction-list article span { font-size: .72rem; color: var(--text-muted); }
.interaction-list article p { margin: 0; line-height: 1.5; }
.interaction-list article small { color: var(--text-muted); }
.interaction-list .attention-high_attention { border-color: #b76845; background: color-mix(in srgb, #b76845 8%, var(--surface)); }
.interaction-list .attention-attention { border-color: var(--gold-deep); }
.state-inline { color: var(--text-muted); }
.qiyun-card { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; padding: 18px; }
.qiyun-card div { display: grid; gap: 5px; }
.qiyun-card span, .qiyun-card small { color: var(--text-muted); }
.timeline-section, .day-picker-panel, .seasonal-panel, .professional-table-card, .relation-map-card { padding: 18px; }
.professional-table-card > header, .relation-map-card > header { display: flex; justify-content: space-between; gap: 16px; align-items: end; margin-bottom: 12px; }
.professional-scroll { overflow-x: auto; border: 1px solid var(--border-soft); border-radius: 16px; }
.professional-grid { display: grid; grid-template-columns: 76px repeat(6, minmax(112px, 1fr)); min-width: 748px; }
.professional-grid > span, .professional-grid > strong, .professional-grid > div { min-height: 50px; padding: 10px 8px; border-right: 1px solid var(--border-soft); border-bottom: 1px solid var(--border-soft); text-align: center; display: grid; place-items: center; }
.professional-grid > span:first-child { color: var(--text-muted); background: var(--surface-soft); }
.professional-header-row strong { color: var(--text-muted); font-weight: 600; }
.professional-grid.gan-row strong, .professional-grid.zhi-row strong { font-size: 2rem; font-family: serif; }
.professional-grid.multi-row > div { align-content: center; gap: 4px; }
.professional-grid.multi-row > div span { display: block; line-height: 1.35; }
.professional-grid.multi-row small { display: block; font-size: .68rem; color: var(--text-muted); }
.professional-grid.shensha-row > div { min-height: 126px; color: var(--gold-deep); }
.horizontal-fortunes { display: flex; gap: 10px; overflow-x: auto; padding: 8px 0 4px; scroll-snap-type: x mandatory; }
.horizontal-fortunes button { min-width: 144px; padding: 12px; border: 1px solid var(--border-soft); border-radius: 14px; display: grid; gap: 4px; text-align: left; scroll-snap-align: start; background: var(--surface); color: inherit; }
.horizontal-fortunes button.active { border-color: var(--gold-deep); background: var(--gold-soft); }
.horizontal-fortunes p, .dark-fortune-card p, .gold-fortune-card p { margin: 4px 0 0; font-size: .75rem; line-height: 1.45; color: var(--text-muted); }
.enriched-months button { min-height: 126px; align-content: start; }
.enriched-months em { font-style: normal; font-size: .68rem; line-height: 1.35; color: var(--gold-deep); }
.temporal-detail-card { display: grid; gap: 14px; }
.temporal-detail-card header, .day-picker-panel header, .seasonal-panel header { display: flex; justify-content: space-between; gap: 14px; align-items: center; }
dl { display: grid; gap: 0; margin: 0; }
dl div { display: grid; grid-template-columns: 92px 1fr; gap: 12px; padding: 9px 0; border-top: 1px solid var(--border-soft); }
dt { color: var(--text-muted); } dd { margin: 0; line-height: 1.55; }
.flow-day-card { display: grid; gap: 14px; padding-top: 14px; }
.flow-day-card > div { display: grid; gap: 4px; }
.flow-day-card > div strong { font-size: 2rem; color: var(--gold-deep); }
.shensha-groups { display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.shensha-groups article { padding: 18px; }
.shensha-groups h2 { color: var(--gold-deep); }
.shensha-groups p { margin: 8px 0; line-height: 1.6; }
.seasonal-panel > div { display: grid; grid-template-columns: repeat(5, 1fr); margin-top: 14px; }
.seasonal-panel span { text-align: center; padding: 8px 2px; border-right: 1px solid var(--border-soft); }
.wood { color: #1fa83d; } .fire { color: #e32626; } .earth { color: #a47700; } .metal { color: #747474; } .water { color: #1474d4; }
@media (max-width: 760px) { .qiyun-card, .shensha-groups { grid-template-columns: 1fr; } .professional-table-card > header, .relation-map-card > header, .temporal-detail-card header, .day-picker-panel header { align-items: flex-start; flex-direction: column; } }
</style>
