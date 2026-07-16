<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const pageTitle = computed(() => String(route.meta.title ?? '问真八字'))
const chartId = computed(() => typeof route.params.chartId === 'string' ? route.params.chartId : null)
const temporalTarget = computed(() => chartId.value ? `/charts/${chartId.value}/temporal` : '/history')
const showBack = computed(() => route.name !== 'home')

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/')
}
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <button v-if="showBack" class="icon-button back-button" type="button" aria-label="返回" @click="goBack">‹</button>
      <span v-else class="topbar-spacer" aria-hidden="true"></span>
      <RouterLink class="brand" to="/">{{ pageTitle }}</RouterLink>
      <RouterLink class="topbar-action" to="/charts/new" aria-label="新建命盘">＋</RouterLink>
    </header>

    <main class="page-shell"><RouterView /></main>

    <nav class="bottom-nav" aria-label="主导航">
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
    </nav>
  </div>
</template>
