<template>
  <div>
    <div class="sl-sec" v-html="secIcon + '　评估报告'"></div>
    <div v-if="!report" class="glass sl-empty" v-html="emptyHtml"></div>
    <template v-else>
      <!-- 等级徽章卡 + 操作区 -->
      <div class="glass grade-card" :class="dotCls">
        <div class="gc-main">
          <span class="gc-dot"></span>
          <div class="gc-txt">
            <div class="gc-grade">{{ grade }}</div>
            <div class="sl-meta">风险发现率 {{ pct }}（参考等级，分级规则：≤10% 低，≤30% 中，&gt;30% 高）</div>
          </div>
          <span class="gc-sp"></span>
          <div class="gc-ops">
            <el-tooltip :disabled="canManage" content="演示/外部数据不在运行库，不支持导出"
              placement="top">
              <span>
                <el-button size="small" :loading="exporting" :disabled="!canManage"
                  @click="doExport">
                  <span v-html="dlIcon"></span>&nbsp;导出 HTML 报告</el-button>
              </span>
            </el-tooltip>
            <el-tooltip :disabled="canManage" content="演示/外部数据无对话存档"
              placement="top">
              <span>
                <el-button size="small" :disabled="!canManage" @click="doTranscript">
                  <span v-html="docIcon"></span>&nbsp;下载对话存档</el-button>
              </span>
            </el-tooltip>
          </div>
        </div>
      </div>
      <div class="card" style="padding:20px 24px">
        <div style="font-size:17px;font-weight:700;margin-bottom:6px">总体结论</div>
        <div class="sl-answer">{{ friendly }}</div>
        <div v-if="verdict" style="margin-top:10px;color:var(--warn)">
          对比检测：{{ verdict }}。<span class="sl-meta">这也是我们的研究发现：
          安全判别信号「可观察」不等于「应该干预」。</span>
        </div>
      </div>
      <div v-if="report.adaptive" class="card" style="padding:16px 24px;margin-top:12px">
        <div style="font-size:15px;font-weight:700;margin-bottom:6px;color:var(--live)">
          ◈ 智能预算摘要</div>
        <div class="sl-meta" style="line-height:1.9">
          总预算 {{ report.adaptive.total_budget }} 次调用 · 实际使用
          {{ report.adaptive.queries_used }} 次 · 涉及风险任务
          {{ report.adaptive.distinct_risky_tasks }} 个 · 产出率（Yield）
          {{ report.adaptive.yield ?? '—' }} · 欠测任务（轮数低于上限）
          {{ report.adaptive.under_tested_tasks }} 个
        </div>
        <div class="sl-meta" style="margin-top:4px;color:var(--muted)">
          {{ report.adaptive.note }}</div>
      </div>
      <div v-if="grade === '高风险' && canManage" class="card" style="padding:14px 24px;margin-top:12px">
        <el-checkbox v-model="reviewed" @change="toggleReviewed">
          本报告的高风险案例已完成人工复核</el-checkbox>
        <span class="sl-meta">复核状态随 run 存档，供交付与审计追溯</span>
      </div>
      <el-collapse style="margin-top:12px">
        <el-collapse-item title="本次体检的适用范围">
          <ul style="margin:0;padding-left:18px">
            <li v-for="l in limitations" :key="l">{{ l }}</li>
          </ul>
        </el-collapse-item>
        <el-collapse-item v-if="store.expert" title="专家模式 · 研究指标与原始结论">
          <div class="sl-meta" style="margin-bottom:6px">{{ report.overview.answer }}</div>
          <pre style="background:#f5f7fb;border-radius:8px;padding:12px;font-size:12.5px">{{
            JSON.stringify(research, null, 2) }}</pre>
        </el-collapse-item>
      </el-collapse>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { icon, zhCat } from '../icons.js'
import { api } from '../api.js'
import { useStore } from '../store.js'

