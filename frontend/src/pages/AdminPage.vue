<script setup lang="ts">
import { ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import type { CurrentUserDTO } from '@/api/schema'

const client = useBaziClient()
const queryClient = useQueryClient()
const username = ref('')
const selected = ref<CurrentUserDTO | null>(null)
const selectedData = ref<{ charts: unknown[]; threads: unknown[] } | null>(null)
const error = ref('')
const { data: users, isLoading } = useQuery({ queryKey: ['admin-users'], queryFn: () => client.listUsers() })

async function create() {
  if (!username.value.trim()) return
  error.value = ''
  try {
    await client.createUser(username.value.trim())
    username.value = ''
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] })
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '创建失败'
  }
}

async function reset(user: CurrentUserDTO) {
  if (!window.confirm(`将 ${user.username} 的密码重置为默认密码 123456？`)) return
  await client.resetUserPassword(user.user_id)
  window.alert('已重置为默认密码。')
}

async function inspect(user: CurrentUserDTO) {
  selected.value = user
  selectedData.value = await client.getAdminUserData(user.user_id)
}
</script>

<template>
  <section class="admin-page">
    <header class="page-heading"><p class="eyebrow">玩具级后台</p><h1>系统后台</h1><p>创建用户、重置密码，并查看用户的排盘和对话记录。</p></header>
    <form class="admin-create card-surface" @submit.prevent="create">
      <input v-model="username" placeholder="新用户名" maxlength="64" />
      <button type="submit">创建用户（初始密码 123456）</button>
    </form>
    <p v-if="error" class="inline-error">{{ error }}</p>
    <p v-if="isLoading" class="state-card">正在加载用户…</p>
    <div v-else class="admin-user-list">
      <article v-for="user in users" :key="user.user_id" class="card-surface">
        <div><strong>{{ user.username }}</strong><span>{{ user.role }}</span></div>
        <button type="button" @click="inspect(user)">查看数据</button>
        <button type="button" @click="reset(user)">重置密码</button>
      </article>
    </div>
    <section v-if="selected && selectedData" class="card-surface admin-inspector">
      <h2>{{ selected.username }} 的数据</h2>
      <h3>排盘（{{ selectedData.charts.length }}）</h3>
      <pre>{{ JSON.stringify(selectedData.charts, null, 2) }}</pre>
      <h3>对话（{{ selectedData.threads.length }}）</h3>
      <pre>{{ JSON.stringify(selectedData.threads, null, 2) }}</pre>
    </section>
  </section>
</template>
