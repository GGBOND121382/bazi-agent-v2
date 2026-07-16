<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { ref } from 'vue'
import { useBaziClient } from '@/api'
import type { UserPreferencesDTO } from '@/api/schema'

const client = useBaziClient()
const saved = ref(false)
const preferences = useQuery({ queryKey: ['preferences'], queryFn: () => client.getUserPreferences() })
const configuration = useQuery({ queryKey: ['configuration'], queryFn: () => client.getConfiguration() })

async function update(field: 'detail_level' | 'theme', value: string) {
  saved.value = false
  await client.updatePreferences({ [field]: value } as Partial<UserPreferencesDTO>)
  saved.value = true
  await preferences.refetch()
}
</script>

<template>
  <section aria-labelledby="settings-title"><p class="eyebrow">偏好与只读配置</p><h1 id="settings-title">设置</h1>
    <template v-if="preferences.data.value">
      <label>详细程度 <select :value="preferences.data.value.detail_level" @change="update('detail_level', ($event.target as HTMLSelectElement).value)"><option value="concise">简洁</option><option value="professional">专业</option></select></label>
      <label>主题 <select :value="preferences.data.value.theme" @change="update('theme', ($event.target as HTMLSelectElement).value)"><option value="light">浅色</option><option value="dark">深色</option><option value="system">跟随系统</option></select></label>
      <span v-if="saved" role="status">已保存</span>
    </template>
    <template v-if="configuration.data.value"><h2>系统配置（只读）</h2><dl>
      <dt>计算口径</dt><dd>{{ configuration.data.value.calculation_profile_id }}</dd>
      <dt>模型 Provider</dt><dd>{{ configuration.data.value.model_provider }}</dd>
      <dt>分享</dt><dd>{{ configuration.data.value.sharing_enabled ? '已启用' : '默认关闭' }}</dd>
    </dl></template>
  </section>
</template>
