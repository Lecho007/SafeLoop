<template>
  <div>
    <!-- 系统架构 -->
    <el-collapse v-model="archOpen" class="glass arch">
      <el-collapse-item name="arch" title="系统架构">
        <div class="sl-meta" style="margin-bottom:8px">
          四阶段闭环：红方生成 → 被测模型回答 → 裁判观察 → 反馈适应；
          独立评审官永远在闭环之外，只在结束后做最终裁决。
        </div>
        <div v-html="hero"></div>
      </el-collapse-item>
    </el-collapse>

    <!-- 双卡表单 -->
    <div class="grid2">
      <div class="glass form-card">
        <h3 v-html="cpuIcon + '　检测对象'"></h3>
        <el-segmented v-model="wizard.target" :options="['本地模型', '在线 API 模型']" block />
        <div class="sl-hint" v-if="wizard.target === '本地模型'">
          已内置 Phi-3.5-mini · 无需配置</div>
        <div class="sl-hint" v-else>填三项接入任意模型 · 密钥只经环境变量，不存盘</div>

        <template v-if="wizard.target === '本地模型'">
          <div class="sl-meta" style="line-height:2.15">
            <div v-html="ic('cpu', 13, 'stroke:#4d6bfe') + ' 被测模型　Phi-3.5-mini（NF4 量化）'"></div>
            <div v-html="ic('play', 11, 'stroke:#7c5cfc') + ' 红方测试员　Qwen3-1.7B'"></div>
            <div v-html="ic('pulse', 13, 'stroke:#d97706') + ' 裁判　Qwen3Guard · 仅观察'"></div>
            <div v-html="ic('shield', 13, 'stroke:#12a150') + ' 独立评审　StrongREJECT · 闭环之外'"></div>
          </div>
        </template>
        <template v-else>
          <div v-if="savedTargets.length" style="margin-bottom:2px">
            <div class="lbl">已保存的模型接口（本机浏览器，不含密钥）</div>
            <el-select v-model="savedIdx" size="default" clearable
              placeholder="选择已保存的接口快速填充" @change="applySaved">
              <el-option v-for="(s, i) in savedTargets" :key="i"
                :label="s.model + ' ｜ ' + s.base_url" :value="i" />
            </el-select>
          </div>
          <div class="lbl">接口协议</div>
          <el-select v-model="wizard.provider" size="default">
            <el-option label="OpenAI 兼容（chat/completions）" value="openai_chat" />
            <el-option label="Anthropic Claude（messages）" value="anthropic" />
            <el-option label="OpenAI 新接口（responses）" value="openai_responses" />
          </el-select>
          <div class="lbl">接口地址</div>
          <el-input v-model="wizard.baseUrl" placeholder="https://api.example.com/v1" />
          <div style="display:flex;gap:10px">
            <div style="flex:1.2">
              <div class="lbl">模型名</div>
              <el-input v-model="wizard.model" placeholder="my-model" />
            </div>
            <div style="flex:1">
              <div class="lbl">密钥环境变量名</div>
              <el-input v-model="wizard.keyEnv" placeholder="TARGET_API_KEY" />
            </div>
          </div>
          <el-button style="margin-top:12px" @click="testConn" :loading="connLoading"
            >测试连接</el-button>
          <el-tag v-if="conn && conn.ok" type="success" style="margin-left:10px">
            已连接 {{ conn.model }} · {{ (conn.latency_s || 0).toFixed(2) }}s</el-tag>
          <el-alert v-else-if="conn && !conn.ok" type="error" :closable="false"
            :title="'连接失败：' + (conn.error || '').slice(0, 140)" style="margin-top:8px" />
        </template>
      </div>

      <div class="glass form-card">
        <h3 v-html="targetIcon + '　检测方式与范围'"></h3>
        <el-segmented v-model="wizard.mode" :options="['标准检测', '智能引导', '对比检测']" block />
        <div class="sl-hint">
          <i v-if="wizard.mode === '智能引导'" class="badge-lab">实验</i>{{ modeHint }}</div>

        <el-segmented v-model="wizard.suite" :options="['国际基准 JBB-100', '中文检测']" block />
        <div class="sl-hint">{{ suiteHint }}</div>

        <el-segmented v-model="wizard.scope" :options="['快速检测', '完整检测', '指定场景']" block />
        <div class="sl-hint">{{ scopeHint }}</div>

        <template v-if="wizard.scope === '快速检测'">
          <div class="lbl">场景数量</div>
          <el-slider v-model="wizard.sampleSize" :min="2" :max="20" show-input
            :show-input-controls="false" input-size="small" />
        </template>
        <template v-if="wizard.scope === '指定场景'">
          <div style="display:flex;gap:10px">
            <div style="flex:1">
              <div class="lbl">危害类别</div>
              <el-select v-model="wizard.category" size="default">
                <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
              </el-select>
            </div>
            <div style="flex:1.6">
              <div class="lbl">场景</div>
              <el-select v-model="wizard.scenario" size="default">
                <el-option v-for="it in categoryItems" :key="it.task_id"
                  :label="it.task_id + ' ｜ ' + it.goal.slice(0, 30)" :value="it.task_id" />
              </el-select>
            </div>
          </div>
        </template>

        <div class="lbl">每个场景测试轮数</div>
        <el-slider v-model="wizard.rounds" :min="1" :max="10" show-input
          :show-input-controls="false" input-size="small" />
        <div class="sl-hint" style="margin:2px 0 0">
          调用次数 = 场景数 × 轮数（对比模式翻倍）；红方与裁判为本地推理，不计 API 费用</div>

        <el-collapse class="adv">
          <el-collapse-item title="高级选项">
            <div class="sl-meta" style="margin-bottom:8px">实验能力，默认关闭 · 不影响标准模式语义</div>
            <el-checkbox v-model="wizard.useMemory">
              使用历史测试经验（长期记忆，round 1+ 生效）</el-checkbox>
            <div style="display:flex;align-items:center;gap:10px;margin-top:8px">
              <span class="sl-meta">智能分配检测预算（0=关闭）</span>
              <el-input-number v-model="wizard.adaptiveQ" :min="0" :max="2000" size="small" />
            </div>
          </el-collapse-item>
        </el-collapse>
        <div class="sl-meta" style="margin-top:10px">每场景 {{ wizard.rounds }} 轮 ·
          预计调用 {{ estCalls }} 次 · 约 {{ estRange }}</div>
      </div>
    </div>

    <!-- 行动条 -->
    <div class="glass action">
      <el-button type="primary" size="large" @click="start"
        :loading="submitting" :disabled="store.running">
        <span v-html="ic('play', 13, 'stroke:#fff')"></span>&nbsp;开始安全体检</el-button>
      <el-button size="large" @click="loadDemo">载入示例数据</el-button>
      <span class="est">运行期间可自由浏览本页各区块 · 离开再回来进度不丢</span>
    </div>

    <!-- 轮询失联 / 失败原因 -->
    <el-alert v-if="store.pollError" type="error" :closable="false"
      title="服务暂时不可达：正在自动重试轮询（请确认 uvicorn 服务仍在运行）"
      style="margin:14px 0 0" />
    <el-alert v-else-if="store.lastRun && store.lastRun.status === 'FAILED'" type="error"
      closable @close="store.lastRun = null"
      :title="'检测失败：' + (store.lastRun.error || '未知原因') + '（可在运行历史中续跑）'"
      style="margin:14px 0 0" />

    <!-- 实况（真实运行） / 实况预演（演示） -->
    <template v-if="store.running">
      <div class="sl-sec" v-html="termIcon + '　实况 · ' + runStateZh"></div>
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
        <el-progress :percentage="progressPct" :stroke-width="10" style="flex:1"
          :show-text="false" />
        <span class="sl-meta">对话 {{ store.run?.steps_done ?? 0 }}/{{ store.run?.total_steps || '?' }}
          　已用 {{ elapsed }}</span>
        <el-button v-if="['RUNNING', 'CANCELLING'].includes(store.run?.status)"
          size="small" type="warning" plain @click="stop">停止</el-button>
      </div>
      <!-- v1.1 能力运行态（A5 可视化） -->
      <div v-if="store.activeAdaptiveQ || store.activeUseMemory" class="v11-bar">
        <template v-if="store.activeAdaptiveQ">
          <span class="sl-meta" style="color:var(--live);font-weight:600">智能预算</span>
          <el-progress :percentage="adaptPct" :stroke-width="8" style="flex:1;max-width:280px"
            :show-text="false" color="#7c5cfc" />
          <span class="sl-meta">{{ store.run?.steps_done ?? 0 }}/{{ store.activeAdaptiveQ }} 次调用 · 调度器按风险覆盖分配轮次</span>
        </template>
        <span v-if="store.activeUseMemory" class="sl-meta" style="color:var(--live)">
          ◈ 长期记忆生效中（round 1+ · 复用同目标的历史测试经验）</span>
      </div>
      <RunTerminal :right="'…' + String(store.activeRunId || '').slice(-6)"
        :right-title="store.activeRunId" legend>
        <template #head>
          <span class="dot"></span>{{ store.run?.status || '…' }} · {{ runStateZh }}
          <span>对话 <span class="val">{{ store.run?.steps_done ?? 0 }}</span>/
            <span class="val">{{ store.run?.total_steps || '?' }}</span></span>
        </template>
        <div v-if="!liveEvents.length" style="color:#5f7495;font-family:ui-monospace,Consolas,monospace;font-size:13px">
          $ 等待首轮对话…（排队 / 模型加载中，完成后逐轮显示在此）<span class="cursor"></span></div>
        <template v-for="(e, i) in liveEvents" :key="i">
          <div class="t-round">
            <span class="sg" :class="sgOf(e)"></span>{{ e.branch ? '［' + e.branch + '］' : '' }}R{{ e.round }}
            · {{ e.task_id }} · {{ stratZh(e.strategy) }} · {{ judgeTxt(e) }}<span
            v-if="e.memory_used" class="mem-tag" title="本轮红方检索了历史测试经验">经验</span>
          </div>
          <div class="t-q"><div class="t-role">TESTER ▸</div>{{ clip(e.prompt, 240) }}<a
            v-if="len(e.prompt) > 240" class="tx-link"
            @click="full(e.prompt, 'TESTER 提问全文 · ' + e.task_id + ' R' + e.round)">全文</a></div>
          <div class="t-a"><div class="t-role">TARGET ▸</div>{{ clip(e.response, 340) || '（空回答）' }}<a
            v-if="len(e.response) > 340" class="tx-link"
            @click="full(e.response, 'TARGET 回答全文 · ' + e.task_id + ' R' + e.round)">全文</a></div>
        </template>
      </RunTerminal>
      <div class="sl-sec" v-html="treeIcon + '　决策路径'"></div>
      <DecisionTree :rounds="liveRounds" :progress="liveRounds.length" />
    </template>

    <template v-else>
      <div class="sl-sec" v-html="termIcon + '　实况预演 ' +
        `<span class='term-badge'>DEMO · 演示数据</span>`"></div>
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:10px">
        <el-button size="small" @click="autoplay">{{ autoPlaying ? '播放中…' : '自动播放' }}</el-button>
        <el-slider v-model="demoStep" :min="1" :max="demo.steps.length" style="flex:1" />
        <span class="sl-meta">{{ demoStep }}/{{ demo.steps.length }} 轮</span>
      </div>
      <RunTerminal right="演示数据 · 非本次检测">
        <template #head>
          <span class="dot"></span>DEMO · {{ demo.category }} · {{ demo.steps.length }} 轮
        </template>
        <template v-for="s in demo.steps.slice(0, demoStep)" :key="s.round">
          <div class="t-round"><span class="sg" :class="s.ok ? 'r' : (s.safety === 'Unsafe' ? 'a' : 'g')">
            </span>{{ demo.task_id }} · {{ stratZh(s.strategy) }} · 内容判定 {{ s.safety }}
             · {{ s.ok ? '风险确认' : '未触发' }}</div>
          <div class="t-q"><div class="t-role">TESTER ▸</div>{{ s.prompt }}</div>
          <div class="t-a"><div class="t-role">TARGET ▸</div>{{ s.response }}</div>
        </template>
      </RunTerminal>
      <div class="grid2" style="margin-top:14px;grid-template-columns:1fr 2.3fr">
        <div>
          <div style="font-weight:700;margin-bottom:8px">智能体状态坞</div>
          <div class="card" style="padding:12px 16px">
            <div class="sl-meta" style="line-height:2.3">
              <div v-html="ic('check', 13, 'stroke:#12a150') + ' 主智能体 · 已规划'"></div>
              <div v-html="ic('play', 11, demoStep < demo.steps.length ? 'stroke:#7c5cfc' : 'stroke:#12a150') + ' 红方测试员'"></div>
              <div v-html="ic('pulse', 13, 'stroke:#4d6bfe') + ' 裁判 · 观察中'"></div>
              <div v-html="ic('shield', 13, demoStep === demo.steps.length ? 'stroke:#12a150' : 'stroke:#9db0c9') + ' 独立评审官'"></div>
            </div>
          </div>
        </div>
        <div>
          <div class="sl-sec" v-html="treeIcon + '　决策路径'"></div>
          <DecisionTree :rounds="demoRounds" :progress="demoStep"
            :verdict="demoStep === demo.steps.length ? demoVerdict : null"
            :trigger-round="2" />
        </div>
      </div>
    </template>

    <!-- 风险发现 + 历史 -->
    <RiskFindings :report="viewedReport" :pool-steps="viewedTrajs" />
    <HistoryList ref="hist" :version="historyVersion" :viewed-run-id="store.viewedRunId" />
    <TextDialog ref="txDlg" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import hero from '../assets/hero.html?raw'
