<template>
  <div>
    <div class="sl-sec" v-html="secIcon + '　运行历史' +
      `<span class='sl-meta' style='font-weight:400'>（重启不丢，含导入的旧 run）</span>`"></div>
    <div v-if="!rows.length" class="glass sl-empty" v-html="emptyHtml"></div>
    <div class="glass hist" v-else>
      <div class="hrow" v-for="r in rows" :key="r.run_id">
        <el-tooltip v-if="r.status === 'FAILED' && r.error"
          :content="r.error" placement="top" :show-after="300">
          <span :style="{ color: stColor(r.status), fontWeight: 600, width: '80px',
            cursor: 'help', textDecoration: 'underline dotted' }">
            {{ stZh(r.status) }}</span>
        </el-tooltip>
        <span v-else :style="{ color: stColor(r.status), fontWeight: 600, width: '80px' }">
          {{ stZh(r.status) }}</span>
        <span class="rid">{{ r.run_id }} {{ r.run_id === viewedRunId ? '（当前查看）' : '' }}</span>
        <span class="sl-meta">{{ modeZh(r.mode) }}</span>
        <span class="sl-meta">{{ r.target || '' }}</span>
        <span class="sl-meta">对话 {{ r.steps_done }}/{{ r.total_steps || '?' }}</span>
        <span class="sl-meta">{{ (r.created_at || '').slice(0, 19) }}</span>
        <span class="sp"></span>
        <el-button v-if="['QUEUED', 'RUNNING', 'CANCELLING'].includes(r.status)"
          size="small" @click="doCancel(r.run_id)">停止</el-button>
        <el-button v-else-if="['CANCELLED', 'FAILED'].includes(r.status)"
          size="small" @click="doResume(r.run_id)">续跑</el-button>
        <el-button v-else-if="r.status === 'COMPLETED'"
          size="small" type="primary" plain @click="doView(r.run_id)">查看</el-button>
      </div>
    </div>
    <div class="sl-meta" style="margin-top:8px" v-if="rows.length">
      「查看」加载该 run 的真实轨迹与报告，在「轨迹回放 / 评估报告」标签页展示；
      失败原因悬停失败状态可查看。
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../api.js'
import { icon } from '../icons.js'
import { useStore } from '../store.js'

const props = defineProps({ version: Number, viewedRunId: String })
const store = useStore()
const rows = ref([])
const secIcon = icon('history', 16)
const emptyHtml = icon('history', 30, 'stroke:#9db0c9') +
  `<div class='t'>还没有历史运行</div><div class='h'>开始一次检测后出现在这里；` +
  `<br>过去保存的报告会在服务启动时自动导入。</div>`

const stZh = (s) => ({ COMPLETED: '✓ 完成', FAILED: '✗ 失败', CANCELLED: '⟲ 已取消',
  RUNNING: '● 运行中', CANCELLING: '… 停止中', QUEUED: '… 排队中' }[s] || s)
const stColor = (s) => ({ COMPLETED: 'var(--safe)', FAILED: 'var(--risk)',
  CANCELLED: 'var(--warn)', RUNNING: 'var(--live)', CANCELLING: 'var(--live)' }[s] || 'var(--muted)')
const modeZh = (m) => ({ standard: '标准', guided: '引导', compare: '对比' }[m] || m || '')

async function refresh() {
  try { rows.value = await api.listRuns(30) } catch (e) { /* 服务不可达 */ }
}
async function doCancel(id) {
  try {
    await api.cancel(id)
    ElMessage({ message: '已请求取消：当前调用结束或超时后生效', type: 'warning' })
  } catch (e) { ElMessage.error('取消请求失败：' + e) }
  refresh()
}
async function doResume(id) {
  try {
    await store.resumeRun(id)
    ElMessage.success('已重新排队（从检查点续跑）')
  } catch (e) { ElMessage.error('续跑失败：' + e) }
}
async function doView(id) {
  try {
    await store.viewRun(id)
    ElMessage.success('已加载该 run 的轨迹与报告')
  } catch (e) { ElMessage.error('无法加载（该 run 可能没有留存轨迹）：' + e) }
}
onMounted(refresh)
watch(() => props.version, refresh)
defineExpose({ refresh })
</script>
