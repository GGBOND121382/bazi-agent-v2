<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import type { TemporalContextViewDTO } from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const year = ref(new Date().getFullYear())
const { data, isLoading, isError, error } = useQuery<TemporalContextViewDTO>({
  queryKey: computed(() => ['temporal', props.chartId, year.value]),
  queryFn: () => client.getTemporalContext(props.chartId, year.value),
})
</script>

<template>
  <section aria-labelledby="temporal-title">
    <p class="eyebrow">大运 → 流年 → 流月</p>
    <h1 id="temporal-title">流运上下文</h1>
    <label>查看年份 <input v-model.number="year" type="number" min="1900" max="2200" /></label>
    <p v-if="isLoading" data-state="loading">正在加载后端计算事实…</p>
    <p v-else-if="isError" data-state="error" role="alert">{{ error?.message }}</p>
    <template v-else-if="data">
      <nav class="breadcrumbs" aria-label="时间层级">
        <span v-for="(item, index) in data.breadcrumb" :key="item.level">
          <span v-if="index" aria-hidden="true">→</span> {{ item.label }} {{ item.ganzhi ?? '—' }}
        </span>
      </nav>
      <div class="temporal-summary">
        <article><span>当前流年</span><strong>{{ data.year.ganzhi }}</strong><code>{{ data.year.fact_id }}</code></article>
        <article><span>所在大运</span><strong>{{ data.active_dayun?.ganzhi ?? '未进入大运' }}</strong></article>
      </div>
      <h2>节气月</h2>
      <div class="month-grid">
        <article v-for="month in data.months" :key="month.fact_id">
          <span>{{ month.label }}</span><strong>{{ month.ganzhi }}</strong><code>{{ month.rule_id }}</code>
        </article>
      </div>
    </template>
  </section>
</template>
