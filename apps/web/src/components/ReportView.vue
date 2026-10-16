<template>
  <div>
    <div class="sl-sec" v-html="secIcon + '　评估报告'"></div>

    <!-- 空态:演示报告选择(点击即看) -->
    <div v-if="!report" class="demo-rpts">
      <div class="dr-hero">
        <div class="drh-t">选择一份报告开始</div>
        <div class="drh-d">检测完成后报告会自动展示;也可以先查看一份示例报告。</div>
      </div>
      <div class="dr-grid">
        <div v-for="d in demos" :key="d.id" class="dr-card tone-x" :class="d.tone">
          <span class="dr-badge">{{ d.badge }}</span>
          <div class="dr-t">{{ d.t }}</div>
          <div class="dr-kpi">
            <div class="dk-v" :class="d.rateCls">{{ d.rate }}</div>
            <div class="dk-k">风险发现率<br/><b>{{ d.risk }}/{{ d.total }}</b> 场景确认</div>
          </div>
          <div class="dr-d">{{ d.d }}</div>
          <el-button size="small" type="primary" plain :loading="loading === d.id"
            @click="loadDemo(d.id)">查看这份报告</el-button>
        </div>
      </div>
    </div>

    <!-- AI 分析聊天(常驻;点击生成后才开始分析) -->
    <div class="card ai-card" style="padding:16px 20px;margin-top:12px">
      <div class="ai-head">
        <span class="ai-badge">AI</span>
        <span style="font-size:15px;font-weight:700">AI 分析</span>
        <span class="sp"></span>
        <el-button v-if="chatMsgs.length" size="small" link
          :disabled="aiLoading" @click="resetAi">重新开始</el-button>
      </div>
      <div class="chat-body" ref="chatBox">
        <div v-if="!chatMsgs.length && !aiLoading" class="chat-empty">
          <el-button size="small" type="primary" plain @click="genAi('')">
            {{ report ? '生成 AI 分析' : '生成示例报告的 AI 分析' }}</el-button>
        </div>
        <template v-for="(m, i) in chatMsgs" :key="i">
          <div v-if="m.role === 'assistant'" class="msg ai">
            <span class="msg-ava">AI</span>
            <div class="msg-bubble">{{ m.content }}</div>
          </div>
          <div v-else-if="m.role === 'user'" class="msg me">
            <div class="msg-bubble">{{ m.content }}</div>
            <span class="msg-ava me-ava">我</span>
          </div>
        </template>
        <div v-if="aiLoading" class="msg ai">
          <span class="msg-ava">AI</span>
          <div class="msg-bubble typing"><span class="d1"></span><span class="d2"></span><span class="d3"></span></div>
        </div>
      </div>
      <div class="chat-input">
        <el-input v-model="chatDraft" placeholder="向 AI 追问这份报告，回车发送…"
          :disabled="aiLoading || !chatMsgs.length" @keyup.enter="sendAi" clearable />
        <el-button type="primary" :loading="aiLoading" :disabled="!chatDraft.trim()"
          @click="sendAi">发送</el-button>
      </div>
      <el-alert v-if="aiError" type="warning" :closable="false" :title="aiError"
        style="margin-top:8px" />
    </div>

    <template v-if="report">
      <!-- 返回选择态(演示/历史入口) -->
      <div class="rp-back">
        <el-button size="small" @click="backToSelect">← 换一份报告</el-button>
      </div>

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
            <el-tooltip :disabled="canManage" content="该报告不在运行库，不支持导出"
              placement="top">
              <span>
                <el-button size="small" :loading="exporting" :disabled="!canManage"
                  @click="doExport">
                  <span v-html="dlIcon"></span>&nbsp;导出 HTML 报告</el-button>
              </span>
            </el-tooltip>
            <el-tooltip :disabled="canManage" content="该报告没有对话存档"
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

    <!-- 历史报告(常驻;点击直接切换) -->
    <div class="hist-rpts">
      <div class="hr-head">历史报告</div>
      <div v-if="!histRows.length" class="sl-meta" style="padding:6px 2px">暂无历史报告</div>
      <div v-else class="glass hist">
        <div class="hrow" v-for="r in histRows" :key="r.run_id">
          <span class="hname">{{ friendlyName(r) }}
            {{ r.run_id === store.viewedRunId ? '（当前查看）' : '' }}</span>
          <span class="sl-meta">{{ (r.created_at || '').slice(5, 16) }}</span>
          <span class="sp"></span>
          <el-button size="small" type="primary"
            :plain="r.run_id !== store.viewedRunId" @click="viewHist(r.run_id)">
            {{ r.run_id === store.viewedRunId ? '重新加载' : '查看' }}</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { icon, zhCat } from '../icons.js'
import { api } from '../api.js'
import { useStore } from '../store.js'

const store = useStore()
const secIcon = icon('doc', 16)
const dlIcon = icon('download', 13)
const docIcon = icon('doc', 13)

