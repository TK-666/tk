<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api.js'
import ArtworkGrid from '../components/ArtworkGrid.vue'

const items = ref([])
const tags = ref([])
const q = ref('')
const style = ref('')
const topic = ref('')
const medium = ref('')
const era = ref('')
const page = ref(1)
const total = ref(0)
const error = ref('')
async function load() {
  const params = new URLSearchParams({ page: page.value, per_page: 12 })
  if (q.value) params.set('q', q.value)
  if (style.value) params.set('style', style.value)
  if (topic.value) params.set('topic', topic.value)
  if (medium.value) params.set('medium', medium.value)
  if (era.value) params.set('era', era.value)
  try { const data = await api(`/artworks?${params}`); items.value = data.items; total.value = data.total; error.value = '' }
  catch (err) { error.value = err.message }
}
function search() { page.value = 1; load() }
onMounted(async () => { try { tags.value = (await api('/tags')).items } catch (err) { error.value = err.message }; load() })
</script>

<template>
  <section class="content-section">
    <p class="eyebrow">EXPLORE THE COLLECTION</p><h1>作品浏览</h1>
    <div class="filters">
      <el-input v-model="q" placeholder="搜索作品或作者" clearable @keyup.enter="search" />
      <el-select v-model="style" placeholder="风格" clearable><el-option v-for="tag in tags.filter(t => t.category === 'style')" :key="tag.id" :label="tag.name" :value="String(tag.id)" /></el-select>
      <el-select v-model="topic" placeholder="题材" clearable><el-option v-for="tag in tags.filter(t => t.category === 'topic')" :key="tag.id" :label="tag.name" :value="String(tag.id)" /></el-select>
      <el-select v-model="medium" placeholder="媒介" clearable><el-option v-for="tag in tags.filter(t => t.category === 'medium')" :key="tag.id" :label="tag.name" :value="String(tag.id)" /></el-select>
      <el-select v-model="era" placeholder="年代" clearable><el-option v-for="tag in tags.filter(t => t.category === 'era')" :key="tag.id" :label="tag.name" :value="String(tag.id)" /></el-select>
      <el-button type="primary" @click="search">筛选</el-button>
    </div>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <ArtworkGrid :items="items" />
    <el-pagination v-if="total > 12" v-model:current-page="page" class="pagination" background layout="prev, pager, next" :total="total" :page-size="12" @current-change="load" />
  </section>
</template>