import { api } from '../api.js'
import { icon } from '../icons.js'
import { useStore } from '../store.js'
import { DEMO, DEMO_ROUNDS } from '../demo.js'
import { liveEventsToRounds } from '../tree.js'
import RunTerminal from './RunTerminal.vue'
import DecisionTree from './DecisionTree.vue'
import RiskFindings from './RiskFindings.vue'
import HistoryList from './HistoryList.vue'
import TextDialog from './TextDialog.vue'

const store = useStore()
const ic = icon
const cpuIcon = icon('cpu', 16)
const targetIcon = icon('target', 16)
const termIcon = icon('terminal', 15)
const treeIcon = icon('tree', 15)

const archOpen = ref(['arch'])
const demo = DEMO
const demoRounds = DEMO_ROUNDS
const demoStep = ref(demo.steps.length)
const hist = ref(null)
const txDlg = ref(null)

const wizard = reactive({
  target: '本地模型', provider: 'openai_chat', baseUrl: '', model: '', keyEnv: 'TARGET_API_KEY',
  mode: '标准检测', suite: '国际基准 JBB-100', scope: '快速检测',
  sampleSize: 3, rounds: 3, category: '', scenario: '',
  useMemory: false, adaptiveQ: 0,
})
const conn = ref(null)
const connLoading = ref(false)
const submitting = ref(false)
const suiteRows = ref([])
const historyVersion = ref(0)

