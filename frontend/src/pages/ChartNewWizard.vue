<script setup lang="ts">
/**
 * Birth info wizard (F2). 4 steps:
 *   1. Identity & gender
 *   2. Birth datetime + timezone
 *   3. Birthplace (city, longitude)
 *   4. Advanced (precision, uncertainty, profile)
 *
 * Submit triggers a POST /v1/charts via BaziClient. On success, route to
 * /charts/:chartId. On failure, surface the api-error envelope inline.
 *
 * Mock-data fast-path: if `VITE_USE_MOCKS=true` we skip the network call
 * and load contracts/examples/chart_overview.mock.json so designers can
 * iterate without a backend.
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useBaziClient, ApiError, type BirthRequest } from '@/api'

const router = useRouter()
const client = useBaziClient()

const useMocks = import.meta.env.VITE_USE_MOCKS === 'true'

const step = ref(1)
const submitting = ref(false)
const submitError = ref<string | null>(null)

const form = ref({
  gender: 'unspecified' as BirthRequest['gender'],
  birthDate: '1990-06-15',
  birthTime: '12:00',
  timezone: 'Asia/Shanghai',
  city: 'Shanghai',
  country: 'CN',
  longitude: 121.5,
  latitude: 31.2,
  timePrecision: 'minute' as BirthRequest['time_precision'],
  uncertaintyMinutes: 0,
  calculationProfileId: 'ziping_standard_v1',
  userFocus: [] as string[],
})

onMounted(() => {
  // Try to restore a draft from localStorage
  const draft = localStorage.getItem('bazi:draft:birth')
  if (draft) {
    try {
      Object.assign(form.value, JSON.parse(draft))
    } catch {
      // ignore corrupt drafts
    }
  }
})

function persistDraft() {
  localStorage.setItem('bazi:draft:birth', JSON.stringify(form.value))
}

function buildRequest(): BirthRequest {
  const req: BirthRequest = {
    schema_version: 'birth-request-v1',
    gender: form.value.gender,
    birth_datetime_local: `${form.value.birthDate}T${form.value.birthTime}:00`,
    timezone: form.value.timezone,
    birthplace: {
      country: form.value.country,
      city: form.value.city,
      longitude: form.value.longitude,
      latitude: form.value.latitude,
    },
    calculation_profile_id: form.value.calculationProfileId,
  }
  // Only attach optional fields when they have meaningful values, to keep
  // exactOptionalPropertyTypes happy.
  if (form.value.timePrecision) req.time_precision = form.value.timePrecision
  if (form.value.uncertaintyMinutes) req.uncertainty_minutes = form.value.uncertaintyMinutes
  if (form.value.userFocus.length) req.user_focus = form.value.userFocus
  return req
}

const isStepValid = computed(() => {
  if (step.value === 1) return form.value.gender !== undefined
  if (step.value === 2) return !!form.value.birthDate && !!form.value.birthTime && !!form.value.timezone
  if (step.value === 3) return !!form.value.city && !!form.value.country
  return true
})

async function submit() {
  submitError.value = null
  submitting.value = true
  persistDraft()
  try {
    if (useMocks) {
      // Designer fast-path: skip network.
      router.push({ name: 'chart-overview', params: { chartId: 'demo_chart' } })
      return
    }
    const dto = await client.createChart(buildRequest())
    localStorage.removeItem('bazi:draft:birth')
    router.push({ name: 'chart-overview', params: { chartId: dto.chart_id } })
  } catch (e) {
    if (e instanceof ApiError) {
      submitError.value = `${e.detail.error_code}: ${e.detail.message_key}`
    } else {
      submitError.value = (e as Error).message
    }
  } finally {
    submitting.value = false
  }
}

function next() {
  if (isStepValid.value && step.value < 4) {
    step.value++
  }
  // Always persist (even on invalid step) so partial drafts survive refresh.
  persistDraft()
}

function back() {
  if (step.value > 1) step.value--
}
</script>

<template>
  <section aria-labelledby="wizard-title">
    <h1 id="wizard-title">新建命盘</h1>
    <p data-state="step">第 {{ step }} / 4 步</p>

    <form @submit.prevent="step === 4 ? submit() : next()">
      <!-- Step 1: gender -->
      <fieldset v-if="step === 1">
        <legend>身份</legend>
        <label><input type="radio" v-model="form.gender" value="male" /> 男</label>
        <label><input type="radio" v-model="form.gender" value="female" /> 女</label>
        <label><input type="radio" v-model="form.gender" value="unspecified" /> 不指定</label>
      </fieldset>

      <!-- Step 2: birth datetime + timezone -->
      <fieldset v-else-if="step === 2">
        <legend>出生时间</legend>
        <label>日期 <input type="date" v-model="form.birthDate" required /></label>
        <label>时间 <input type="time" v-model="form.birthTime" required /></label>
        <label>时区 <input v-model="form.timezone" placeholder="Asia/Shanghai" required /></label>
      </fieldset>

      <!-- Step 3: birthplace -->
      <fieldset v-else-if="step === 3">
        <legend>出生地点</legend>
        <label>国家 <input v-model="form.country" required /></label>
        <label>城市 <input v-model="form.city" required /></label>
        <label>经度 <input type="number" step="0.01" v-model.number="form.longitude" /></label>
        <label>纬度 <input type="number" step="0.01" v-model.number="form.latitude" /></label>
      </fieldset>

      <!-- Step 4: advanced -->
      <fieldset v-else>
        <legend>高级</legend>
        <label>精度
          <select v-model="form.timePrecision">
            <option value="second">秒</option>
            <option value="minute">分钟</option>
            <option value="hour">小时</option>
            <option value="unknown">未知</option>
          </select>
        </label>
        <label>误差容忍（分钟） <input type="number" v-model.number="form.uncertaintyMinutes" min="0" /></label>
        <label>计算口径 <input v-model="form.calculationProfileId" /></label>
      </fieldset>

      <p v-if="submitError" data-state="error" role="alert">{{ submitError }}</p>

      <button type="button" @click="back" :disabled="step === 1 || submitting">上一步</button>
      <button type="button" data-testid="next" @click="next" :disabled="!isStepValid || submitting">
        下一步
      </button>
      <button v-if="step === 4" type="button" data-testid="submit" @click="submit" :disabled="submitting">
        {{ submitting ? '提交中…' : '提交并排盘' }}
      </button>
    </form>
  </section>
</template>