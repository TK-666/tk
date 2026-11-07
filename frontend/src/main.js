import { createApp } from 'vue'
import {
  ElAlert, ElButton, ElCheckbox, ElCheckboxGroup, ElContainer,
  ElEmpty, ElFooter, ElForm, ElFormItem, ElHeader, ElInput,
  ElInputNumber, ElLoading, ElMain, ElOption, ElPagination,
  ElRate, ElSegmented, ElSelect, ElSwitch, ElTabPane, ElTable,
  ElTableColumn, ElTabs, ElTag, ElUpload,
} from 'element-plus'
import 'element-plus/dist/index.css'
import './style.css'
import App from './App.vue'
import router from './router.js'

const app = createApp(App)
for (const component of [
  ElAlert, ElButton, ElCheckbox, ElCheckboxGroup, ElContainer,
  ElEmpty, ElFooter, ElForm, ElFormItem, ElHeader, ElInput,
  ElInputNumber, ElMain, ElOption, ElPagination, ElRate,
  ElSegmented, ElSelect, ElSwitch, ElTabPane, ElTable,
  ElTableColumn, ElTabs, ElTag, ElUpload,
]) app.use(component)
app.use(ElLoading).use(router).mount('#app')