// ---- 提示行
const modeHint = computed(() => ({
  标准检测: '测试员自主多轮测试，全程记录证据 · 适合首次使用',
  智能引导: '安全判别结果参与下一轮测试策略引导',
  对比检测: '两种模式都跑，报告直接对比引导是否有效 · 用时约 2 倍',
}[wizard.mode] || ''))
const suiteHint = computed(() => wizard.suite === '中文检测'
  ? `JailBench 全量 ${suiteRows.value.length || 108} 场景 · 国标五类风险 · 适合中文模型`
  : '英文原版题库 · 100 场景 · 研究与基准对照')
const scopeHint = computed(() => ({
  快速检测: '跨风险类别均匀抽取 · 下方选择数量',
  完整检测: `全部 ${suiteRows.value.length || 100} 个场景 · 耗时较长，建议先用快速检测验证链路`,
  指定场景: '选一个场景反复多轮 · 深度测试',
}[wizard.scope] || ''))

// ---- 任务集
const suiteName = computed(() => (wizard.suite === '中文检测' ? 'safeloop_cn' : 'jbb100'))
async function loadSuite() {
  try { suiteRows.value = await api.get('/suite?name=' + suiteName.value) } catch (e) { /* 忽略 */ }
}
watch(suiteName, loadSuite)
onMounted(loadSuite)

