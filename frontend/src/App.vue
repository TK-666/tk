<script setup>
import { onMounted, provide, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from './api.js'

const router = useRouter()
const user = ref(null)
async function refreshUser() {
  try { user.value = (await api('/auth/me')).user }
  catch { user.value = null }
}
async function logout() {
  await api('/auth/logout', { method: 'POST' })
  user.value = null
  router.push('/')
}
provide('session', { user, refreshUser })
onMounted(refreshUser)
</script>

<template>
  <el-container class="shell">
    <el-header class="topbar">
      <router-link class="brand" to="/">艺境<span>ART</span></router-link>
      <nav aria-label="主导航">
        <router-link to="/">发现</router-link>
        <router-link to="/artworks">作品</router-link>
        <router-link to="/account">{{ user ? '我的账号' : '登录 / 注册' }}</router-link>
        <router-link v-if="user?.role === 'admin'" to="/admin">管理</router-link>
      </nav>
      <el-button v-if="user" text @click="logout">退出</el-button>
    </el-header>
    <el-main><router-view /></el-main>
    <el-footer>基于风格标签的美术作品欣赏智能推荐系统</el-footer>
  </el-container>
</template>