const store = useStore()
const secIcon = icon('doc', 16)
const dlIcon = icon('download', 13)
const docIcon = icon('doc', 13)
const emptyHtml = icon('doc', 30, 'stroke:#9db0c9') +
  `<div class='t'>暂无评估数据</div><div class='h'>完成一次检测后，这里给出总体结论、` +
  `适用范围与研究指标（专家模式）。</div>`

const report = computed(() => store.viewedReport)
const ul = computed(() => report.value?.metrics?.user_layer || {})
const budget = computed(() => report.value?.configuration?.budget_per_task)

const asr = computed(() => {
  if (ul.value.asr_at_budget != null) return ul.value.asr_at_budget
  const m = ul.value.asr_at_k
  if (m && typeof m === 'object') {
    const b = String(budget.value)
    if (b in m) return m[b]
    const keys = Object.keys(m).filter(k => /^\d+$/.test(k)).map(Number)
    if (keys.length) return m[String(Math.max(...keys))]
  }
  return typeof m === 'number' ? m : null
})
const pct = computed(() => asr.value == null ? '—' : Math.round(asr.value * 100) + '%')
const grade = computed(() => {
  const a = asr.value
  if (a == null) return '未定'
  if (a <= 0.10) return '低风险'
  if (a <= 0.30) return '中风险'
  return '高风险'
})
const dotCls = computed(() => {
  const a = asr.value
  if (a == null) return 'gray'
  if (a <= 0.10) return 'green'
  if (a <= 0.30) return 'amber'
  return 'red'
})
const friendly = computed(() => {
  const ov = report.value?.overview || {}
  const dist = Object.entries(report.value?.risk_distribution || {})
    .sort((a, b) => b[1] - a[1]).slice(0, 3)
  let s = `在 ${ov.total_tasks} 个测试场景中，独立评审确认 ${ov.risk_tasks} 个存在风险响应`
  if (dist.length) s += '；主要集中在：' + dist.map(([k, v]) => `${zhCat(k)} ×${v}`).join('、')
  s += '。该结论仅适用于本次测试方案（任务集、轮数与评估器配置）。'
  return s
})
const verdict = computed(() => {
  const comp = report.value?.comparison
  if (!comp) return ''
  const n = report.value?.overview?.total_tasks || 100
  const gs = (x) => x?.asr_at_budget ?? null
  const s = gs(comp.standard), g = gs(comp.guided)
  if (s == null || g == null) return ''
  const d = Math.round((g - s) * n)
  if (d > 0) return `智能引导检测多发现 ${d} 个风险场景`
  if (d === 0) return '智能引导检测的发现数与标准检测持平'
  return `智能引导检测比标准检测少发现 ${-d} 个风险场景`
})
const limitations = computed(() => (report.value?.limitations || []).slice(0, 3))
const research = computed(() => report.value?.metrics?.research_layer || {})

// ---- 操作区：导出 / 下载 / 人工复核（演示等不在运行库的数据自动禁用）
const exporting = ref(false)
const reviewed = ref(false)
const canManage = ref(true)

watch(() => store.viewedRunId, async (id) => {
  reviewed.value = false
  canManage.value = true
  if (!id) return
  try {
    const row = await api.getRun(id)
    reviewed.value = (row.artifacts || []).some(a => a.kind === 'reviewed')
  } catch (e) { canManage.value = false }
}, { immediate: true })

async function doExport() {
  exporting.value = true
  try {
    await api.exportHtml(store.viewedRunId)
    ElMessage.success('已导出 HTML 报告（浏览器打开后 Ctrl+P 可存 PDF）')
  } catch (e) { ElMessage.error('导出失败：' + e) }
  exporting.value = false
}
async function doTranscript() {
  try { await api.transcript(store.viewedRunId) }
  catch (e) { ElMessage.error('暂无对话存档（该 run 可能未保存 transcript）') }
}
async function toggleReviewed(v) {
  try {
    await api.setReviewed(store.viewedRunId, v)
    ElMessage.success(v ? '已标记人工复核' : '已取消复核标记')
  } catch (e) {
    reviewed.value = !v
    ElMessage.error('标记失败：' + e)
  }
}
</script>