const categories = computed(() =>
  [...new Set(suiteRows.value.map(r => zhCategory(r.harm_category)))].sort())
const categoryItems = computed(() =>
  suiteRows.value.filter(r => zhCategory(r.harm_category) === wizard.category))

const CAT_ZH = {
  Disinformation: '虚假信息', 'Economic harm': '经济损害', 'Expert advice': '冒充专家',
  'Fraud/Deception': '欺诈骗术', 'Government decision-making': '政务操纵',
  'Harassment/Discrimination': '骚扰歧视', 'Malware/Hacking': '恶意软件与入侵',
  'Physical harm': '人身伤害', Privacy: '隐私侵犯', 'Sexual/Adult content': '成人内容',
}
const zhCategory = (k) => CAT_ZH[String(k || '').replace('JBB:', '')] || k

watch(categories, cs => { if (cs.length && !wizard.category) wizard.category = cs[0] })
watch(categoryItems, items => {
  if (items.length && !items.some(i => i.task_id === wizard.scenario)) {
    wizard.scenario = items[0].task_id
  }
})

// ---- 预估
const nTasks = computed(() => wizard.scope === '指定场景' ? 1
  : wizard.scope === '完整检测' ? (suiteRows.value.length || 100) : wizard.sampleSize)
const estCalls = computed(() =>
  nTasks.value * wizard.rounds * (wizard.mode === '对比检测' ? 2 : 1))
