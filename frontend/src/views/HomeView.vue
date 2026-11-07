<script setup>
import { computed, inject, ref, watch } from 'vue'
import { api } from '../api.js'
import ArtworkGrid from '../components/ArtworkGrid.vue'

const { user } = inject('session')
const mode = ref('personal')
const items = ref([])
const strategy = ref('')
const error = ref('')
const loading = ref(false)
let requestId = 0
const guidance = computed(() => {
  if (mode.value !== 'personal') return ''
  if (strategy.value === 'guest_fallback') return '登录并选择喜欢的风格，即可获得更贴合你的推荐。'
  if (strategy.value === 'cold_start') return '浏览、点赞或收藏作品后，推荐会逐渐贴近你的喜好。'
  if (strategy.value === 'preferences') return '已根据你选择的风格推荐作品。'
  if (strategy.value === 'hybrid') {
    return user.value?.preference_tag_ids.length
      ? '已结合偏好风格与浏览、点赞、收藏和评分记录推荐。'
      : '已根据你的浏览、点赞、收藏和评分记录推荐。'
  }
  return ''
})
async function load() {
  const currentRequest = ++requestId
  loading.value = true
  error.value = ''
  strategy.value = ''
  items.value = []
  try {
    const result = await api(`/recommendations?kind=${mode.value}`)
    if (currentRequest === requestId) { items.value = result.items; strategy.value = result.strategy }
  } catch (err) {
    if (currentRequest === requestId) { error.value = err.message; items.value = [] }
  } finally { if (currentRequest === requestId) loading.value = false }
}
watch([mode, () => mode.value === 'personal' ? user.value?.id : undefined], load, { immediate: true })
</script>

<template>
  <section class="hero">
    <p class="eyebrow">DISCOVER ART THROUGH YOUR TASTE</p>
    <h1>遇见与你共鸣的艺术</h1>
    <p>从喜欢的风格出发，探索作品背后的灵感与故事。</p>
    <router-link to="/artworks"><el-button type="primary" size="large">浏览全部作品</el-button></router-link>
  </section>
  <section class="content-section">
    <div class="section-head"><div><p class="eyebrow">CURATED FOR YOU</p><h2>发现作品</h2></div>
      <el-segmented v-model="mode" :options="[{ label: '为你推荐', value: 'personal' }, { label: '热门', value: 'hot' }, { label: '最新', value: 'latest' }]" />
    </div>
    <p v-if="guidance" class="recommendation-guidance">{{ guidance }} <router-link v-if="strategy === 'guest_fallback'" to="/account">设置我的偏好</router-link></p>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <div v-loading="loading"><ArtworkGrid :items="items" :empty="strategy === 'empty' ? '还没有已发布的作品，可由管理员先添加作品。' : '暂时没有可推荐的作品，去作品库看看吧。'" /></div>
  </section>
</template>
