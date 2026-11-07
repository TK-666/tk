<script setup>
import { inject, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, json } from '../api.js'

const route = useRoute()
const router = useRouter()
const { user } = inject('session')
const item = ref(null)
const emptyInteraction = { liked: false, favorited: false, rating: null }
const interaction = ref(emptyInteraction)
const error = ref('')
const ready = ref(false)
const saving = ref(false)

watch(() => route.params.id, async (id, _, onCleanup) => {
  let current = true
  onCleanup(() => { current = false })
  item.value = null
  error.value = ''
  if (!id) return
  try {
    const data = await api(`/artworks/${id}`)
    if (current) item.value = data.item
  } catch (err) {
    if (current) error.value = err.message
  }
}, { immediate: true })

watch([item, () => user.value?.id], async ([artwork, userId], _, onCleanup) => {
  let current = true
  onCleanup(() => { current = false })
  interaction.value = emptyInteraction
  ready.value = false
  if (!artwork || !userId) return
  try {
    const data = await api(`/artworks/${artwork.id}/interaction`)
    if (current) {
      interaction.value = data
      ready.value = true
    }
  } catch (err) {
    if (current) ElMessage.error(err.message)
  }
})

async function update(action, value) {
  const artwork = item.value
  const userId = user.value?.id
  if (!artwork) return
  if (!userId) {
    await router.push({ path: '/account', query: { artwork: String(artwork.id) } })
    return
  }
  if (!ready.value || saving.value) return
  saving.value = true
  try {
    const change = action === 'rate' ? { action, score: value } : { action, active: value }
    const data = await api(`/artworks/${artwork.id}/interaction`, json('PUT', change))
    if (item.value === artwork && user.value?.id === userId) {
      interaction.value = data
      ElMessage.success('已保存')
    }
  } catch (err) {
    if (item.value === artwork && user.value?.id === userId) ElMessage.error(err.message)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section v-if="item" class="detail">
    <div class="detail-image"><img v-if="item.image_url || item.cover_url" :src="item.image_url || item.cover_url" :alt="item.title" /><span v-else>ART</span></div>
    <div class="detail-copy">
      <p class="eyebrow">ARTWORK DETAIL</p><h1>{{ item.title }}</h1><p class="artist">{{ item.artist || '佚名' }}</p>
      <div class="tags"><el-tag v-for="tag in item.tags" :key="tag.id" effect="plain">{{ tag.name }}</el-tag></div>
      <p>{{ item.description || '暂无作品简介。' }}</p>
      <a v-if="item.image_url" :href="item.image_url" target="_blank" rel="noopener noreferrer">查看高清原图</a>
      <h3>关于作者</h3><p>{{ item.artist_bio || '暂无作者介绍。' }}</p>
      <div class="actions">
        <el-button :disabled="saving || (!!user && !ready)" :type="interaction.liked ? 'primary' : 'default'" @click="update('like', !interaction.liked)">{{ interaction.liked ? '取消点赞' : '点赞' }}</el-button>
        <el-button :disabled="saving || (!!user && !ready)" :type="interaction.favorited ? 'primary' : 'default'" @click="update('favorite', !interaction.favorited)">{{ interaction.favorited ? '取消收藏' : '收藏' }}</el-button>
        <el-rate v-if="user" :disabled="saving || !ready" :model-value="interaction.rating || 0" @change="score => update('rate', score)" />
        <el-button v-else text @click="update('rate')">登录后评分</el-button>
      </div>
    </div>
  </section>
  <el-alert v-else-if="error" :title="error" type="error" show-icon />
</template>
