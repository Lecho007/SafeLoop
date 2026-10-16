<template>
  <header class="site-hd">
    <div class="site-hd-in">
      <a class="brand" href="#/home">
        <span class="logo" v-html="logoIcon"></span>
        <span class="bt">SafeLoop<i>安全评估平台</i></span>
      </a>
      <nav class="nav">
        <a v-for="n in NAV" :key="n.key" :href="n.hash"
          :class="{ on: route === n.key }">{{ n.label }}</a>
      </nav>
      <span class="sp"></span>
      <el-popover placement="bottom-end" :width="330" trigger="click">
        <template #reference>
          <button class="hd-icon-btn" title="API 访问密钥">
            <span v-html="keyIcon"></span>
          </button>
        </template>
        <div class="sl-meta" style="margin-bottom:8px">
          服务端启用 SAFELOOP_API_KEY 鉴权时在此填写访问密钥；只存本机浏览器，不落盘。</div>
        <el-input v-model="apiKeyInput" placeholder="X-API-Key（留空 = 不启用）" clearable />
        <el-button size="small" style="margin-top:10px" @click="saveKey">保存</el-button>
      </el-popover>
      <el-switch v-model="store.expert" active-text="专家模式" />
      <a class="cta" href="#/workbench">开始检测</a>
    </div>
  </header>
</template>

<script setup>
// 智谱式通栏导航:白底毛玻璃 + 品牌区 + 水平导航 + 右侧动作(密钥/专家/CTA)
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { icon } from '../icons.js'
import { useStore } from '../store.js'
import { NAV, useRoute } from '../router.js'

const store = useStore()
const route = useRoute()
const logoIcon = icon('shield', 20, 'stroke:#ffffff')
const keyIcon = icon('key', 15)
const apiKeyInput = ref(localStorage.getItem('safeloop_api_key') || '')

function saveKey() {
  const v = apiKeyInput.value.trim()
  if (v) localStorage.setItem('safeloop_api_key', v)
  else localStorage.removeItem('safeloop_api_key')
  ElMessage.success(v ? '密钥已保存（本机浏览器）' : '已清除密钥')
}
</script>
