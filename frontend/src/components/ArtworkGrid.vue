<script setup>
defineProps({ items: { type: Array, default: () => [] }, empty: { type: String, default: '暂无作品' } })
</script>

<template>
  <el-empty v-if="!items.length" :description="empty" />
  <div v-else class="art-grid">
    <article v-for="item in items" :key="item.id" class="art-card">
      <router-link :to="`/artworks/${item.id}`">
        <div class="art-image">
          <img v-if="item.cover_url || item.image_url" :src="item.cover_url || item.image_url" :alt="item.title" loading="lazy" />
          <span v-else>ART</span>
        </div>
        <div class="art-meta">
          <h3>{{ item.title }}</h3>
          <p>{{ item.artist || '佚名' }}</p>
          <div class="tags"><el-tag v-for="tag in item.tags.slice(0, 3)" :key="tag.id" size="small" effect="plain">{{ tag.name }}</el-tag></div>
          <p v-if="item.recommendation_reason" class="recommendation-reason">{{ item.recommendation_reason }}</p>
          <p v-if="item.itemcf_evidence" class="recommendation-reason">
            你曾与《{{ item.itemcf_evidence.source_title }}》互动，另有 {{ item.itemcf_evidence.shared_user_count }} 位用户与这两件作品都互动过。
          </p>
        </div>
      </router-link>
      <div v-if="$slots.actions" class="art-meta"><slot name="actions" :item="item" /></div>
    </article>
  </div>
</template>
