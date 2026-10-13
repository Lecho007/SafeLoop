<template>
  <div class="wrap">
    <!-- 页头（sticky 玻璃） -->
    <div class="glass hd">
      <div class="logo" v-html="logoIcon"></div>
      <div>
        <h1>SafeLoop <b>安全体检</b></h1>
        <div class="sl-sub">多智能体闭环安全评估 —— 让 AI 智能体替你测试你的大模型</div>
      </div>
      <span class="sp"></span>
      <el-popover placement="bottom-end" :width="330" trigger="click">
        <template #reference>
          <el-button circle size="small" title="API 访问密钥">
            <span v-html="keyIcon"></span>
          </el-button>
        </template>
        <div class="sl-meta" style="margin-bottom:8px">
          服务端启用 SAFELOOP_API_KEY 鉴权时在此填写访问密钥；只存本机浏览器，不落盘。</div>
        <el-input v-model="apiKeyInput" placeholder="X-API-Key（留空 = 不启用）" clearable />
        <el-button size="small" style="margin-top:10px" @click="saveKey">保存</el-button>
      </el-popover>
      <el-switch v-model="store.expert" active-text="专家模式" />
    </div>

    <el-tabs v-model="tab">
      <el-tab-pane label="总览" name="overview" />
      <el-tab-pane label="轨迹回放" name="replay" />
      <el-tab-pane label="评估报告" name="report" />
    </el-tabs>

    <Overview v-show="tab === 'overview'" />
    <ReplayView v-show="tab === 'replay'" />
    <ReportView v-show="tab === 'report'" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { icon } from './icons.js'
import { useStore } from './store.js'
import Overview from './components/Overview.vue'
import ReplayView from './components/ReplayView.vue'
import ReportView from './components/ReportView.vue'

const store = useStore()
const tab = ref('overview')
const logoIcon = icon('shield', 22, 'stroke:#ffffff')
const keyIcon = icon('key', 15)
const apiKeyInput = ref(localStorage.getItem('safeloop_api_key') || '')

function saveKey() {
  const v = apiKeyInput.value.trim()
  if (v) localStorage.setItem('safeloop_api_key', v)
  else localStorage.removeItem('safeloop_api_key')
  ElMessage.success(v ? '密钥已保存（本机浏览器）' : '已清除密钥')
}

// 刷新页面后恢复活动 run 的轮询（进度不丢）
onMounted(() => store.restoreActive())
</script>
