<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import type { TemporalContextViewDTO } from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const year = ref(new Date().getFullYear())
const selectedMonth = ref<number | null>(null)
const { data, isLoading, isError, error } = useQuery<TemporalContextViewDTO>({
  queryKey: computed(() => ['temporal', props.chartId, year.value]),
  queryFn: () => client.getTemporalContext(props.chartId, year.value),
})

const activeDayunGanzhi = computed(() => String(data.value?.active_dayun?.ganzhi ?? '未进入大运'))
const selected = computed(() => data.value?.months.find((item) => item.index === selectedMonth.value) ?? null)
</script>

<template>
  <section class="temporal-page" aria-labelledby="temporal-title">
    <header class="page-heading compact-heading">
      <p class="eyebrow">大运 → 流年 → 流月</p>
      <h1 id="temporal-title">流运排盘</h1>
      <p>先查看确定性的时间干支，再进入智能问答分析事业、财运、感情与行动时机。</p>
    </header>

    <div class="year-picker card-surface">
      <button type="button" aria-label="上一年" @click="year--">‹</button>
      <label><span>查看年份</span><input v-model.number="year" type="number" min="1900" max="2200" /></label>
      <button type="button" aria-label="下一年" @click="year++">›</button>
    </div>

    <p v-if="isLoading" class="state-card">正在计算流运上下文…</p>
    <p v-else-if="isError" class="state-card error-card" role="alert">{{ error?.message }}</p>
    <template v-else-if="data">
      <nav class="fortune-breadcrumb" aria-label="时间层级">
        <span v-for="(item, index) in data.breadcrumb" :key="item.level">
          <i v-if="index">›</i><small>{{ item.label }}</small><strong>{{ item.ganzhi ?? '—' }}</strong>
        </span>
      </nav>

      <div class="fortune-summary-grid">
        <article class="dark-fortune-card"><span>当前大运</span><strong>{{ activeDayunGanzhi }}</strong><small>结合原局查看十年阶段</small></article>
        <article class="gold-fortune-card"><span>{{ year }} 流年</span><strong>{{ data.year.ganzhi }}</strong><small>{{ data.year.stem }}天干 · {{ data.year.branch }}地支</small></article>
      </div>

      <section class="month-calendar card-surface">
        <header><div><p class="eyebrow">节气月</p><h2>流月干支</h2></div><RouterLink :to="{ name: 'chart-chat', params: { chartId }, query: { scope: 'year', date: `${year}-01-01` } }">问全年运势</RouterLink></header>
        <div class="month-grid-new">
          <button v-for="month in data.months" :key="month.fact_id" type="button" :class="{ active: selectedMonth === month.index }" @click="selectedMonth = month.index">
            <span>{{ month.index }}月</span><strong>{{ month.ganzhi }}</strong><small>{{ month.label }}</small>
          </button>
        </div>
      </section>

      <section v-if="selected" class="selected-month-panel card-surface">
        <div><span>已选流月</span><strong>{{ selected.ganzhi }}</strong><small>{{ selected.label }}</small></div>
        <RouterLink class="secondary-action gold-action" :to="{ name: 'chart-chat', params: { chartId }, query: { scope: 'month', date: `${year}-${String(selected.index).padStart(2, '0')}-15` } }">分析本月事业、财运和感情</RouterLink>
      </section>

      <RouterLink class="full-primary-button button-link" :to="{ name: 'chart-chat', params: { chartId } }">进入年 / 月 / 日运势问答</RouterLink>
    </template>
  </section>
</template>
