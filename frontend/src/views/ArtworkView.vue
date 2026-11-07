<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, json } from '../api.js'

const route = useRoute()
const router = useRouter()
const { user } = inject('session')
const item = ref(null)
const interaction = ref({ liked: false, favorited: false, rating: null })
const error = ref('')
async function load() {
  try {
    item.value = (await api(`/artworks/${route.params.id}`)).item
    if (user.value) interaction.value = await api(`/artworks/${route.params.id}/interaction`)
  } catch (err) { error.value = err.message }
}
async function update(action, value) {
  if (!user.value) { router.push('/account'); return }
  try {
    interaction.value = await api(`/artworks/${route.params.id}/interaction`, json('PUT', action === 'rate' ? { action, score: value } : { action, active: value }))
    ElMessage.success('已保存')
  } catch (err) { ElMessage.error(err.message) }
}
onMounted(load)
watch(() => route.params.id, load)
watch(user, async () => {
  if (user.value && item.value) {
    try { interaction.value = await api(`/artworks/${route.params.id}/interaction`) }
    catch (err) { error.value = err.message }
  }
})
</script>

<template>
  <section v-if="item" class="detail">
    <div class="detail-image"><img v-if="item.image_url || item.cover_url" :src="item.image_url || item.cover_url" :alt="item.title" /><span v-else>ART</span></div>
    <div class="detail-copy">
      <p class="eyebrow">ARTWORK DETAIL</p><h1>{{ item.title }}</h1><p class="artist">{{ item.artist || '佚名' }}</p>
      <div class="tags"><el-tag v-for="tag in item.tags" :key="tag.id" effect="plain">{{ tag.name }}</el-tag></div>
      <p>{{ item.description || '暂无作品简介。' }}</p>
      <h3>关于作者</h3><p>{{ item.artist_bio || '暂无作者介绍。' }}</p>
      <div class="actions"><el-button :type="interaction.liked ? 'primary' : 'default'" @click="update('like', !interaction.liked)">点赞</el-button>
        <el-button :type="interaction.favorited ? 'primary' : 'default'" @click="update('favorite', !interaction.favorited)">收藏</el-button>
        <el-rate :model-value="interaction.rating || 0" @change="score => update('rate', score)" /></div>
    </div>
  </section>
  <el-alert v-else-if="error" :title="error" type="error" show-icon />
</template>
