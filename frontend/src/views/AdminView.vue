<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api, json } from '../api.js'

const { user } = inject('session')
const stats = ref(null)
const artworks = ref([])
const artworkPage = ref(1)
const artworkTotal = ref(0)
const artworkQuery = ref('')
const artworkStatus = ref('')
const tags = ref([])
const users = ref([])
const deletingUserId = ref(null)
const settings = ref({ tag_weight: 3, itemcf_weight: 2 })
const form = ref(emptyArtwork())
const artworkAction = ref('')
const tagForm = ref({ name: '', category: 'style' })
const error = ref('')
function emptyArtwork() { return { title: '', artist: '', description: '', artist_bio: '', cover_url: '', image_url: '', tag_ids: [], status: 'draft', featured: false } }
function resetArtwork() { form.value = emptyArtwork() }
function artworkPath() {
  const params = new URLSearchParams({ page: artworkPage.value, per_page: 20 })
  if (artworkQuery.value) params.set('q', artworkQuery.value)
  if (artworkStatus.value) params.set('status', artworkStatus.value)
  return `/admin/artworks?${params}`
}
async function loadArtworks() {
  const result = await api(artworkPath())
  artworks.value = result.items
  artworkTotal.value = result.total
}
async function searchArtworks() {
  artworkPage.value = 1
  try { await loadArtworks(); error.value = '' } catch (err) { error.value = err.message }
}
async function changeArtworkPage() {
  try { await loadArtworks(); error.value = '' } catch (err) { error.value = err.message }
}
async function load() {
  if (user.value?.role !== 'admin') return
  try {
    const [a, b, c, d, e] = await Promise.all([api('/admin/stats'), api(artworkPath()), api('/tags'), api('/admin/users'), api('/admin/settings')])
    stats.value = a; artworks.value = b.items; artworkTotal.value = b.total; tags.value = c.items; users.value = d.items
    settings.value = { tag_weight: Number(e.items.tag_weight ?? 3), itemcf_weight: Number(e.items.itemcf_weight ?? 2) }; error.value = ''
  } catch (err) { error.value = err.message }
}
async function saveArtwork() {
  if (artworkAction.value) return
  artworkAction.value = 'save'
  try {
    const id = form.value.id
    await api(id ? `/admin/artworks/${id}` : '/admin/artworks', json(id ? 'PATCH' : 'POST', form.value))
    ElMessage.success('作品已保存'); resetArtwork(); artworkPage.value = 1; await load()
  } catch (err) { ElMessage.error(err.message) }
  finally { artworkAction.value = '' }
}
async function removeArtwork() {
  const { id } = form.value
  if (!id || artworkAction.value) return
  const title = artworks.value.find(item => item.id === id)?.title ?? form.value.title
  artworkAction.value = 'delete'
  try {
    await ElMessageBox.confirm(
      `确定永久删除《${title}》？该作品的收藏、点赞、评分和浏览记录也会删除，此操作无法撤销。`,
      '删除作品',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonType: 'danger', autofocus: false },
    )
    await api(`/admin/artworks/${id}`, { method: 'DELETE' })
    resetArtwork()
    artworkPage.value = 1
    await load()
    ElMessage.success('作品已删除')
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') ElMessage.error(err.message || String(err))
  } finally {
    artworkAction.value = ''
  }
}
function editArtwork(item) {
  if (artworkAction.value) return
  form.value = { ...item, tag_ids: item.tags.map(tag => tag.id) }
  window.scrollTo({ top: 0, behavior: 'smooth' })
}
async function upload(file, field) {
  try {
    const body = new FormData()
    body.append('file', file.raw)
    body.append('purpose', field === 'image_url' ? 'original' : 'cover')
    const result = await api('/admin/uploads', { method: 'POST', body })
    form.value[field] = result.url
    if (field === 'image_url' && !form.value.cover_url) form.value.cover_url = result.cover_url
    ElMessage.success('上传完成')
  }
  catch (err) { ElMessage.error(err.message) }
}
async function saveTag() {
  try { await api(tagForm.value.id ? `/admin/tags/${tagForm.value.id}` : '/admin/tags', json(tagForm.value.id ? 'PATCH' : 'POST', tagForm.value)); tagForm.value = { name: '', category: 'style' }; load() }
  catch (err) { ElMessage.error(err.message) }
}
function editTag(item) { tagForm.value = { ...item } }
async function removeTag(id) {
  try {
    await ElMessageBox.confirm('删除后，作品与用户偏好中的这个标签也会移除。', '确认删除标签', { type: 'warning' })
    await api(`/admin/tags/${id}`, { method: 'DELETE' }); await load()
  } catch (err) { if (err !== 'cancel') ElMessage.error(err.message || String(err)) }
}
async function toggleUser(item) {
  try { await api(`/admin/users/${item.id}`, json('PATCH', { enabled: !item.enabled })); load() }
  catch (err) { ElMessage.error(err.message) }
}
async function resetPassword(item) {
  try {
    const { value } = await ElMessageBox.prompt(`为 ${item.username} 设置新密码（至少 8 字符）`, '重置密码', { inputType: 'password' })
    await api(`/admin/users/${item.id}`, json('PATCH', { password: value }))
    ElMessage.success('密码已重置')
  } catch (err) { if (err !== 'cancel') ElMessage.error(err.message || String(err)) }
}
async function removeUser(item) {
  if (item.role === 'admin' || deletingUserId.value !== null) return
  deletingUserId.value = item.id
  try {
    await ElMessageBox.confirm(
      `确定永久删除账号「${item.username}」？该用户的偏好、收藏、点赞、评分和浏览记录也会删除，此操作无法撤销。`,
      '删除用户',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消', confirmButtonType: 'danger', autofocus: false },
    )
    await api(`/admin/users/${item.id}`, { method: 'DELETE', headers: { 'If-Match': `"${item.created_at}"` } })
    await load()
    ElMessage.success('用户已删除')
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') ElMessage.error(err.message || String(err))
  } finally {
    deletingUserId.value = null
  }
}
async function saveSettings() {
  try { await api('/admin/settings', json('PUT', settings.value)); ElMessage.success('推荐权重已保存') }
  catch (err) { ElMessage.error(err.message) }
}
onMounted(load)
watch(user, load)
</script>

