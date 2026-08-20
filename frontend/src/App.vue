<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useQueryClient } from '@tanstack/vue-query'
import { useBaziClient } from '@/api'
import {
  authEventKey,
  clearCurrentUser,
  getCurrentUser,
  migrateLegacyStorageToAdmin,
  parseAuthChange,
  publishAuthChange,
} from '@/utils/user-context'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const client = useBaziClient()
const queryClient = useQueryClient()
const pageTitle = computed(() => String(route.meta.title ?? '问真八字'))
const chartId = computed(() => typeof route.params.chartId === 'string' ? route.params.chartId : null)
const temporalTarget = computed(() => chartId.value ? `/charts/${chartId.value}/temporal` : '/history')
const showBack = computed(() => route.name !== 'home' && route.name !== 'login' && route.name !== 'register')
const showChrome = computed(() => route.name !== 'login' && route.name !== 'register')
const currentUser = ref<{ role?: string; username?: string } | null>(null)

function refreshCurrentUser() {
  const user = getCurrentUser()
  currentUser.value = user
  if (user) migrateLegacyStorageToAdmin(user)
}
watch(() => route.fullPath, refreshCurrentUser, { immediate: true })

function handleAuthStorage(event: StorageEvent) {
  if (event.key !== authEventKey()) return
  const change = parseAuthChange(event.newValue)
  if (!change) return
  const current = getCurrentUser()
  if (!current || change.user_id === current.user_id) return

  queryClient.clear()
  clearCurrentUser()
  currentUser.value = null
  if (route.name !== 'login' && route.name !== 'register') {
    void router.replace({ name: 'login', query: { redirect: route.fullPath } })
  }
}

onMounted(() => window.addEventListener('storage', handleAuthStorage))
onBeforeUnmount(() => window.removeEventListener('storage', handleAuthStorage))

async function logout() {
  try { await client.logout() } catch { /* local private state is still cleared below */ }
  queryClient.clear()
  clearCurrentUser()
  currentUser.value = null
  publishAuthChange(null)
  await router.replace('/login')
}

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}
</script>

<template>
  <div class="app-shell">
    <header v-if="showChrome" class="topbar">
      <button v-if="showBack" class="icon-button back-button" type="button" aria-label="返回" @click="goBack">‹</button>
      <span v-else class="topbar-spacer" aria-hidden="true"></span>
      <RouterLink class="brand" to="/">{{ pageTitle }}</RouterLink>
      <RouterLink v-if="currentUser?.role === 'admin'" class="topbar-action" to="/admin" aria-label="系统后台">管</RouterLink>
      <RouterLink v-else class="topbar-action" to="/charts/new" aria-label="新建命盘">＋</RouterLink>
    </header>

    <main class="page-shell"><RouterView /></main>

    <nav v-if="showChrome" class="bottom-nav" aria-label="主导航">
      <RouterLink to="/" :class="{ active: route.name === 'home' || route.name === 'chart-new' || route.name === 'chart-overview' }">
        <span class="nav-icon">☯</span><span>排盘</span>
      </RouterLink>
      <RouterLink to="/history" :class="{ active: route.name === 'history' }">
        <span class="nav-icon">▤</span><span>记录</span>
      </RouterLink>
      <RouterLink :to="temporalTarget" :class="{ active: route.name === 'temporal' || route.name === 'chart-chat' }">
        <span class="nav-icon">◫</span><span>流运</span>
      </RouterLink>
      <RouterLink to="/settings" :class="{ active: route.name === 'settings' }">
        <span class="nav-icon">☷</span><span>设置</span>
      </RouterLink>
      <button class="nav-logout" type="button" @click="logout"><span class="nav-icon">↪</span><span>退出</span></button>
    </nav>
  </div>
</template>