const estRange = computed(() => {
  const lo = estCalls.value * 0.7, hi = estCalls.value * 1.5
  const f = m => m >= 90 ? (m / 60).toFixed(1) + ' 小时' : Math.round(m) + ' 分钟'
  return f(lo) + '-' + f(hi)
})

// ---- 连接测试 / 提交
// 改动接入配置后旧测试结果失效，避免带旧地址提交
watch(() => [wizard.provider, wizard.baseUrl, wizard.model, wizard.keyEnv],
  () => { conn.value = null })

// ---- API 目标配置持久化（P4：保存非敏感配置；只存本机浏览器，密钥永不落盘）
const SAVED_KEY = 'safeloop_api_targets'
const savedTargets = ref([])
const savedIdx = ref(null)
function loadSaved() {
  try { return JSON.parse(localStorage.getItem(SAVED_KEY) || '[]') } catch (e) { return [] }
}
function saveTarget() {
  if (!(wizard.baseUrl.trim() && wizard.model.trim())) return
  const item = { provider: wizard.provider, base_url: wizard.baseUrl.trim(),
    model: wizard.model.trim(), key_env: wizard.keyEnv.trim() }
  const rest = savedTargets.value.filter(s =>
    !(s.base_url === item.base_url && s.model === item.model))
  savedTargets.value = [item, ...rest].slice(0, 6)
  localStorage.setItem(SAVED_KEY, JSON.stringify(savedTargets.value))
}
function applySaved(v) {
  if (v === null || v === '' || v === undefined) return
  const s = savedTargets.value[v]
  if (!s) return
  wizard.provider = s.provider
  wizard.baseUrl = s.base_url
  wizard.model = s.model
  wizard.keyEnv = s.key_env || 'TARGET_API_KEY'
}

async function testConn() {
  connLoading.value = true
  try {
    conn.value = await api.testConnection({
      provider: wizard.provider, base_url: wizard.baseUrl.trim(),
      model: wizard.model.trim(), api_key_env: wizard.keyEnv.trim(),
    })
    if (conn.value?.ok) saveTarget()   // 验证通过才值得记住
  } catch (e) { conn.value = { ok: false, error: String(e) } }
  connLoading.value = false
}

async function start() {
  if (store.running) {
    ElMessage.warning('已有检测在进行，请等待完成或先停止')
    return
  }
  let apiTarget = null
  if (wizard.target !== '本地模型') {
    if (!conn.value?.ok) {
      ElMessage.warning('请先完成测试连接，再开始 API 模型检测')
      return
    }
    apiTarget = { provider: wizard.provider, base_url: wizard.baseUrl.trim(),
      model: wizard.model.trim(), api_key_env: wizard.keyEnv.trim() }
  }
  const scope = { 快速检测: 'sample', 完整检测: 'full', 指定场景: 'single' }[wizard.scope]
  const spec = {
    mode: { 标准检测: 'standard', 智能引导: 'guided', 对比检测: 'compare' }[wizard.mode],
    scope, scenario_ids: scope === 'single' ? [wizard.scenario].filter(Boolean) : null,
    rounds: wizard.rounds, sample_size: wizard.sampleSize,
    suite: suiteName.value,
    question: apiTarget ? `检测 API 模型 ${apiTarget.model} 的安全风险`
      : '检测本地模型 Phi-3.5 的安全风险',
    target_model: apiTarget ? apiTarget.model : 'phi-3.5-mini',
    api_target: apiTarget, save_transcript: true,
  }
  if (wizard.useMemory || wizard.adaptiveQ > 0) {
    // v1.1 实验能力经兼容字段透传（RunSpec 扩展字段）
    spec.use_memory = wizard.useMemory
    spec.adaptive_budget = wizard.adaptiveQ || null
  }
  submitting.value = true
  try {
    const id = await store.submitRun(spec)
    ElMessage.success('已加入队列：' + id + ' —— 运行期间可继续浏览')
  } catch (e) { ElMessage.error('提交失败：' + e) }
  submitting.value = false
}
async function stop() {
  try {
    await store.cancelActive()
    ElMessage({ message: '已请求取消：当前调用结束或超时后生效，已完成结果保留', type: 'warning' })
  } catch (e) { ElMessage.error('取消请求失败：' + e) }
  historyVersion.value++
}
async function loadDemo() {
  try {
    await api.replay('stage1b_r_4060')
    await store.viewRun('stage1b_r_4060')
    ElMessage.success('已载入示例报告（演示数据，非本次检测）')
  } catch (e) { ElMessage.error('载入失败：' + e) }
}

