<script setup lang="ts">
import { ref } from 'vue'
import { useBaziClient } from '@/api'

const client = useBaziClient()
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const error = ref('')
const submitted = ref(false)
const loading = ref(false)

async function submit() {
  error.value = ''
  if (password.value !== confirmPassword.value) {
    error.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  try {
    await client.register(username.value, password.value)
    submitted.value = true
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message.replace(/^\w+: /, '') : '注册失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="login-page">
    <div v-if="submitted" class="login-card card-surface registration-success">
      <div class="round-seal">候</div>
      <h1>注册申请已提交</h1>
      <p>管理员审批通过后即可登录。</p>
      <RouterLink class="full-primary-button auth-button-link" to="/login">返回登录</RouterLink>
    </div>
    <form v-else class="login-card card-surface" @submit.prevent="submit">
      <p class="eyebrow">新用户申请</p>
      <h1>注册账号</h1>
      <label><span>用户名</span><input v-model.trim="username" minlength="2" maxlength="64" required /></label>
      <label><span>设置密码</span><input v-model="password" type="password" minlength="6" maxlength="128" required /></label>
      <label><span>确认密码</span><input v-model="confirmPassword" type="password" minlength="6" maxlength="128" required /></label>
      <p v-if="error" class="inline-error">{{ error }}</p>
      <button class="full-primary-button" type="submit" :disabled="loading">{{ loading ? '提交中…' : '提交注册申请' }}</button>
      <RouterLink class="auth-secondary-link" to="/login">已有账号，返回登录</RouterLink>
    </form>
  </section>
</template>
