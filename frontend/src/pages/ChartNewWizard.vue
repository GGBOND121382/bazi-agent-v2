<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, useBaziClient, type BirthRequest } from '@/api'
import { chartMetaKey, userStorageKey } from '@/utils/user-context'

const router = useRouter()
const client = useBaziClient()
const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'
const submitting = ref(false)
const submitError = ref<string | null>(null)
const showAdvanced = ref(false)
const draftKey = userStorageKey('draft:birth')

const form = ref({
  name: '',
  gender: 'male' as BirthRequest['gender'],
  birthDate: '1990-01-01',
  birthTime: '00:00',
  timezone: 'Asia/Shanghai',
  city: '北京',
  province: '北京',
  country: 'CN',
  longitude: 116.42,
  latitude: 39.93,
  timePrecision: 'minute' as NonNullable<BirthRequest['time_precision']>,
  uncertaintyMinutes: 0,
  calculationProfileId: 'ziping_standard_v1',
  userFocus: ['命局结构', '事业财运', '感情关系'],
})

onMounted(() => {
  const draft = localStorage.getItem(draftKey)
  if (!draft) return
  try {
    Object.assign(form.value, JSON.parse(draft))
  } catch {
    localStorage.removeItem(draftKey)
  }
})

const locationText = computed(() => `${form.value.city || '未知地区'} · ${form.value.timezone}`)
const coordinateText = computed(() => `北纬 ${Math.abs(form.value.latitude).toFixed(2)}°　东经 ${Math.abs(form.value.longitude).toFixed(2)}°`)
const canSubmit = computed(() => Boolean(form.value.birthDate && form.value.birthTime && form.value.timezone && form.value.city))

function persistDraft() {
  localStorage.setItem(draftKey, JSON.stringify(form.value))
}

function toggleAdvanced(event: Event) {
  showAdvanced.value = (event.currentTarget as HTMLDetailsElement).open
}

function buildRequest(): BirthRequest {
  const request: BirthRequest = {
    schema_version: 'birth-request-v1',
    gender: form.value.gender,
    birth_datetime_local: `${form.value.birthDate}T${form.value.birthTime}:00`,
    timezone: form.value.timezone,
    birthplace: {
      country: form.value.country,
      province: form.value.province,
      city: form.value.city,
      longitude: form.value.longitude,
      latitude: form.value.latitude,
    },
    calculation_profile_id: form.value.calculationProfileId,
    time_precision: form.value.timePrecision,
    user_focus: form.value.userFocus,
  }
  if (form.value.uncertaintyMinutes > 0) request.uncertainty_minutes = form.value.uncertaintyMinutes
  return request
}

async function submit() {
  if (!canSubmit.value || submitting.value) return
  submitError.value = null
  submitting.value = true
  persistDraft()
  try {
    const chartId = useMocks
      ? 'demo_chart'
      : (await client.createChart(buildRequest())).chart_id
    localStorage.setItem(chartMetaKey(chartId), JSON.stringify({
      name: form.value.name.trim() || '未命名命盘',
      gender: form.value.gender,
      birthDate: form.value.birthDate,
      city: form.value.city,
    }))
    localStorage.removeItem(draftKey)
    await router.push({ name: 'chart-overview', params: { chartId } })
  } catch (cause) {
    if (cause instanceof ApiError) submitError.value = `${cause.detail.error_code}: ${cause.detail.message_key}`
    else submitError.value = cause instanceof Error ? cause.message : '排盘失败'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <section class="birth-page" aria-labelledby="birth-title">
    <header class="page-heading compact-heading">
      <p class="eyebrow">出生信息</p>
      <h1 id="birth-title">建立命盘</h1>
      <p>时间和经纬度会直接影响真太阳时与时柱，请尽量准确填写。</p>
    </header>

    <form class="birth-card card-surface" @submit.prevent="submit">
      <label class="line-field name-field">
        <span>姓名</span>
        <input v-model.trim="form.name" placeholder="请输入姓名或命盘备注" maxlength="30" @change="persistDraft" />
      </label>

      <div class="form-split-row">
        <div class="segmented-control compact" aria-label="性别">
          <button type="button" :class="{ active: form.gender === 'male' }" @click="form.gender = 'male'; persistDraft()">男</button>
          <button type="button" :class="{ active: form.gender === 'female' }" @click="form.gender = 'female'; persistDraft()">女</button>
        </div>
        <div class="segmented-control compact calendar-choice" aria-label="历法输入">
          <button type="button" class="active">公历</button>
          <button type="button" disabled title="后续版本开放农历直接输入">农历</button>
          <button type="button" disabled title="后续版本开放四柱直接输入">四柱</button>
        </div>
      </div>

      <div class="datetime-grid">
        <label><span>出生日期</span><input v-model="form.birthDate" type="date" required @change="persistDraft" /></label>
        <label><span>出生时间</span><input v-model="form.birthTime" type="time" required @change="persistDraft" /></label>
      </div>

      <label class="line-field">
        <span>出生地区</span>
        <input v-model.trim="form.city" required placeholder="城市" @change="persistDraft" />
      </label>
      <div class="birth-preview">
        <div><span>地区时区</span><strong>{{ locationText }}</strong></div>
        <div><span>地址经纬</span><strong>{{ coordinateText }}</strong></div>
        <div><span>计算方式</span><strong>真太阳时校正 · 节气精确交接</strong></div>
      </div>

      <details class="advanced-form" :open="showAdvanced" @toggle="toggleAdvanced">
        <summary>高级设置</summary>
        <div class="advanced-grid">
          <label><span>时区</span><input v-model.trim="form.timezone" required placeholder="Asia/Shanghai" /></label>
          <label><span>省份</span><input v-model.trim="form.province" /></label>
          <label><span>经度</span><input v-model.number="form.longitude" type="number" step="0.01" min="-180" max="180" /></label>
          <label><span>纬度</span><input v-model.number="form.latitude" type="number" step="0.01" min="-90" max="90" /></label>
          <label><span>时间精度</span>
            <select v-model="form.timePrecision">
              <option value="second">精确到秒</option><option value="minute">精确到分钟</option>
              <option value="hour">仅知小时</option><option value="unknown">时间不确定</option>
            </select>
          </label>
          <label><span>误差分钟</span><input v-model.number="form.uncertaintyMinutes" type="number" min="0" max="720" /></label>
        </div>
      </details>

      <p v-if="submitError" class="inline-error" role="alert">{{ submitError }}</p>
      <button data-testid="submit" class="full-primary-button" type="submit" :disabled="submitting || !canSubmit">
        {{ submitting ? '正在排盘…' : '开始排盘' }}
      </button>
    </form>
  </section>
</template>
