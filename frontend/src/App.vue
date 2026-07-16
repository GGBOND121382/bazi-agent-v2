<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/">四柱研习</RouterLink>
      <nav aria-label="主导航">
        <RouterLink to="/charts/new">新建命盘</RouterLink>
        <RouterLink to="/history">历史</RouterLink>
        <RouterLink to="/settings">设置</RouterLink>
      </nav>
    </header>
    <main class="page-shell"><RouterView /></main>
    <footer>传统文化规则辅助研习，不构成医疗、投资或法律建议。</footer>
  </div>
</template>
