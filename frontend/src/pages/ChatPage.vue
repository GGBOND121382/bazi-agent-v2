<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useBaziClient } from '@/api'
import type {
  ChatScope,
  ChatTurnDTO,
  FortuneChatResponseDTO,
  FortuneChatSectionDTO,
} from '@/api/schema'

const props = defineProps<{ chartId: string }>()
const client = useBaziClient()
const route = useRoute()
const scopeOptions: { value: ChatScope; label: string }[] = [
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
  return value === 'month' || value === 'day' || value === 'general' ? value : 'year'
}

function initialDate(): string {
  const value = String(route.query.date ?? '')
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : todayLocal()
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  sections?: FortuneChatSectionDTO[]
  citations?: FortuneChatResponseDTO['citations']
}

const scope = ref<ChatScope>(initialScope())
const targetDate = ref(initialDate())
const question = ref('请结合原局、大运和流年，分析我今年的事业、财运与感情。')
const sending = ref(false)
const error = ref<string | null>(null)
const chatEnd = ref<HTMLElement | null>(null)
const messages = ref<ChatMessage[]>([
  {
    role: 'assistant',
    content: '可以继续问今年、某月或某一天的事业、财运、感情与行动时机。我会结合原局、大运、流年、流月或流日以及 RAG 资料回答。',
  },
])

const quickPrompts = computed(() => {
  if (scope.value === 'day') {
    return ['今天适合谈合作吗？', '今天财运和开支要注意什么？', '今天感情沟通的重点是什么？']
  }
  if (scope.value === 'month') {
    return ['这个月事业上有哪些机会？', '这个月财运如何安排？', '这个月感情关系要注意什么？']
  }
  return ['今年事业发展的关键月份', '今年财运的机会与风险', '今年感情运势和相处建议']
})

function historyPayload(): ChatTurnDTO[] {
  return messages.value
    .slice(-8)
    .filter((item) => item.content.trim())
    .map((item) => ({ role: item.role, content: item.content }))
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
    })
    messages.value.push({
      role: 'assistant',
      content: response.answer,
      sections: response.sections,
      citations: response.citations,
    })
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : '问答请求失败'
    error.value = message
    messages.value.push({ role: 'assistant', content: `暂时无法完成本次分析：${message}` })
  } finally {
    sending.value = false
    await nextTick()
    chatEnd.value?.scrollIntoView({ behavior: 'smooth' })
  }
}
</script>

<template>
  <section class="chat-page" aria-labelledby="chat-title">
    <header class="page-heading compact-heading">
      <p class="eyebrow">命盘追问</p>
      <h1 id="chat-title">流年运势问答</h1>
      <p>选择时间范围后直接提问，系统会自动补齐相应的大运、流年、流月和流日上下文。</p>
    </header>

    <div class="chat-controls card-surface">
      <div class="segmented-control" aria-label="分析时间范围">
        <button v-for="item in scopeOptions" :key="item.value" type="button"
          :class="{ active: scope === item.value }" @click="scope = item.value">
          {{ item.label }}运
        </button>
      </div>
      <label class="field-row">
        <span>目标日期</span>
        <input v-model="targetDate" type="date" />
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
            <h2>{{ section.title }}</h2>
            <p>{{ section.content }}</p>
            <div v-if="section.opportunities?.length" class="answer-list positive">
              <strong>机会</strong><span v-for="item in section.opportunities" :key="item">{{ item }}</span>
            </div>
            <div v-if="section.cautions?.length" class="answer-list caution">
              <strong>注意</strong><span v-for="item in section.cautions" :key="item">{{ item }}</span>
            </div>
            <div v-if="section.timing?.length" class="answer-list timing">
              <strong>时机</strong><span v-for="item in section.timing" :key="item">{{ item }}</span>
            </div>
          </section>
          <details v-if="message.citations?.length" class="citation-details">
            <summary>查看 {{ message.citations.length }} 条参考资料</summary>
            <ul>
              <li v-for="item in message.citations" :key="item.evidence_id">
                <strong>{{ item.title ?? item.evidence_id }}</strong>
                <span>{{ item.locator ?? item.source_id }}</span>
              </li>
            </ul>
          </details>
        </div>
      </article>
      <article v-if="sending" class="chat-message" data-role="assistant">
        <div class="message-avatar" aria-hidden="true">真</div>
        <div class="message-bubble typing"><span></span><span></span><span></span></div>
      </article>
      <div ref="chatEnd"></div>
    </div>

    <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
    <form class="chat-composer" @submit.prevent="send()">
      <textarea v-model="question" rows="2" maxlength="2000" placeholder="例如：今年哪几个月更适合换工作或争取晋升？"></textarea>
      <button type="submit" class="send-button" :disabled="sending || !question.trim()" aria-label="发送问题">➤</button>
    </form>
  </section>
</template>
