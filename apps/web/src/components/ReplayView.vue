<template>
  <div>
    <div class="sl-sec" v-html="secIcon + '　证据链回放' + (isDemo ? demoTag : '')"></div>

    <template v-if="isDemo">
      <div class="card" style="padding:16px 22px;margin-bottom:12px">
        <b>测试目标（全程固定不变）</b><br>{{ demo.goal }}</div>
      <RunTerminal right="演示数据 · 非本次检测">
        <template #head><span class="dot"></span>DEMO · {{ demo.category }} · {{ demo.steps.length }} 轮</template>
        <template v-for="s in demo.steps" :key="s.round">
          <div class="t-round"><span class="sg" :class="s.ok ? 'r' : (s.safety === 'Unsafe' ? 'a' : 'g')"></span>
            {{ demo.task_id }} · {{ stratZh(s.strategy) }} · 内容判定 {{ s.safety }}
             · {{ s.ok ? '风险确认' : '未触发' }}</div>
          <div class="t-q"><div class="t-role">TESTER ▸</div>{{ s.prompt }}</div>
          <div class="t-a"><div class="t-role">TARGET ▸</div>{{ s.response }}</div>
        </template>
      </RunTerminal>
      <div class="card" style="margin-top:14px;padding:18px 22px">
        <b>⚖️ 独立评审官最终裁决</b><br>
        <span :style="{ color: demoVerdict === '风险确认' ? 'var(--risk)' : 'var(--safe)', fontWeight: 700 }">
          {{ demoVerdict }}：{{ demo.steps.length }} 轮测试中{{ demoVerdict === '风险确认' ? '模型至少一次给出风险回答' : '未出现风险回答' }}。</span><br>
        <span class="sl-meta">闭环之外 · 仅依据原始目标与模型回答裁决</span>
      </div>
    </template>

    <template v-else-if="!trajs.length">
      <div class="glass sl-empty" v-html="emptyHtml"></div>
    </template>

    <template v-else>
      <div class="rp-bar">
        <el-select v-model="selIdx" style="max-width:520px" filterable>
          <el-option v-for="(t, i) in showList" :key="t.task_id + t.branch"
            :label="labelOf(t)" :value="i" />
        </el-select>
        <el-segmented v-model="riskyFilter" :options="['全部', '仅风险', '仅抵御']" />
        <span class="sl-meta">共 {{ trajs.length }} 条 · 风险 {{ risky.length }} · 抵御 {{ safe.length }}</span>
      </div>
      <div class="card" style="padding:16px 22px;margin-bottom:12px">
        <b>测试目标（全程固定不变）</b><br>{{ traj.goal }}</div>
      <RunTerminal :right="traj.task_id" :right-title="traj.task_id" legend>
        <template #head><span class="dot"></span>{{ traj.task_id }} · {{ traj.steps.length }} 轮</template>
        <template v-for="s in traj.steps" :key="s.round_id">
          <div class="t-round"><span class="sg" :class="sgOf(s)"></span>R{{ s.round_id + 1 }}
            · {{ stratZh(s.action.strategy) }} · {{ judgeTxt(s) }}</div>
          <div class="t-q"><div class="t-role">TESTER ▸</div>{{ clip(s.action.prompt, 300) }}<a
            v-if="len(s.action.prompt) > 300" class="tx-link"
            @click="full(s.action.prompt, 'TESTER 提问全文 · ' + traj.task_id + ' R' + (s.round_id + 1))">全文</a></div>
          <div class="t-a"><div class="t-role">TARGET ▸</div>{{ clip(s.response.text, 420) }}<a
            v-if="len(s.response.text) > 420" class="tx-link"
            @click="full(s.response.text, 'TARGET 回答全文 · ' + traj.task_id + ' R' + (s.round_id + 1))">全文</a></div>
        </template>
      </RunTerminal>
      <div class="card" style="margin-top:14px;padding:18px 22px">
        <b>⚖️ 独立评审官最终裁决</b><br>
        <span :style="{ color: finalOk ? 'var(--risk)' : 'var(--safe)', fontWeight: 700 }">
          {{ finalOk ? '风险确认' : '抵御成功' }}：{{ finalOk
            ? traj.steps.length + ' 轮测试中模型至少一次给出风险回答'
            : '全部 ' + traj.steps.length + ' 轮未出现风险回答' }}。</span><br>
        <span class="sl-meta">闭环之外 · 仅依据原始目标与模型回答裁决</span>
      </div>
      <TextDialog ref="txDlg" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { icon, zhCat } from '../icons.js'
import { useStore } from '../store.js'
import { DEMO } from '../demo.js'
import RunTerminal from './RunTerminal.vue'
import TextDialog from './TextDialog.vue'

const store = useStore()
const secIcon = icon('doc', 16)
const demoTag = "　<span class='sl-pill'>演示数据</span>"
const demo = DEMO
const txDlg = ref(null)
const emptyHtml = icon('doc', 30, 'stroke:#9db0c9') +
  `<div class='t'>暂无轨迹数据</div><div class='h'>完成一次检测（或在总览页载入示例数据）后，` +
  `<br>这里逐轮展示红方提问、模型回答与最终裁决。</div>`

const isDemo = computed(() => !store.viewedRunId)
const trajs = computed(() => store.viewedTrajs || [])

const risky = computed(() => trajs.value.filter(t => t.steps.some(ok)))
const safe = computed(() => trajs.value.filter(t => !t.steps.some(ok)))
const riskyFilter = ref('全部')
// 全部列出（此前只显示风险 9 + 抵御 3，完整检测时大部分场景无入口）
const showList = computed(() => {
  if (riskyFilter.value === '仅风险') return risky.value
  if (riskyFilter.value === '仅抵御') return safe.value
  return [...risky.value, ...safe.value]
})
const selIdx = ref(0)
watch(showList, l => { if (selIdx.value >= l.length) selIdx.value = 0 })

const traj = computed(() => showList.value[selIdx.value] || { task_id: '', goal: '', steps: [] })
const ok = (s) => !!(s.external_evaluation && s.external_evaluation.success)
const finalOk = computed(() => traj.value.steps.some(ok))
const labelOf = (t) => {
  const first = t.steps.findIndex(ok) + 1
  return `${t.task_id} · ${zhCat(t.category || '')}（${
    first ? `第${first}轮触发` : '未触发'}）`
}
const stratZh = (s) => ({ direct: '直接提问', roleplay: '角色扮演', reframing: '换角度提问',
  obfuscation: '混淆表述', multi_turn: '分步引导' }[s] || s || '?')
const judgeTxt = (s) => {
  const m = (s.judge_output && s.judge_output.metadata) || {}
  return m.advancement ? `目标推进 ${m.advancement}`
    : m.safety ? `内容判定 ${m.safety}` : '已记录'
}
const sgOf = (s) => ok(s) ? 'r'
  : ((((s.judge_output || {}).metadata || {}).safety === 'Unsafe')
    || (((s.judge_output || {}).metadata || {}).advancement === 'PARTIAL')) ? 'a' : 'g'
const len = (t) => String(t ?? '').length
const clip = (t, n) => { t = String(t ?? ''); return t.length <= n ? t : t.slice(0, n) + '…' }
const full = (t, title) => txDlg.value?.open(t, title)
const demoVerdict = computed(() =>
  demo.steps.some(s => s.ok) ? '风险确认' : '抵御成功')
</script>

<style scoped>
.rp-bar { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; margin-bottom: 12px; }
</style>
