<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useBaziClient } from '@/api'

const client = useBaziClient()
const route = useRoute()
const router = useRouter()
const username = ref('admin')
const password = ref('123456')
const error = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const user = await client.login(username.value, password.value)
    sessionStorage.setItem('bazi:current-user', JSON.stringify(user))
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="login-page">
    <form class="login-card card-surface" @submit.prevent="submit">
      <div class="round-seal">命</div>
      <p class="eyebrow">本地八字智能体</p>
      <h1>登录门户</h1>
      <label><span>用户名</span><input v-model="username" autocomplete="username" /></label>
      <label><span>密码</span><input v-model="password" type="password" autocomplete="current-password" /></label>
      <p v-if="error" class="inline-error">{{ error }}</p>
      <button class="full-primary-button" type="submit" :disabled="loading">{{ loading ? '登录中…' : '登录' }}</button>
      <small>首次启动：admin / 123456，可在本地环境配置中修改。</small>
    </form>
  </section>
</template>
