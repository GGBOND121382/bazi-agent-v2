<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import EvidenceDrawer from '@/components/EvidenceDrawer.vue'
import { useBaziClient } from '@/api'
import type { ReportBlockDTO, ReportViewDTO } from '@/api/schema'

const props = withDefaults(defineProps<{ reportId: string; printMode?: boolean }>(), { printMode: false })
const client = useBaziClient()
const professional = ref(false)
const drawerOpen = ref(false)
const selected = ref<ReportBlockDTO | null>(null)
const shareInfo = ref<{ share_id: string; share_token: string; expires_at: string } | null>(null)
const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'
const { data, isLoading, isError, error } = useQuery<ReportViewDTO>({
  queryKey: ['report', props.reportId],
  queryFn: async () => {
    if (!useMocks) return client.getReport(props.reportId)
    const response = await fetch(new URL('@contracts/examples/report_view.mock.json', import.meta.url).href)
    return (await response.json()) as ReportViewDTO
  },
})

const drawerItems = computed(() => {
  if (!selected.value || !data.value) return []
  const block = selected.value
  const facts = (block.fact_ids ?? []).map((id) => ({ id, layer: 'fact' as const, title: id, detail: '后端确定性计算事实' }))
  const rules = (block.rule_ids ?? []).map((id) => ({ id, layer: 'rule' as const, title: id, detail: '命理规则依据' }))
  const model = (block.evidence_ids ?? []).map((id) => {
    const citation = data.value?.citations.find((item) => item.evidence_id === id)
    return {
      id,
      layer: 'model' as const,
      title: citation?.title ?? id,
      detail: citation?.source_label ?? 'RAG 参考资料',
      ...(citation?.locator ? { locator: citation.locator } : {}),
    }
  })
  return [...facts, ...rules, ...model]
})

function showEvidence(block: ReportBlockDTO) {
  selected.value = block
  drawerOpen.value = true
}
async function share() { shareInfo.value = await client.createShare(props.reportId) }
async function revokeShare() {
  if (!shareInfo.value) return
  await client.revokeShare(shareInfo.value.share_id)
  shareInfo.value = null
}
function printReport() { window.print() }
</script>

<template>
  <section class="report-page" aria-labelledby="report-title">
    <p v-if="isLoading" class="state-card">正在加载命理分析…</p>
    <p v-else-if="isError" class="state-card error-card" role="alert">{{ error?.message }}</p>
    <template v-else-if="data">
      <header class="report-hero">
        <span class="report-seal">析</span>
        <div><p class="eyebrow">大模型 + RAG 综合分析</p><h1 id="report-title">{{ data.title }}</h1>
          <p>生成于 {{ new Date(data.generated_at).toLocaleString('zh-CN') }}</p>
        </div>
      </header>

      <nav class="report-toc" aria-label="报告目录">
        <a v-for="item in data.toc" :key="item.anchor" :href="`#${item.anchor}`">{{ item.title }}</a>
      </nav>

      <div class="report-toolbar card-surface">
        <label class="switch-label"><input v-model="professional" type="checkbox" /><span>专业模式</span></label>
        <button type="button" @click="printReport">打印 / PDF</button>
        <button v-if="!printMode" type="button" @click="share">限时分享</button>
        <button v-if="shareInfo" type="button" @click="revokeShare">撤销</button>
      </div>
      <p v-if="shareInfo" class="share-token card-surface">分享令牌：<code>{{ shareInfo.share_token }}</code><br />过期时间：{{ shareInfo.expires_at }}</p>

      <article class="report-body">
        <template v-for="block in data.blocks" :key="block.block_id">
          <component :is="`h${block.level ?? 2}`" v-if="block.block_type === 'heading'" :id="block.anchor ?? undefined" class="report-heading">{{ block.text }}</component>
          <p v-else-if="block.block_type === 'paragraph'" class="report-paragraph">{{ block.text }}</p>
          <aside v-else-if="block.block_type === 'callout'" class="callout card-surface" :data-tone="block.tone"><strong>{{ block.title }}</strong><p>{{ block.text }}</p></aside>
          <section v-else-if="block.block_type === 'claim'" class="claim-card card-surface">
            <header><span>综合判断</span><i v-if="block.confidence">置信度 {{ Math.round(block.confidence * 100) }}%</i></header>
            <h2>{{ block.title }}</h2><p>{{ block.summary }}</p>
            <div v-if="professional && block.counterevidence?.length" class="counter-evidence"><strong>其他可能：</strong>{{ block.counterevidence.join('；') }}</div>
            <button type="button" class="evidence-button" @click="showEvidence(block)">查看命盘事实与参考资料</button>
          </section>
          <ul v-else-if="block.block_type === 'evidence_list'" class="evidence-list"><li v-for="id in block.evidence_ids" :key="id">{{ id }}</li></ul>
          <p v-else class="block-alternative">{{ block.text_alternative ?? '该内容块暂不支持展示。' }}</p>
        </template>
      </article>

      <section v-if="data.limitations.length" class="supplement-panel card-surface">
        <h2>补充说明</h2><p v-for="item in data.limitations" :key="item">{{ item }}</p>
      </section>

      <RouterLink class="full-primary-button button-link" :to="{ name: 'chart-chat', params: { chartId: data.chart_id } }">基于本命盘继续追问</RouterLink>
      <EvidenceDrawer :open="drawerOpen" :items="drawerItems" @close="drawerOpen = false" />
    </template>
  </section>
</template>
