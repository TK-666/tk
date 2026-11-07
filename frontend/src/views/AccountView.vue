<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api, json } from '../api.js'
import ArtworkGrid from '../components/ArtworkGrid.vue'

const { user, refreshUser } = inject('session')
const route = useRoute()
const router = useRouter()
const mode = ref('login')
const username = ref('')
const password = ref('')
const name = ref('')
const tags = ref([])
const selected = ref([])
const favorites = ref([])
const error = ref('')
const busy = ref(false)
const removing = ref(null)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
async function submit() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await api(`/auth/${mode.value}`, json('POST', { username: username.value, password: password.value }))
    password.value = ''
    await refreshUser()
    const artwork = route.query.artwork
    if (user.value && typeof artwork === 'string' && /^[1-9][0-9]*$/.test(artwork)) {
      await router.replace(`/artworks/${artwork}`)
    }
  } catch (err) { error.value = err.message }
  finally { busy.value = false }
}
async function save() {
  if (busy.value) return
  busy.value = true
  try {
    await api('/auth/me', json('PATCH', { display_name: name.value, tag_ids: selected.value }))
    await refreshUser()
    ElMessage.success('资料已保存')
  } catch (err) { ElMessage.error(err.message) }
  finally { busy.value = false }
}

async function changePassword() {
  if (busy.value) return
  if (!currentPassword.value || newPassword.value.length < 8 || newPassword.value !== confirmPassword.value) {
    ElMessage.error('请填写当前密码和至少 8 位的新密码，并确认两次新密码一致')
    return
  }
  busy.value = true
  try {
    await api('/auth/me', json('PATCH', { current_password: currentPassword.value, password: newPassword.value }))
    currentPassword.value = newPassword.value = confirmPassword.value = ''
    ElMessage.success('密码已更新')
  } catch (err) { ElMessage.error(err.message) }
  finally { busy.value = false }
}

async function removeFavorite(id) {
  if (removing.value !== null) return
  removing.value = id
  try {
    await api(`/artworks/${id}/interaction`, json('PUT', { action: 'favorite', active: false }))
    favorites.value = favorites.value.filter(item => item.id !== id)
    ElMessage.success('已取消收藏')
  } catch (err) { ElMessage.error(err.message) }
  finally { removing.value = null }
}

onMounted(async () => {
  try { tags.value = (await api('/tags?category=style')).items }
  catch (err) { error.value = err.message }
})
watch(user, profile => {
  name.value = profile?.display_name ?? ''
  selected.value = [...(profile?.preference_tag_ids ?? [])]
}, { immediate: true })
watch(() => user.value?.id, async (id, _, onCleanup) => {
  let current = true
  onCleanup(() => { current = false })
  favorites.value = []
  if (!id) return
  try {
    const data = await api('/me/favorites')
    if (current) favorites.value = data.items
  } catch (err) {
    if (current) error.value = err.message
  }
}, { immediate: true })
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
        <el-button type="primary" native-type="submit" :loading="busy">{{ mode === 'login' ? '登录' : '注册' }}</el-button>
      </el-form>
    </template>
    <template v-else>
      <el-form class="account-form" label-position="top" @submit.prevent="save">
        <el-form-item label="昵称"><el-input v-model="name" /></el-form-item>
        <el-form-item label="偏好风格"><el-checkbox-group v-model="selected"><el-checkbox v-for="tag in tags" :key="tag.id" :value="tag.id" :label="tag.name" /></el-checkbox-group></el-form-item>
        <el-button type="primary" native-type="submit" :loading="busy">保存资料与偏好</el-button>
      </el-form>
      <h2>修改密码</h2>
      <el-form class="account-form" label-position="top" @submit.prevent="changePassword">
        <el-form-item label="当前密码"><el-input v-model="currentPassword" type="password" autocomplete="current-password" /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="newPassword" type="password" autocomplete="new-password" :maxlength="128" /></el-form-item>
        <el-form-item label="确认新密码"><el-input v-model="confirmPassword" type="password" autocomplete="new-password" :maxlength="128" /></el-form-item>
        <el-button native-type="submit" :disabled="busy">更新密码</el-button>
      </el-form>
      <h2>我的收藏</h2>
      <ArtworkGrid :items="favorites" empty="还没有收藏作品。">
        <template #actions="{ item }">
          <el-button :loading="removing === item.id" :disabled="removing !== null" @click="removeFavorite(item.id)">取消收藏</el-button>
        </template>
      </ArtworkGrid>
    </template>
  </section>
</template>
