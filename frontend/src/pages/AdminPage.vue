<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import type { CurrentUserDTO } from '@/api/schema'

const client = useBaziClient()
const queryClient = useQueryClient()
const username = ref('')
const password = ref('123456')
const selected = ref<CurrentUserDTO | null>(null)
const selectedData = ref<{ charts: unknown[]; reports: unknown[]; threads: unknown[] } | null>(null)
const error = ref('')
const { data: users, isLoading } = useQuery({ queryKey: ['admin-users'], queryFn: () => client.listUsers() })
const pendingUsers = computed(() => users.value?.filter((user) => user.approval_status === 'pending') ?? [])
const managedUsers = computed(() => users.value?.filter((user) => user.approval_status !== 'pending') ?? [])

async function refresh() {
  await queryClient.invalidateQueries({ queryKey: ['admin-users'] })
}

async function create() {
  if (!username.value.trim() || password.value.length < 6) return
  error.value = ''
  try {
    await client.createUser(username.value.trim(), password.value)
    username.value = ''
    password.value = '123456'
    await refresh()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message.replace(/^\w+: /, '') : '创建失败'
  }
}

async function approve(user: CurrentUserDTO) {
  await client.approveUser(user.user_id)
  await refresh()
}

async function reject(user: CurrentUserDTO) {
  if (!window.confirm(`拒绝 ${user.username} 的注册申请？`)) return
  await client.rejectUser(user.user_id)
  await refresh()
}

async function reset(user: CurrentUserDTO) {
  const nextPassword = window.prompt(`为 ${user.username} 设置临时密码`, '123456')
  if (!nextPassword) return
  await client.resetUserPassword(user.user_id, nextPassword)
  window.alert('密码已重置，用户下次登录后应修改密码。')
}

async function inspect(user: CurrentUserDTO) {
  selected.value = user
  selectedData.value = await client.getAdminUserData(user.user_id)
}

function statusLabel(user: CurrentUserDTO) {
  return user.approval_status === 'approved' ? '已通过' : user.approval_status === 'rejected' ? '已拒绝' : '待审批'
}
</script>

<template>
  <section class="admin-page">
    <header class="page-heading">
      <p class="eyebrow">管理员工作台</p>
      <h1>用户审批与管理</h1>
      <p>审批注册申请、创建测试账号、重置密码，并查看各用户的数据。</p>
    </header>

    <section class="card-surface admin-section">
      <div class="section-title-row"><div><p class="eyebrow">待处理</p><h2>注册申请</h2></div><span class="count-badge">{{ pendingUsers.length }}</span></div>
      <p v-if="!pendingUsers.length" class="muted-copy">暂无待审批用户。</p>
      <div class="admin-user-list">
        <article v-for="user in pendingUsers" :key="user.user_id">
          <div><strong>{{ user.username }}</strong><span>申请时间 {{ new Date(user.created_at).toLocaleString() }}</span></div>
          <button class="approve-button" type="button" @click="approve(user)">通过</button>
          <button class="ghost-button" type="button" @click="reject(user)">拒绝</button>
        </article>
      </div>
    </section>

    <form class="admin-create card-surface" @submit.prevent="create">
      <div><p class="eyebrow">快速创建</p><h2>新增已审批用户</h2></div>
      <input v-model="username" placeholder="用户名" maxlength="64" required />
      <input v-model="password" type="password" placeholder="初始密码" minlength="6" required />
      <button type="submit">创建用户</button>
    </form>
    <p v-if="error" class="inline-error">{{ error }}</p>

    <section class="card-surface admin-section">
      <div class="section-title-row"><div><p class="eyebrow">账户列表</p><h2>全部用户</h2></div><span class="count-badge">{{ managedUsers.length }}</span></div>
      <p v-if="isLoading" class="state-card">正在加载用户…</p>
      <div v-else class="admin-user-list">
        <article v-for="user in managedUsers" :key="user.user_id">
          <div><strong>{{ user.username }}</strong><span>{{ user.role }} · {{ statusLabel(user) }}</span></div>
          <button type="button" @click="inspect(user)">查看数据</button>
          <button v-if="user.role !== 'admin'" class="ghost-button" type="button" @click="reset(user)">重置密码</button>
        </article>
      </div>
    </section>

    <section v-if="selected && selectedData" class="card-surface admin-inspector">
      <h2>{{ selected.username }} 的数据概览</h2>
      <div class="admin-data-counts">
        <span>命盘 {{ selectedData.charts.length }}</span>
        <span>报告 {{ selectedData.reports.length }}</span>
        <span>对话 {{ selectedData.threads.length }}</span>
      </div>
      <details><summary>查看命盘数据</summary><pre>{{ JSON.stringify(selectedData.charts, null, 2) }}</pre></details>
      <details><summary>查看报告数据</summary><pre>{{ JSON.stringify(selectedData.reports, null, 2) }}</pre></details>
      <details><summary>查看对话数据</summary><pre>{{ JSON.stringify(selectedData.threads, null, 2) }}</pre></details>
    </section>
  </section>
</template>
