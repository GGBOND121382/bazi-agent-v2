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

const current = computed(() => events.value.at(-1))
const progress = computed(() => current.value?.progress ?? snapshot.value?.progress ?? 0)
const stage = computed(() => current.value?.stage ?? snapshot.value?.stage ?? 'queued')

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
    if (failures < 3) return
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
    <p><strong>{{ stage }}</strong> · {{ progress }}%</p>
    <ol class="job-events">
      <li v-for="event in events" :key="event.event_id">
        <span>{{ event.progress }}%</span><strong>{{ event.message_key }}</strong>
        <code v-if="event.error_code">{{ event.error_code }}</code>
      </li>
    </ol>
    <p v-if="errorMessage" role="alert" data-state="error">{{ errorMessage }}</p>
    <button v-if="!terminal.has(stage)" type="button" @click="cancel">取消任务</button>
    <button v-if="stage === 'completed'" type="button" @click="openReport">阅读报告</button>
    <p class="privacy-note">这里只展示公开阶段摘要，不展示模型内部思维链。</p>
  </section>
</template>
