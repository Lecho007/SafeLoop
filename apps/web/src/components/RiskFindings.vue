<template>
  <div>
    <div class="sl-sec" v-html="secIcon + '　风险发现'"></div>
    <div v-if="!report" class="glass sl-empty" v-html="emptyHtml"></div>
    <template v-else>
      <div class="kpis">
        <div class="glass kpi">
          <div class="v" :class="vClass"><CountNum :value="report.overview.risk_tasks" /><small>/{{ report.overview.total_tasks }}</small></div>
          <div class="c">发现风险场景</div>
        </div>
        <div class="glass kpi">
          <div class="v" :class="vClass"><CountNum v-if="asr != null" :value="asr * 100"
            :format="v => Math.round(v) + '%'" /><template v-else>—</template></div>
          <div class="c">风险发现率（参考等级：{{ grade }}）</div>
        </div>
        <div class="glass kpi">
          <div class="v"><CountNum :value="Number(ul.mean_ctts) || 0"
            :format="v => v.toFixed(1)" /><small> 轮</small></div>
          <div class="c">平均首次触发轮次</div>
        </div>
        <div class="glass kpi">
          <div class="v">{{ stars }}</div>
          <div class="c">探索效率 AUC-B {{ ul.auc_b ?? '—' }}</div>
        </div>
      </div>
      <el-alert v-if="turning > 0" type="info" :closable="false"
        :title="`${turning} 个场景首轮表现安全，多轮测试后才暴露风险——这正是多轮体检的价值。`" />
      <template v-if="distItems.length">
        <div class="sl-sec" style="font-size:15px" v-html="barIcon + '　风险类别分布'"></div>
        <div class="glass" style="padding:14px 22px">
          <div class="bar-row" v-for="(d, i) in distItems" :key="d.k">
            <div class="bar-name">{{ d.k }}</div>
            <div class="bar" :style="{ width: d.w + 'px', background: colors[i % colors.length] }"></div>
            <div class="bar-n">{{ d.v }}</div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { icon, zhCat } from '../icons.js'
import CountNum from './CountNum.vue'

const props = defineProps({ report: Object, poolSteps: Array })

const secIcon = icon('pulse', 16)
const barIcon = icon('alert', 14)
const emptyHtml = icon('pulse', 30, 'stroke:#9db0c9') +
  `<div class='t'>暂无评估数据</div><div class='h'>完成一次检测后，` +
  `这里汇总风险发现比例、首次触发轮次与类别分布。</div>`
const colors = ['#4d6bfe', '#0ea5e9', '#14b8a6', '#12a150', '#65a30d',
  '#d97706', '#ea8a2b', '#e5484d', '#a855f7', '#6366f1']

const ul = computed(() => (props.report?.metrics?.user_layer) || {})
const asr = computed(() => ul.value.asr_at_budget ?? null)
const grade = computed(() => {
  const a = asr.value
  if (a == null) return '未定'
  if (a <= 0.10) return '低'
  if (a <= 0.30) return '中'
  return '高'
})
const vClass = computed(() => {
  const a = asr.value
  if (a == null) return ''
  if (a > 0.30) return 'red'
  if (a > 0.10) return 'amber'
  return 'green'
})
const stars = computed(() => {
  const auc = ul.value.auc_b
  if (auc == null) return '—'
  const n = Math.max(1, Math.min(5, Math.ceil(auc / 0.4 * 5)))
  return '★'.repeat(n) + '☆'.repeat(5 - n)
})
const distItems = computed(() => {
  const dist = props.report?.risk_distribution || {}
  const max = Math.max(...Object.values(dist), 1)
  return Object.entries(dist).sort((a, b) => b[1] - a[1])
    .map(([k, v]) => ({ k: zhCat(k), v, w: Math.max(14, Math.trunc(v / max * 230)) }))
})
const turning = computed(() => (props.poolSteps || []).filter(t =>
  t.steps?.length && !ok(t.steps[0]) && t.steps.some(ok)).length)
const ok = (s) => !!(s.external_evaluation && s.external_evaluation.success)
</script>
