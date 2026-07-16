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
  const rules = (block.rule_ids ?? []).map((id) => ({ id, layer: 'rule' as const, title: id, detail: '版本化规则引用' }))
  const model = (block.evidence_ids ?? []).map((id) => {
    const citation = data.value?.citations.find((item) => item.evidence_id === id)
    return {
      id,
      layer: 'model' as const,
      title: citation?.title ?? id,
      detail: citation?.source_label ?? '审核证据',
      ...(citation?.locator ? { locator: citation.locator } : {}),
    }
  })
  return [...facts, ...rules, ...model]
})

function showEvidence(block: ReportBlockDTO) {
  selected.value = block
  drawerOpen.value = true
}

async function share() {
  shareInfo.value = await client.createShare(props.reportId)
}

async function revokeShare() {
  if (!shareInfo.value) return
  await client.revokeShare(shareInfo.value.share_id)
  shareInfo.value = null
}

function printReport() {
  window.print()
}
</script>

<template>
  <section class="report-layout" aria-labelledby="report-title">
    <p v-if="isLoading" data-state="loading">正在加载报告…</p>
    <p v-else-if="isError" data-state="error" role="alert">{{ error?.message }}</p>
    <template v-else-if="data">
      <aside class="toc"><strong>目录</strong><a v-for="item in data.toc" :key="item.anchor" :href="`#${item.anchor}`">{{ item.title }}</a></aside>
      <article class="report-body">
        <header><p class="eyebrow">验证后的结构化报告</p><h1 id="report-title">{{ data.title }}</h1>
          <label><input v-model="professional" type="checkbox" /> 专业模式</label>
          <button type="button" @click="printReport">打印 / 保存 PDF</button>
          <button v-if="!printMode" type="button" @click="share">创建限时分享</button>
          <button v-if="shareInfo" type="button" @click="revokeShare">撤销分享</button>
          <p v-if="shareInfo" class="share-token">分享令牌仅显示一次：<code>{{ shareInfo.share_token }}</code>，过期时间 {{ shareInfo.expires_at }}</p>
        </header>
        <template v-for="block in data.blocks" :key="block.block_id">
          <component :is="`h${block.level ?? 2}`" v-if="block.block_type === 'heading'" :id="block.anchor ?? undefined">{{ block.text }}</component>
          <p v-else-if="block.block_type === 'paragraph'">{{ block.text }}</p>
          <aside v-else-if="block.block_type === 'callout'" class="callout" :data-tone="block.tone"><strong>{{ block.title }}</strong><p>{{ block.text }}</p></aside>
          <article v-else-if="block.block_type === 'claim'" class="claim-card">
            <span>模型归纳 · 置信度 {{ block.confidence ?? '—' }}</span><h2>{{ block.title }}</h2><p>{{ block.summary }}</p>
            <p v-if="professional && block.counterevidence?.length"><strong>反向证据：</strong>{{ block.counterevidence.join('；') }}</p>
            <button type="button" @click="showEvidence(block)">查看事实、规则与证据</button>
          </article>
          <ul v-else-if="block.block_type === 'evidence_list'"><li v-for="id in block.evidence_ids" :key="id">{{ id }}</li></ul>
          <p v-else class="block-alternative">{{ block.text_alternative ?? '该结构块请在专业模式中查看。' }}</p>
        </template>
        <section class="limitations"><h2>限制说明</h2><ul><li v-for="item in data.limitations" :key="item">{{ item }}</li></ul></section>
      </article>
    </template>
    <EvidenceDrawer :open="drawerOpen" :items="drawerItems" @close="drawerOpen = false" />
  </section>
</template>
