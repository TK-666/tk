<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
import ArtworkGrid from '../components/ArtworkGrid.vue'

const mode = ref('personal')
const items = ref([])
const error = ref('')
const loading = ref(false)
async function load() {
  loading.value = true
  error.value = ''
  try { items.value = (await api(`/recommendations?kind=${mode.value}`)).items }
  catch (err) { error.value = err.message }
  finally { loading.value = false }
}
onMounted(load)
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
      <el-segmented v-model="mode" :options="[{ label: '为你推荐', value: 'personal' }, { label: '热门', value: 'hot' }, { label: '最新', value: 'latest' }]" @change="load" />
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <div v-loading="loading"><ArtworkGrid :items="items" empty="还没有已发布的作品，可由管理员先添加作品。" /></div>
  </section>
</template>