// ---- 演示自动播放（防重入：播放中不叠加定时器）
let demoTimer = null
const autoPlaying = ref(false)
function autoplay() {
  if (demoTimer) return
  demoStep.value = 1
  autoPlaying.value = true
  demoTimer = setInterval(() => {
    if (demoStep.value >= demo.steps.length) {
      clearInterval(demoTimer)
      demoTimer = null
      autoPlaying.value = false
    } else demoStep.value++
  }, 900)
}

// ---- 实况
const liveEvents = computed(() => store.live?.events || [])
const liveRounds = computed(() => liveEventsToRounds(liveEvents.value))
const progressPct = computed(() => Math.min(100,
  Math.round(((store.run?.steps_done || 0) / Math.max(1, store.run?.total_steps || 1)) * 100)))
const adaptPct = computed(() => Math.min(100,
  Math.round(((store.run?.steps_done || 0) / Math.max(1, store.activeAdaptiveQ || 1)) * 100)))
const runStateZh = computed(() => ({
  QUEUED: '排队中（单 GPU 串行队列）', RUNNING: '多轮对话测试',
  CANCELLING: '正在停止（当前调用结束后生效）', EVALUATING: '独立评审',
  ANALYZING: '分析', REPORTING: '生成报告',
}[store.run?.status] || store.run?.status || ''))
// 每秒 tick 驱动「已用时间」（此前 computed 依赖 Date.now() 会冻结）
const nowTick = ref(Date.now())
let tickTimer = null
onMounted(() => {
  tickTimer = setInterval(() => { nowTick.value = Date.now() }, 1000)
  if (store.activeRunId && !store.timer) store.startPolling()
  // 恢复上次保存的 API 目标配置（非敏感四项）
  savedTargets.value = loadSaved()
  if (savedTargets.value[0] && !wizard.baseUrl) {
    applySaved(0)
    savedIdx.value = 0
  }
})
onUnmounted(() => {
  clearInterval(tickTimer)
  if (demoTimer) clearInterval(demoTimer)
})
const elapsed = computed(() => {
  const sec = Math.max(0, (nowTick.value - (store.runT0 || nowTick.value)) / 1000)
  return String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(Math.floor(sec % 60)).padStart(2, '0')
})
const sgOf = (e) => e.success ? 'r' : (e.advancement === 'PARTIAL' || e.safety === 'Unsafe' ? 'a' : 'g')
const judgeTxt = (e) => e.advancement ? `目标推进 ${e.advancement}`
  : e.safety ? `内容判定 ${e.safety}` : '已记录'
const stratZh = (s) => ({ direct: '直接提问', roleplay: '角色扮演', reframing: '换角度提问',
  obfuscation: '混淆表述', multi_turn: '分步引导' }[s] || s || '?')
const len = (t) => String(t ?? '').length
const clip = (t, n) => { t = String(t ?? ''); return t.length <= n ? t : t.slice(0, n) + '…' }
const full = (t, title) => txDlg.value?.open(t, title)
const demoVerdict = computed(() =>
  demo.steps.some(s => s.ok) ? '风险确认' : '抵御成功')

// 完成后刷新历史
watch(() => store.historyVersion, () => { historyVersion.value++; hist.value?.refresh?.() })
const viewedReport = computed(() => store.viewedReport)
const viewedTrajs = computed(() => store.viewedTrajs || [])
</script>

<style scoped>
.grid2 { display: grid; grid-template-columns: 1fr 1.18fr; gap: 16px; margin: 14px 0; }
.arch { padding: 4px 18px; margin-bottom: 14px; }
@media (max-width: 900px) { .grid2 { grid-template-columns: 1fr; } }
</style>
