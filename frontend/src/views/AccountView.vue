<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api, json } from '../api.js'
import ArtworkGrid from '../components/ArtworkGrid.vue'

const { user, refreshUser } = inject('session')
const mode = ref('login')
const username = ref('')
const password = ref('')
const name = ref('')
const tags = ref([])
const selected = ref([])
const favorites = ref([])
const error = ref('')
async function submit() {
  try {
    await api(`/auth/${mode.value}`, json('POST', { username: username.value, password: password.value }))
    await refreshUser(); await loadProfile(); password.value = ''; error.value = ''
  } catch (err) { error.value = err.message }
}
async function loadProfile() {
  if (!user.value) return
  name.value = user.value.display_name
  selected.value = user.value.preference_tag_ids
  try { favorites.value = (await api('/me/favorites')).items } catch (err) { error.value = err.message }
}
async function save() {
  try {
    await api('/auth/me', json('PATCH', { display_name: name.value }))
    await api('/auth/preferences', json('PUT', { tag_ids: selected.value }))
    await refreshUser(); ElMessage.success('资料已保存')
  } catch (err) { ElMessage.error(err.message) }
}
onMounted(async () => { try { tags.value = (await api('/tags?category=style')).items } catch (err) { error.value = err.message }; loadProfile() })
watch(user, loadProfile)
</script>

<template>
  <section class="content-section account">
    <p class="eyebrow">YOUR COLLECTION</p><h1>{{ user ? '我的账号' : '欢迎来到艺境' }}</h1>
    <el-alert v-if="error" :title="error" type="error" show-icon />
    <template v-if="!user">
      <el-segmented v-model="mode" :options="[{ label: '登录', value: 'login' }, { label: '注册', value: 'register' }]" />
      <el-form class="account-form" label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名"><el-input v-model="username" autocomplete="username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="password" type="password" show-password :autocomplete="mode === 'login' ? 'current-password' : 'new-password'" /></el-form-item>
        <el-button type="primary" native-type="submit">{{ mode === 'login' ? '登录' : '注册' }}</el-button>
      </el-form>
    </template>
    <template v-else>
      <el-form class="account-form" label-position="top" @submit.prevent="save">
        <el-form-item label="昵称"><el-input v-model="name" /></el-form-item>
        <el-form-item label="偏好风格"><el-checkbox-group v-model="selected"><el-checkbox v-for="tag in tags" :key="tag.id" :value="tag.id" :label="tag.name" /></el-checkbox-group></el-form-item>
        <el-button type="primary" native-type="submit">保存偏好</el-button>
      </el-form>
      <h2>我的收藏</h2><ArtworkGrid :items="favorites" empty="还没有收藏作品。" />
    </template>
  </section>
</template>
