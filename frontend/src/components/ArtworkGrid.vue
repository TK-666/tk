<script setup>
defineProps({ items: { type: Array, default: () => [] }, empty: { type: String, default: '暂无作品' } })
</script>

<template>
  <el-empty v-if="!items.length" :description="empty" />
  <div v-else class="art-grid">
    <router-link v-for="item in items" :key="item.id" :to="`/artworks/${item.id}`" class="art-card">
      <div class="art-image">
        <img v-if="item.cover_url || item.image_url" :src="item.cover_url || item.image_url" :alt="item.title" loading="lazy" />
        <span v-else>ART</span>
      </div>
      <div class="art-meta">
        <h3>{{ item.title }}</h3>
        <p>{{ item.artist || '佚名' }}</p>
        <div class="tags"><el-tag v-for="tag in item.tags.slice(0, 3)" :key="tag.id" size="small" effect="plain">{{ tag.name }}</el-tag></div>
      </div>
    </router-link>
  </div>
</template>
