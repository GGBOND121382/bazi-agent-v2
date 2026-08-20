<script setup lang="ts">
import { ref } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import { useBaziClient } from '@/api'
import { migrateLegacyStorageToAdmin, publishAuthChange, setCurrentUser } from '@/utils/user-context'

const client = useBaziClient()
const queryClient = useQueryClient()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

function safeExternalRedirect(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !value.startsWith('/') ||
    value.startsWith('//') ||
    value.includes('\\')
  ) {
    return ''
  }
  return value
}

async function submit() {
  loading.value = true
  error.value = ''
  try {
    const user = await client.login(username.value, password.value)
    queryClient.clear()
    setCurrentUser(user)
    migrateLegacyStorageToAdmin(user)
    publishAuthChange(user.user_id)
    const externalRedirect = safeExternalRedirect(route.query.external_redirect)
    if (externalRedirect) {
      window.location.assign(externalRedirect)
      return
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message.replace(/^\w+: /, '') : '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="login-page">
    <form class="login-card card-surface" @submit.prevent="submit">
      <div class="round-seal">命</div>
      <p class="eyebrow">八字智能分析门户</p>
      <h1>欢迎登录</h1>
      <p class="login-intro">登录后查看自己的命盘、报告和问答记录。</p>
      <label><span>用户名</span><input v-model.trim="username" autocomplete="username" required /></label>
      <label><span>密码</span><input v-model="password" type="password" autocomplete="current-password" required /></label>
      <p v-if="error" class="inline-error">{{ error }}</p>
      <button class="full-primary-button" type="submit" :disabled="loading">{{ loading ? '登录中…' : '登录' }}</button>
      <RouterLink class="auth-secondary-link" to="/register">没有账号？申请注册</RouterLink>
    </form>
  </section>
</template>
