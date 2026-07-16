<template>
  <section class="home-dashboard">
    <article class="hero-card card-surface">
      <div>
        <p class="eyebrow">确定性排盘 · RAG 命理分析</p>
        <h1>把命盘事实与命理解读放在同一处</h1>
        <p>支持真太阳时、四柱十神、藏干、空亡、纳音、十二长生、神煞、大运流年，以及年、月、日运势追问。</p>
      </div>
      <div class="hero-symbol" aria-hidden="true">☯</div>
    </article>

    <RouterLink class="home-primary-action" to="/charts/new">开始排盘</RouterLink>

    <div class="feature-grid">
      <RouterLink class="feature-card wide" to="/charts/new">
        <span class="feature-icon">◉</span><span><strong>开始合盘</strong><small>建立个人命盘并生成分析</small></span>
      </RouterLink>
      <RouterLink class="feature-card" to="/history">
        <span class="feature-icon">⌁</span><span><strong>八字论财</strong><small>查看命盘与历史报告</small></span>
      </RouterLink>
      <RouterLink class="feature-card" to="/history">
        <span class="feature-icon">✣</span><span><strong>多盘对比</strong><small>从记录中切换不同命盘</small></span>
      </RouterLink>
      <article class="feature-card calendar-card">
        <span class="calendar-icon">三</span>
        <strong>万年历与流运</strong>
        <small>按节气查看流年、流月与流日</small>
      </article>
    </div>

    <section class="assistant-entry card-surface">
      <div class="assistant-orb">真</div>
      <div><strong>命盘智能助手</strong><p>完成排盘后，可继续询问事业、财运、感情和具体日期。</p></div>
    </section>
  </section>
</template>
