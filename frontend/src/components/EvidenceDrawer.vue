<script setup lang="ts">
defineProps<{
  open: boolean
  items: { id: string; layer: 'fact' | 'rule' | 'model'; title: string; detail: string; locator?: string }[]
}>()
const emit = defineEmits<{ close: [] }>()

const layerLabel = { fact: '确定性事实', rule: '审核规则', model: '模型归纳' } as const
</script>

<template>
  <div v-if="open" class="drawer-backdrop" @click.self="emit('close')">
    <aside class="evidence-drawer" role="dialog" aria-modal="true" aria-labelledby="evidence-title">
      <header>
        <div><p class="eyebrow">三层证据</p><h2 id="evidence-title">证据抽屉</h2></div>
        <button type="button" aria-label="关闭证据抽屉" @click="emit('close')">关闭</button>
      </header>
      <p v-if="items.length === 0" data-state="empty">当前段落没有可展示证据。</p>
      <article v-for="item in items" :key="item.id" class="evidence-card" :data-layer="item.layer">
        <span class="layer-label">{{ layerLabel[item.layer] }}</span>
        <h3>{{ item.title }}</h3>
        <p>{{ item.detail }}</p>
        <code v-if="item.locator">{{ item.locator }}</code>
      </article>
    </aside>
  </div>
</template>
