<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useBaziClient } from '@/api'
import type { AnalysisJobDTO, JobEventDTO } from '@/api/schema'

const props = defineProps<{ jobId: string }>()
const client = useBaziClient()
const router = useRouter()
const events = ref<JobEventDTO[]>([])
const snapshot = ref<AnalysisJobDTO | null>(null)
const connectionState = ref<'connecting' | 'live' | 'polling' | 'closed'>('connecting')
const errorMessage = ref<string | null>(null)
let source: EventSource | null = null
let failures = 0
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const storageKey = `bazi:last-event:${props.jobId}`
const terminal = new Set<JobEventDTO['stage']>(['completed', 'failed', 'cancelled'])
const stageLabels: Record<JobEventDTO['stage'], string> = {
  queued: '排队中',
  calculating: '排盘计算',
  needs_user_resolution: '等待确认',
  retrieving: '检索资料',
  interpreting: '模型解读',
  verifying: '结果校验',
  revision_pending: '自动修订',
  report_building: '生成报告',
  completed: '分析完成',
  failed: '分析失败',
  cancelled: '已取消',
}

const current = computed(() => events.value.at(-1))
const progress = computed(() => current.value?.progress ?? snapshot.value?.progress ?? 0)
const stage = computed(() => current.value?.stage ?? snapshot.value?.stage ?? 'queued')
const errorLabels: Record<string, string> = {
  MODEL_CONFIGURATION_ERROR: '模型配置缺失或无效',
  MODEL_TIMEOUT: '模型生成超时，可重试',
  MODEL_STREAM_INTERRUPTED: '模型传输中断，可重试',
  MODEL_OUTPUT_TRUNCATED: '模型输出达到长度上限',
  MODEL_INVALID_OUTPUT: '模型返回的结构化结果无效',
  MODEL_PROVIDER_ERROR: '模型服务拒绝了请求',
  ANALYSIS_VALIDATION_FAILED: '分析结果未通过确定性校验',
  INTERNAL_ERROR: '系统内部错误',
}

const providerPhaseLabels: Record<string, string> = {
  request_started: '连接模型',
  reasoning: '整体推理',
  answering: '生成结构化报告',
  retrying: '传输中断，自动重试',
  completed: '模型输出完成',
}

function providerPhase(event: JobEventDTO | undefined): string | null {
  const value = event?.safe_details?.provider_phase
  return typeof value === 'string' ? value : null
}

const activeProviderPhase = computed(() => providerPhase(current.value))
const stageLabel = computed(() => {
  if (stage.value === 'interpreting' && activeProviderPhase.value) {
    return providerPhaseLabels[activeProviderPhase.value] ?? stageLabels[stage.value]
  }
  return stageLabels[stage.value]
})
const modelActivity = computed(() => {
  const details = current.value?.safe_details
  if (!details || stage.value !== 'interpreting') return null
  const reasoning = typeof details.reasoning_chars === 'number' ? details.reasoning_chars : 0
  const content = typeof details.content_chars === 'number' ? details.content_chars : 0
  const attempt = typeof details.attempt === 'number' ? details.attempt : 1
  if (!reasoning && !content) return `第 ${attempt} 次模型连接`
  return `第 ${attempt} 次调用 · 推理 ${reasoning} 字符 · 报告 ${content} 字符`
})

function connect() {
  source?.close()
  connectionState.value = 'connecting'
  const lastId = sessionStorage.getItem(storageKey) ?? undefined
  source = new EventSource(client.jobEventsUrl(props.jobId, lastId))
  source.addEventListener('job', (raw) => {
    const event = JSON.parse((raw as MessageEvent<string>).data) as JobEventDTO
    if (!events.value.some((item) => item.event_id === event.event_id)) events.value.push(event)
    sessionStorage.setItem(storageKey, event.event_id)
    failures = 0
    connectionState.value = 'live'
    if (terminal.has(event.stage)) {
      source?.close()
      connectionState.value = 'closed'
    }
  })
  source.onerror = () => {
    failures += 1
    source?.close()
    void pollAndReconnect()
  }
}

async function pollAndReconnect() {
  connectionState.value = 'polling'
  try {
    snapshot.value = await client.getJob(props.jobId)
    if (terminal.has(snapshot.value.stage)) {
      connectionState.value = 'closed'
      return
    }
    reconnectTimer = setTimeout(connect, Math.min(1000 * 2 ** failures, 10000))
  } catch (cause) {
    errorMessage.value = cause instanceof Error ? cause.message : '任务状态读取失败'
  }
}

async function cancel() {
  try {
    snapshot.value = await client.cancelJob(props.jobId)
  } catch (cause) {
    errorMessage.value = cause instanceof Error ? cause.message : '取消失败'
  }
}

function openReport() {
  const ref = current.value?.result_ref ?? snapshot.value?.result_ref
  if (ref) void router.push({ name: 'report-read', params: { reportId: ref } })
}

onMounted(connect)
onBeforeUnmount(() => { source?.close(); if (reconnectTimer) clearTimeout(reconnectTimer) })
</script>

<template>
  <section aria-labelledby="progress-title">
    <p class="eyebrow">分析任务 · {{ connectionState }}</p>
    <h1 id="progress-title">结构化分析进度</h1>
    <div class="progress-track" role="progressbar" aria-label="结构化分析完成进度" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
      <span :style="{ width: `${progress}%` }"></span>
    </div>
    <p><strong>{{ stageLabel }}</strong> · {{ progress }}%</p>
    <p v-if="modelActivity" class="privacy-note">{{ modelActivity }}</p>
    <ol class="job-events">
      <li v-for="event in events" :key="event.event_id">
        <span>{{ event.progress }}%</span><strong>{{ event.stage === 'interpreting' && providerPhase(event) ? (providerPhaseLabels[providerPhase(event)!] ?? stageLabels[event.stage]) : stageLabels[event.stage] }}</strong>
        <code v-if="event.error_code">{{ errorLabels[event.error_code] ?? event.error_code }}</code>
      </li>
    </ol>
    <p v-if="errorMessage" role="alert" data-state="error">{{ errorMessage }}</p>
    <button v-if="!terminal.has(stage)" type="button" @click="cancel">取消任务</button>
    <button v-if="stage === 'completed'" type="button" @click="openReport">阅读报告</button>
    <p class="privacy-note">进度来自流式心跳；正式报告只在完整 JSON 通过校验后生成。</p>
  </section>
</template>