<template>
  <section class="content-section">
    <p class="eyebrow">MANAGE THE COLLECTION</p><h1>管理后台</h1>
    <el-alert v-if="user?.role !== 'admin'" title="请使用管理员账号登录。" type="warning" show-icon />
    <template v-else>
      <el-alert v-if="error" :title="error" type="error" show-icon />
      <div v-if="stats" class="stats"><div>用户 <strong>{{ stats.users }}</strong></div><div>作品 <strong>{{ stats.artworks }}</strong></div><div>已发布 <strong>{{ stats.published }}</strong></div><div>浏览 <strong>{{ stats.views }}</strong></div></div>
      <el-tabs>
        <el-tab-pane label="作品管理">
          <h2>{{ form.id ? '编辑作品' : '添加作品' }}</h2>
          <el-form class="editor" label-position="top" @submit.prevent="saveArtwork">
            <div class="form-row"><el-form-item label="标题"><el-input v-model="form.title" /></el-form-item><el-form-item label="作者"><el-input v-model="form.artist" /></el-form-item></div>
            <el-form-item label="作品简介"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
            <el-form-item label="作者介绍"><el-input v-model="form.artist_bio" type="textarea" :rows="2" /></el-form-item>
            <div class="form-row"><el-form-item label="封面地址"><el-input v-model="form.cover_url" /></el-form-item><el-upload :show-file-list="false" :auto-upload="false" accept="image/png,image/jpeg,image/webp" @change="file => upload(file, 'cover_url')"><el-button>上传封面</el-button></el-upload></div>
            <img v-if="form.cover_url" class="upload-preview" :src="form.cover_url" alt="封面预览" />
            <div class="form-row"><el-form-item label="原图地址（发布前必填）"><el-input v-model="form.image_url" /></el-form-item><el-upload :show-file-list="false" :auto-upload="false" accept="image/png,image/jpeg,image/webp" @change="file => upload(file, 'image_url')"><el-button>上传原图并生成封面</el-button></el-upload></div>
            <el-form-item label="标签"><el-select v-model="form.tag_ids" multiple filterable placeholder="选择标签"><el-option v-for="tag in tags" :key="tag.id" :label="`${tag.category} · ${tag.name}`" :value="tag.id" /></el-select></el-form-item>
            <div class="form-row"><el-form-item label="状态"><el-select v-model="form.status"><el-option label="草稿" value="draft" /><el-option label="发布" value="published" /><el-option label="下架" value="archived" /></el-select></el-form-item><el-form-item label="热门置顶"><el-switch v-model="form.featured" /></el-form-item></div>
            <el-button type="primary" native-type="submit" :loading="artworkAction === 'save'" :disabled="artworkAction === 'delete'">保存作品</el-button>
            <template v-if="form.id">
              <el-button :disabled="!!artworkAction" @click="resetArtwork">取消编辑</el-button>
              <el-button type="danger" plain :loading="artworkAction === 'delete'" :disabled="artworkAction === 'save'" @click="removeArtwork">删除作品</el-button>
            </template>
          </el-form>
          <div class="form-row"><el-input v-model="artworkQuery" placeholder="搜索作品或作者" clearable @keyup.enter="searchArtworks" /><el-select v-model="artworkStatus" placeholder="全部状态" clearable><el-option label="草稿" value="draft" /><el-option label="发布" value="published" /><el-option label="下架" value="archived" /></el-select><el-button @click="searchArtworks">查询</el-button></div>
          <el-table :data="artworks" class="admin-table"><el-table-column label="封面" width="90"><template #default="scope"><img v-if="scope.row.cover_url" class="table-cover" :src="scope.row.cover_url" :alt="scope.row.title" /></template></el-table-column><el-table-column prop="title" label="作品" /><el-table-column prop="artist" label="作者" /><el-table-column prop="status" label="状态" /><el-table-column label="操作"><template #default="scope"><el-button text type="primary" @click="editArtwork(scope.row)">编辑</el-button></template></el-table-column></el-table>
          <el-pagination v-if="artworkTotal > 20" v-model:current-page="artworkPage" class="pagination" background layout="prev, pager, next" :total="artworkTotal" :page-size="20" @current-change="changeArtworkPage" />
        </el-tab-pane>
        <el-tab-pane label="标签管理">
          <el-form class="tag-editor" label-position="top" size="large" @submit.prevent="saveTag">
            <el-form-item label="标签名称">
              <el-input v-model="tagForm.name" placeholder="请输入标签名称" />
            </el-form-item>
            <el-form-item label="标签类别">
              <el-select v-model="tagForm.category">
                <el-option label="风格" value="style" />
                <el-option label="题材" value="topic" />
                <el-option label="媒介" value="medium" />
                <el-option label="年代" value="era" />
              </el-select>
            </el-form-item>
            <el-button type="primary" native-type="submit">{{ tagForm.id ? '保存修改' : '添加' }}</el-button>
          </el-form>
          <el-table :data="tags" class="admin-table"><el-table-column prop="name" label="名称" /><el-table-column prop="category" label="类别" /><el-table-column label="操作"><template #default="scope"><el-button text type="primary" @click="editTag(scope.row)">编辑</el-button><el-button text type="danger" @click="removeTag(scope.row.id)">删除</el-button></template></el-table-column></el-table>
        </el-tab-pane>
        <el-tab-pane label="用户管理">
          <el-table :data="users">
            <el-table-column prop="username" label="用户名" />
            <el-table-column prop="role" label="角色" />
            <el-table-column label="状态">
              <template #default="{ row }">{{ row.enabled ? '启用' : '禁用' }}</template>
            </el-table-column>
            <el-table-column label="操作" min-width="235">
              <template #default="{ row }">
                <el-button text :disabled="deletingUserId === row.id" @click="toggleUser(row)">{{ row.enabled ? '禁用' : '启用' }}</el-button>
                <el-button text :disabled="deletingUserId === row.id" @click="resetPassword(row)">重置密码</el-button>
                <el-button v-if="row.role !== 'admin'" text type="danger" :loading="deletingUserId === row.id" :disabled="deletingUserId !== null" @click="removeUser(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane label="推荐配置"><div class="form-row"><el-input-number v-model="settings.tag_weight" :min="0" :max="100" /> 标签权重 <el-input-number v-model="settings.itemcf_weight" :min="0" :max="100" /> 协同过滤权重 <el-button type="primary" @click="saveSettings">保存</el-button></div></el-tab-pane>
      </el-tabs>
    </template>
  </section>
</template>

<style scoped>
.tag-editor {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(128px, 1fr) auto;
  align-items: end;
  gap: 16px;
  max-width: 640px;
}

.tag-editor .el-form-item { margin-bottom: 0; }

@media (max-width: 600px) {
  .tag-editor { grid-template-columns: minmax(0, 1fr); }
  .tag-editor .el-button { justify-self: start; }
}
</style>
