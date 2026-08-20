<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError, useBaziClient } from '@/api'
import type {
  ChatScope,
  ChatThreadSummaryDTO,
  ChatTurnDTO,
  FortuneChatResponseDTO,
  FortuneChatSectionDTO,
  TemporalDayunDTO,
} from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const route = useRoute()
const scopeOptions: { value: ChatScope; label: string }[] = [
  { value: 'lifecycle', label: '一生' },
  { value: 'dayun', label: '大运' },
  { value: 'year', label: '年' },
  { value: 'month', label: '月' },
  { value: 'day', label: '日' },
]

function todayLocal(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function initialScope(): ChatScope {
  const value = String(route.query.scope ?? '')
  return ['general', 'dayun', 'lifecycle', 'year', 'month', 'day'].includes(value)
    ? (value as ChatScope)
    : 'dayun'
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  sections?: FortuneChatSectionDTO[]
  citations?: FortuneChatResponseDTO['citations']
  generationTrace?: Record<string, unknown>
}

const scope = ref<ChatScope>(initialScope())
const targetDate = ref(todayLocal())
const dayuns = ref<TemporalDayunDTO[]>([])
const selectedDayunIndex = ref<number | undefined>()
const question = ref('请分析这一步大运的事业、财运、感情六亲与健康，并说明它与前后大运的承接。')
const sending = ref(false)
const error = ref<string | null>(null)
const chatEnd = ref<HTMLElement | null>(null)
const threads = ref<ChatThreadSummaryDTO[]>([])
const threadId = ref<string | undefined>()
const messages = ref<ChatMessage[]>([
  {
    role: 'assistant',
    content: '可以询问出生至起运、任意一步大运，以及流年、流月、流日中的事业、财运、感情六亲和健康。我会使用确定性命盘与大运表回答。',
  },
])

const quickPrompts = computed(() => {
  if (scope.value === 'lifecycle') return ['从出生到晚年的大运主线', '哪几步大运事业财运最好？', '六亲和健康在哪些大运变化最大？']
  if (scope.value === 'dayun') return ['这步大运的事业与财运', '这步大运的婚恋和六亲', '这步大运的健康倾向']
  if (scope.value === 'day') return ['今天适合谈合作吗？', '今天财运和开支要注意什么？', '今天感情与健康要注意什么？']
  if (scope.value === 'month') return ['这个月事业上有哪些机会？', '这个月财运如何安排？', '这个月六亲与健康要注意什么？']
  return ['今年事业发展的关键月份', '今年财运的机会与风险', '今年感情六亲与健康趋势']
})

function historyPayload(): ChatTurnDTO[] {
  return messages.value.slice(-8).filter((item) => item.content.trim()).map((item) => ({ role: item.role, content: item.content }))
}

async function loadTemporal() {
  const year = Number(targetDate.value.slice(0, 4))
  const temporal = await client.getTemporalContext(props.chartId, year, targetDate.value)
  dayuns.value = temporal.dayuns
  if (selectedDayunIndex.value === undefined) selectedDayunIndex.value = temporal.active_dayun?.index ?? temporal.dayuns[0]?.index
}

async function refreshThreads() {
  threads.value = await client.listChatThreads(props.chartId)
}

async function loadThread(id: string) {
  const data = await client.getChatThread(id)
  threadId.value = id
  scope.value = data.thread.scope
  messages.value = data.messages.map((item) => ({
    role: item.role,
    content: item.content,
    ...(item.payload?.sections ? { sections: item.payload.sections } : {}),
    ...(item.payload?.citations ? { citations: item.payload.citations } : {}),
    ...(item.payload?.generation_trace ? { generationTrace: item.payload.generation_trace } : {}),
  }))
}

function newThread() {
  threadId.value = undefined
  messages.value = [{ role: 'assistant', content: '已开始新对话。请选择大运或时间范围后提问。' }]
}

async function send(preset?: string) {
  const text = (preset ?? question.value).trim()
  if (!text || sending.value) return
  error.value = null
  const history = historyPayload()
  messages.value.push({ role: 'user', content: text })
  question.value = ''
  sending.value = true
  await nextTick()
  chatEnd.value?.scrollIntoView({ behavior: 'smooth' })
  try {
    const response = await client.chatAboutChart(props.chartId, {
      question: text,
      scope: scope.value,
      target_date: targetDate.value,
      history,
      school: 'engineering_policy',
      ...(threadId.value ? { thread_id: threadId.value } : {}),
      ...(scope.value === 'dayun' && selectedDayunIndex.value !== undefined
        ? { target_dayun_index: selectedDayunIndex.value }
        : {}),
    })
    threadId.value = response.thread_id
    messages.value.push({
      role: 'assistant',
      content: response.answer,
      sections: response.sections,
      citations: response.citations,
      generationTrace: response.generation_trace,
    })
    await refreshThreads()
  } catch (cause) {
    const message = cause instanceof ApiError && cause.detail.error_code === 'MODEL_PROVIDER_ERROR'
      ? '模型本次未生成有效答复，请稍后重试。'
      : cause instanceof Error ? cause.message : '问答请求失败'
    question.value = text
    error.value = message
    messages.value.push({ role: 'assistant', content: `暂时无法完成本次分析：${message}` })
  } finally {
    sending.value = false
    await nextTick()
    chatEnd.value?.scrollIntoView({ behavior: 'smooth' })
  }
}

watch(targetDate, () => void loadTemporal())
onMounted(async () => {
  await Promise.all([loadTemporal(), refreshThreads()])
  const routeThread = typeof route.query.thread === 'string' ? route.query.thread : undefined
  if (routeThread) await loadThread(routeThread)
})
</script>

<template>
  <section class="chat-page" aria-labelledby="chat-title">
    <header class="page-heading compact-heading">
      <p class="eyebrow">命盘追问</p>
      <h1 id="chat-title">大运与流运问答</h1>
      <p>完整覆盖出生至起运、各步大运，以及流年、流月、流日中的事业、财运、感情六亲和健康。</p>
    </header>

    <div class="chat-history-bar card-surface">
      <select :value="threadId ?? ''" @change="($event.target as HTMLSelectElement).value ? loadThread(($event.target as HTMLSelectElement).value) : newThread()">
        <option value="">新对话</option>
        <option v-for="item in threads" :key="item.thread_id" :value="item.thread_id">{{ item.title }}</option>
      </select>
      <button type="button" @click="newThread">新建</button>
    </div>

    <div class="chat-controls card-surface">
      <div class="segmented-control" aria-label="分析时间范围">
        <button v-for="item in scopeOptions" :key="item.value" type="button" :class="{ active: scope === item.value }" @click="scope = item.value">
          {{ item.label }}运
        </button>
      </div>
      <label v-if="scope === 'dayun'" class="field-row">
        <span>选择大运</span>
        <select v-model.number="selectedDayunIndex">
          <option v-for="item in dayuns" :key="item.index" :value="item.index">
            {{ item.ganzhi }}（{{ item.start_age }}～{{ item.end_age }}岁，{{ item.start_year }}～{{ item.end_year }}）
          </option>
        </select>
      </label>
      <label v-if="scope === 'year' || scope === 'month' || scope === 'day'" class="field-row">
        <span>目标日期</span><input v-model="targetDate" type="date" />
      </label>
    </div>

    <div class="quick-question-row" aria-label="快捷问题">
      <button v-for="item in quickPrompts" :key="item" type="button" @click="send(item)">{{ item }}</button>
    </div>

    <div class="message-list" aria-live="polite">
      <article v-for="(message, index) in messages" :key="index" class="chat-message" :data-role="message.role">
        <div class="message-avatar" aria-hidden="true">{{ message.role === 'assistant' ? '真' : '我' }}</div>
        <div class="message-bubble">
          <p>{{ message.content }}</p>
          <section v-for="section in message.sections" :key="section.title" class="answer-section">
            <h2>{{ section.title }}</h2><p>{{ section.content }}</p>
            <div v-if="section.opportunities?.length" class="answer-list positive"><strong>机会</strong><span v-for="item in section.opportunities" :key="item">{{ item }}</span></div>
            <div v-if="section.cautions?.length" class="answer-list caution"><strong>注意</strong><span v-for="item in section.cautions" :key="item">{{ item }}</span></div>
            <div v-if="section.timing?.length" class="answer-list timing"><strong>时机</strong><span v-for="item in section.timing" :key="item">{{ item }}</span></div>
          </section>
          <details v-if="message.citations?.length" class="citation-details">
            <summary>查看 {{ message.citations.length }} 条参考资料</summary>
            <ul><li v-for="item in message.citations" :key="item.evidence_id"><strong>{{ item.title ?? item.evidence_id }}</strong><span>{{ item.locator ?? item.source_id }}</span></li></ul>
          </details>
          <details v-if="message.generationTrace" class="citation-details generation-details">
            <summary>查看本次生成过程</summary>
            <pre>{{ JSON.stringify(message.generationTrace, null, 2) }}</pre>
          </details>
        </div>
      </article>
      <article v-if="sending" class="chat-message" data-role="assistant"><div class="message-avatar">真</div><div class="message-bubble typing"><span></span><span></span><span></span></div></article>
      <div ref="chatEnd"></div>
    </div>

    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <form class="chat-composer" @submit.prevent="send()">
      <textarea v-model="question" rows="2" maxlength="2000" placeholder="例如：第三步大运的婚姻、父母关系和健康需要注意什么？"></textarea>
      <button type="submit" class="send-button" :disabled="sending || !question.trim()" aria-label="发送问题">➤</button>
    </form>
  </section>
</template>