// ---- 演示报告(空态展示;仅收录带独立评审标签、报告有效的真实运行,零 GPU 秒级载入)
const loading = ref('')
const demos = [
  { id: 'stage1b_r_4060', badge: '对比检测', tone: 'tone-blue',
    t: '标准 vs 智能引导 · 全量 100 场景',
    rate: '38%', risk: '38', total: '100', rateCls: 'red',
    d: '两支并行对比引导是否有效,JBB-100 全量任务集,含完整轨迹与对比结论',
    meta: '英文基准 · 100 场景 · 5 轮' },
  { id: 'run-e700e52186', badge: '黑盒 API', tone: 'tone-rose',
    t: 'DeepSeek 标准检测 · 3 场景',
    rate: '67%', risk: '2', total: '3', rateCls: 'red',
    d: '在线 API 黑盒目标的真实运行:3 个场景中 2 个被独立评审确认存在风险响应',
    meta: '中文场景 · 3 场景 · 标准模式' },
  { id: 'run-8d1aa38232', badge: '黑盒 API', tone: 'tone-green',
    t: 'DeepSeek 引导检测 · 3 场景',
    rate: '0%', risk: '0', total: '3', rateCls: 'green',
    d: '智能引导模式下的在线检测样例:3 个合规域场景全部抵御',
    meta: '中文场景 · 3 场景 · 引导模式' },
]

async function loadDemo(id) {
  loading.value = id
  try {
    await api.replay(id)
    await store.viewRun(id)
    ElMessage.success('已载入示例报告')
  } catch (e) { ElMessage.error('载入失败：' + e) }
  loading.value = ''
}

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

// ---- 返回选择态 / 历史报告
function backToSelect() { store.clearViewed() }

// ---- AI 分析(本地 Qwen3-4B;只解读不裁决)
// ---- AI 对话式分析(本地 Qwen3-4B;只解读不裁决)
const chatMsgs = ref([])      // [{role:'assistant'|'user', content}]
const chatDraft = ref('')
const aiLoading = ref(false)
const aiError = ref('')
const chatBox = ref(null)
const scrollChat = () => setTimeout(() => {
  const el = chatBox.value
  if (el) el.scrollTop = el.scrollHeight
}, 80)
async function loadAiCache() {
  chatMsgs.value = []; chatDraft.value = ''; aiError.value = ''
  const id = store.viewedRunId
  if (!id) return
  try {
    const r = await api.getAnalysis(id)
    if (r.available && Array.isArray(r.messages)) {
      chatMsgs.value = r.messages.filter(m => m.role === 'user' || m.role === 'assistant')
      scrollChat()
    }
  } catch (e) { /* 无缓存静默 */ }
}
async function genAi(message = '') {
  let id = store.viewedRunId
  if (!id && !message) {          // 空态点"生成":自动载入默认演示再分析
    try { await loadDemo(demos[0].id) } catch (e) { ElMessage.error('载入失败：' + e) }
    id = store.viewedRunId
  }
  if (!id || aiLoading.value) return
  aiLoading.value = true; aiError.value = ''
  if (message) chatMsgs.value.push({ role: 'user', content: message })
  chatDraft.value = ''
  scrollChat()
  try {
    const r = await api.analyzeReport(id, message)
    chatMsgs.value = (r.messages || []).filter(m => m.role === 'user' || m.role === 'assistant')
  } catch (e) {
    aiError.value = 'AI 分析失败：' + e
    if (message) chatMsgs.value.pop()   // 失败回滚本轮用户消息
  }
  aiLoading.value = false
  scrollChat()
}
const sendAi = () => {
  const t = chatDraft.value.trim()
  if (t) genAi(t)
}
async function resetAi() {
  const id = store.viewedRunId
  if (!id || aiLoading.value) return
  chatMsgs.value = []; aiError.value = ''
  aiLoading.value = true
  try {
    const r = await api.analyzeReport(id, '', true)
    chatMsgs.value = (r.messages || []).filter(m => m.role === 'user' || m.role === 'assistant')
  } catch (e) { aiError.value = 'AI 分析失败：' + e }
  aiLoading.value = false
  scrollChat()
}
watch(() => store.viewedRunId, loadAiCache, { immediate: true })
const modeZh = (m) => ({ standard: '标准', guided: '引导', compare: '对比' }[m] || m || '')
const targetZh = (t) => {
  if (!t || /phi/i.test(t)) return '本地模型'
  if (/deepseek/i.test(t)) return 'DeepSeek'
  return t
}
function friendlyName(r) {
  const parts = [modeZh(r.mode) + '检测', targetZh(r.target)]
  if (r.n_tasks) parts.push(r.n_tasks + ' 场景')
  return parts.filter(Boolean).join(' · ')
}
const histRows = ref([])
async function loadHist() {
  try {
    const rows = await api.listRuns(20)
    histRows.value = rows.filter(r => r.status === 'COMPLETED')
  } catch (e) { /* 服务不可达 */ }
}
async function viewHist(id) {
  try { await store.viewRun(id) }
  catch (e) { ElMessage.error('无法加载：' + e) }
}
onMounted(loadHist)
watch(() => store.historyVersion, loadHist)
</script>
