<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import type {
  TemporalContextViewDTO,
  TemporalMonthDTO,
  TemporalPillarDetailDTO,
  TemporalShenshaDTO,
} from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const now = new Date()
const year = ref(now.getFullYear())
const selectedDate = ref(`${year.value}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`)
const selectedMonth = ref<number | null>(null)

watch(year, (value) => {
  const current = new Date(selectedDate.value)
  const month = Number.isNaN(current.getTime()) ? 6 : current.getMonth() + 1
  const day = Number.isNaN(current.getTime()) ? 15 : current.getDate()
  selectedDate.value = `${value}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
})

const { data, isLoading, isError, error } = useQuery<TemporalContextViewDTO>({
  queryKey: computed(() => ['temporal', props.chartId, year.value, selectedDate.value]),
  queryFn: () => client.getTemporalContext(props.chartId, year.value, selectedDate.value),
})

const activeDayun = computed(() => data.value?.active_dayun ?? null)
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

const elementOrder = ['木', '火', '土', '金', '水']
const positionLabels: Record<string, string> = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' }

function names(items?: TemporalShenshaDTO[]): string {
  return items?.map((item) => item.name).join('　') || '—'
}

function dateTimeLabel(value?: string): string {
  if (!value) return '—'
  return value.replace('T', ' ').replace(/\+.*$/, '')
}

function relationText(item: TemporalPillarDetailDTO): string {
  return item.relations.map((relation) => {
    const natal = relation.natal_position ? positionLabels[relation.natal_position] ?? relation.natal_position : '原局'
    return `${natal}${relation.label}${relation.participants.join('')}`
  }).join('｜') || '—'
}
</script>

<template>
  <section class="temporal-page" aria-labelledby="temporal-title">
    <header class="page-heading compact-heading">
      <p class="eyebrow">大运 → 流年 → 流月 → 流日</p>
      <h1 id="temporal-title">流运排盘</h1>
      <p>每一层均按原局日主计算十神、藏干、长生、纳音、空亡、神煞与干支作用。</p>
    </header>

    <div class="year-picker card-surface">
      <button type="button" aria-label="上一年" @click="year--">‹</button>
      <label><span>查看年份</span><input v-model.number="year" type="number" min="1900" max="2200" /></label>
      <button type="button" aria-label="下一年" @click="year++">›</button>
    </div>

    <p v-if="isLoading" class="state-card">正在计算精确节气流运…</p>
    <p v-else-if="isError" class="state-card error-card" role="alert">{{ error?.message }}</p>
    <template v-else-if="data">
      <nav class="fortune-breadcrumb" aria-label="时间层级">
        <span v-for="(item, index) in data.breadcrumb" :key="item.level">
          <i v-if="index">›</i><small>{{ item.label }}</small><strong>{{ item.ganzhi ?? '—' }}</strong>
        </span>
      </nav>

      <section class="qiyun-card card-surface">
        <div><span>起运</span><strong>出生后 {{ qiyunText }}</strong><small>{{ data.qiyun?.direction === 'forward' ? '顺运' : '逆运' }} · {{ dateTimeLabel(data.qiyun?.start_datetime) }} 交运</small></div>
        <div v-if="activeDayun"><span>当前大运</span><strong>{{ activeDayun.ganzhi }} · {{ activeDayun.stem_ten_god }}</strong><small>{{ activeDayun.start_year }}—{{ activeDayun.end_year }}（{{ activeDayun.start_age }}—{{ activeDayun.end_age }}岁）</small></div>
      </section>

      <section class="card-surface timeline-section">
        <header><div><p class="eyebrow">十年一运</p><h2>大运十神与神煞</h2></div></header>
        <div class="horizontal-fortunes">
          <article v-for="item in data.dayuns" :key="item.index" :class="{ active: item.index === activeDayun?.index }">
            <small>{{ item.start_year }}</small><strong>{{ item.ganzhi }}</strong><span>{{ item.stem_ten_god }} / {{ item.branch_ten_god }}</span>
            <p>{{ names(item.shensha) }}</p>
          </article>
        </div>
      </section>

      <section class="fortune-summary-grid">
        <article class="dark-fortune-card">
          <span>{{ year }} 流年 · {{ data.year.age }}岁</span>
          <strong>{{ data.year.ganzhi }}</strong>
          <small>{{ data.year.stem_ten_god }} / {{ data.year.branch_ten_god }} · 小运 {{ data.year.xiaoyun ?? '—' }}</small>
          <p>{{ names(data.year.shensha) }}</p>
        </article>
        <article class="gold-fortune-card">
          <span>流年作用</span><strong>{{ relationText(data.year) }}</strong><small>{{ data.year.nayin }} · {{ data.year.growth_stage }} · 空亡 {{ data.year.xunkong }}</small>
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
        <dl><div><dt>藏干十神</dt><dd>{{ selected.hidden_stems.map((item) => `${item.stem}${item.ten_god}`).join('　') }}</dd></div><div><dt>星运 / 纳音</dt><dd>{{ selected.growth_stage }} · {{ selected.nayin }} · 空亡 {{ selected.xunkong }}</dd></div><div><dt>流月神煞</dt><dd>{{ names(selected.shensha) }}</dd></div><div><dt>原局作用</dt><dd>{{ relationText(selected) }}</dd></div></dl>
      </section>

      <section class="card-surface day-picker-panel">
        <header><div><p class="eyebrow">逐日查询</p><h2>流日十神与神煞</h2></div><input v-model="selectedDate" type="date" :min="`${year}-01-01`" :max="`${year}-12-31`" /></header>
        <article v-if="data.selected_day" class="flow-day-card">
          <div><span>{{ data.selected_day.date }} · {{ data.selected_day.lunar_date }}</span><strong>{{ data.selected_day.ganzhi }}</strong><small>{{ data.selected_day.stem_ten_god }} / {{ data.selected_day.branch_ten_god }}</small></div>
          <dl><div><dt>藏干十神</dt><dd>{{ data.selected_day.hidden_stems.map((item) => `${item.stem}${item.ten_god}`).join('　') }}</dd></div><div><dt>星运 / 自坐</dt><dd>{{ data.selected_day.growth_stage }} / {{ data.selected_day.self_seat }}</dd></div><div><dt>纳音 / 空亡</dt><dd>{{ data.selected_day.nayin }} / {{ data.selected_day.xunkong }}</dd></div><div><dt>流日神煞</dt><dd>{{ names(data.selected_day.shensha) }}</dd></div><div><dt>原局作用</dt><dd>{{ relationText(data.selected_day) }}</dd></div></dl>
          <RouterLink class="secondary-action gold-action" :to="{ name: 'chart-chat', params: { chartId }, query: { scope: 'day', date: selectedDate } }">询问当天财运、事业与感情</RouterLink>
        </article>
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
.qiyun-card { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; padding: 18px; }
.qiyun-card div { display: grid; gap: 5px; }
.qiyun-card span, .qiyun-card small { color: var(--text-muted); }
.timeline-section, .day-picker-panel, .seasonal-panel { padding: 18px; }
.horizontal-fortunes { display: flex; gap: 10px; overflow-x: auto; padding: 8px 0 4px; scroll-snap-type: x mandatory; }
.horizontal-fortunes article { min-width: 138px; padding: 12px; border: 1px solid var(--border-soft); border-radius: 14px; display: grid; gap: 4px; scroll-snap-align: start; }
.horizontal-fortunes article.active { border-color: var(--gold-deep); background: var(--gold-soft); }
.horizontal-fortunes p, .dark-fortune-card p { margin: 4px 0 0; font-size: .75rem; line-height: 1.45; color: var(--text-muted); }
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
.seasonal-panel > div { display: grid; grid-template-columns: repeat(5, 1fr); margin-top: 14px; }
.seasonal-panel span { text-align: center; padding: 8px 2px; border-right: 1px solid var(--border-soft); }
@media (max-width: 640px) { .qiyun-card { grid-template-columns: 1fr; } .temporal-detail-card header, .day-picker-panel header { align-items: flex-start; flex-direction: column; } }
</style>
