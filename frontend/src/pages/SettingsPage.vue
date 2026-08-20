<script setup lang="ts">
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useBaziClient } from '@/api'
import type { UserPreferencesDTO } from '@/api/schema'
import { clearCurrentUser, currentUserId } from '@/utils/user-context'

const client = useBaziClient()
const router = useRouter()
const queryClient = useQueryClient()
const userId = currentUserId()
const saved = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const passwordMessage = ref('')
const passwordError = ref('')
const preferences = useQuery({ queryKey: ['preferences', userId], queryFn: () => client.getUserPreferences() })
const configuration = useQuery({ queryKey: ['configuration'], queryFn: () => client.getConfiguration() })

async function update(field: 'detail_level' | 'theme', value: string) {
  saved.value = false
  await client.updatePreferences({ [field]: value } as Partial<UserPreferencesDTO>)
  saved.value = true
  await preferences.refetch()
}

async function updatePassword() {
  passwordMessage.value = ''
  passwordError.value = ''
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  try {
    await client.changePassword(currentPassword.value, newPassword.value)
    queryClient.clear()
    clearCurrentUser()
    passwordMessage.value = '密码已修改，请重新登录。'
    setTimeout(() => router.replace('/login'), 800)
  } catch (cause) {
    passwordError.value = cause instanceof Error ? cause.message.replace(/^\w+: /, '') : '修改失败'
  }
}
</script>

<template>
  <section class="settings-page" aria-labelledby="settings-title">
    <header class="page-heading"><p class="eyebrow">个人中心</p><h1 id="settings-title">设置</h1></header>
    <section class="card-surface settings-card">
      <h2>显示偏好</h2>
      <template v-if="preferences.data.value">
        <label>详细程度 <select :value="preferences.data.value.detail_level" @change="update('detail_level', ($event.target as HTMLSelectElement).value)"><option value="concise">简洁</option><option value="professional">专业</option></select></label>
        <label>主题 <select :value="preferences.data.value.theme" @change="update('theme', ($event.target as HTMLSelectElement).value)"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label>
        <span v-if="saved" role="status">已保存</span>
      </template>
    </section>

    <form class="card-surface settings-card password-form" @submit.prevent="updatePassword">
      <h2>修改密码</h2>
      <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required /></label>
      <label>新密码<input v-model="newPassword" type="password" minlength="6" autocomplete="new-password" required /></label>
      <label>确认新密码<input v-model="confirmPassword" type="password" minlength="6" autocomplete="new-password" required /></label>
      <p v-if="passwordError" class="inline-error">{{ passwordError }}</p>
      <p v-if="passwordMessage" class="success-copy">{{ passwordMessage }}</p>
      <button type="submit">确认修改</button>
    </form>

    <section v-if="configuration.data.value" class="card-surface settings-card"><h2>系统配置（只读）</h2><dl>
      <dt>计算口径</dt><dd>{{ configuration.data.value.calculation_profile_id }}</dd>
      <dt>模型 Provider</dt><dd>{{ configuration.data.value.model_provider }}</dd>
      <dt>分享</dt><dd>{{ configuration.data.value.sharing_enabled ? '已启用' : '默认关闭' }}</dd>
    </dl></section>
  </section>
</template>