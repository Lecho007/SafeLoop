<template>
  <div>
    <!-- Hero(智谱式:深蓝黑渐变+光斑+网格,通栏;底部带快捷入口卡排) -->
    <section class="hero">
      <div class="hero-in">
        <div class="hero-tag">多智能体闭环安全评估</div>
        <h1>让 AI 智能体<br/>替你测试你的大模型</h1>
        <p class="hero-sub">红方测试员多轮自适应提问 · 安全判别逐轮观察 · 独立评审官最终裁决</p>
        <div class="hero-cta">
          <a class="btn-main" href="#/workbench">开始安全检测 →</a>
          <button class="btn-ghost" :disabled="demoLoading" @click="loadDemo">
            {{ demoLoading ? '载入中…' : '查看演示报告' }}</button>
        </div>
      </div>
      <!-- 快捷入口卡排(智谱 Hero 模型入口卡) -->
      <div class="hero-quick">
        <a v-for="q in quicks" :key="q.t" class="hq-card" :href="q.href">
          <span class="hq-ico" v-html="q.icon"></span>
          <div class="hq-t">{{ q.t }}</div>
          <div class="hq-d">{{ q.d }}</div>
        </a>
      </div>
    </section>

    <!-- 能力矩阵(智谱式 4 列小卡 + 彩色标签) -->
    <section class="cap">
      <div class="cap-head">
        <h2>核心能力</h2>
        <p>从接入到报告的完整闭环，每一环都可追溯 ·
          <a class="cap-more" href="#/product">了解系统架构 →</a></p>
      </div>
      <div class="cap-grid">
        <a v-for="c in caps" :key="c.t" class="cap-card tone-x" :class="c.tone" href="#/workbench">
          <span v-if="c.tag" class="cc-tag" :class="c.tagCls">{{ c.tag }}</span>
          <span class="cc-ico" v-html="c.icon"></span>
          <div class="cc-t">{{ c.t }}</div>
          <div class="cc-d">{{ c.d }}</div>
          <span class="cc-more">了解更多 →</span>
        </a>
      </div>
    </section>

    <!-- 四步流程(浅灰通栏区块,深浅交替) -->
    <section class="band-gray">
      <div class="band-in">
        <div class="cap-head">
          <h2>四步拿到报告</h2>
          <p>全程网页操作，无需任何命令</p>
        </div>
        <div class="step-flow">
          <div class="sf-item" v-for="(s, i) in steps" :key="s.t">
            <div class="sf-n">{{ String(i + 1).padStart(2, '0') }}</div>
            <div class="sf-t">{{ s.t }}</div>
            <div class="sf-d">{{ s.d }}</div>
            <i v-if="i < steps.length - 1" class="sf-ar"></i>
          </div>
        </div>
      </div>
    </section>

    <!-- 数据亮点 -->
    <section class="nums">
      <div class="num-item" v-for="n in nums" :key="n.k">
        <div class="nu-v">{{ n.v }}</div>
        <div class="nu-k">{{ n.k }}</div>
      </div>
    </section>

    <!-- 底部 CTA -->
    <section class="cta-band">
      <div class="cta-in">
        <div>
          <div class="cb-t">准备好开始第一次安全体检了吗？</div>
          <div class="cb-d">快速检测 3 个场景约 10 分钟；运行期间可自由离开，进度不丢</div>
        </div>
        <a class="btn-main" href="#/workbench">进入工作台</a>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { icon } from '../icons.js'
import { api } from '../api.js'
import { useStore } from '../store.js'
import { goto } from '../router.js'

const store = useStore()
const demoLoading = ref(false)

const quicks = [
  { t: '闭环检测', d: '多轮自适应红队', href: '#/workbench',
    icon: icon('play', 17, 'stroke:#8fa3ff') },
  { t: '独立评审', d: '闭环外最终裁决', href: '#/product',
    icon: icon('shield', 17, 'stroke:#34d899') },
  { t: '黑盒接入', d: '三种 API 协议', href: '#/workbench',
    icon: icon('target', 17, 'stroke:#b9a4ff') },
  { t: '一页读懂', d: '结论一键导出', href: '#/docs',
    icon: icon('doc', 17, 'stroke:#ffb86b') },
]

const caps = [
  { t: '多智能体闭环检测', d: '红方逐轮调整攻击策略，判别信号驱动适应，深挖多轮风险',
    tone: 'tone-blue', tag: '核心', tagCls: 'tg-blue',
    icon: icon('play', 18, 'stroke:#4d6bfe') },
  { t: '独立评审官裁决', d: 'StrongREJECT 只依据目标与回答裁决，过程信号不冒充结论',
    tone: 'tone-green', tag: '可信', tagCls: 'tg-green',
    icon: icon('shield', 18, 'stroke:#12a150') },
  { t: '黑盒 API 接入', d: 'OpenAI 兼容 / Anthropic / Responses，测试通过即存预设',
    tone: 'tone-purple', tag: '推荐', tagCls: 'tg-purple',
    icon: icon('target', 18, 'stroke:#7c5cfc') },
  { t: '一页读懂报告', d: 'N 场景 M 风险的直接结论 + 参考等级 + 适用范围',
    tone: 'tone-rose', tag: '', tagCls: '',
    icon: icon('doc', 18, 'stroke:#e5484d') },
  { t: '长期测试记忆', d: '跨运行积累同目标经验，round 1+ 生效，冻结快照防泄漏',
    tone: 'tone-orange', tag: '实验', tagCls: 'tg-orange',
    icon: icon('history', 18, 'stroke:#d97706') },
  { t: '智能预算调度', d: '按风险覆盖缺口分配调用预算，D(Q)/Yield 全程可视化',
    tone: 'tone-teal', tag: '实验', tagCls: 'tg-teal',
    icon: icon('pulse', 18, 'stroke:#0e9f6e') },
  { t: '断点续跑', d: '轮边界优雅取消，检查点无损续跑，历史重启不丢',
    tone: 'tone-blue', tag: '', tagCls: '',
    icon: icon('check', 18, 'stroke:#4d6bfe') },
  { t: '双语题库', d: 'JBB-100 英文基准 + 中文国标五域 108 场景',
    tone: 'tone-purple', tag: '', tagCls: '',
    icon: icon('doc', 18, 'stroke:#7c5cfc') },
]

const steps = [
  { t: '选择被测对象', d: '本地模型开箱即用，或在线 API 填三项并测试连接' },
  { t: '选择方式与范围', d: '模式 / 题库 / 快速·完整·指定场景，轮数与预算实时预估' },
  { t: '运行与实况', d: '终端逐轮展示测试对话，可随时停止，离开进度不丢' },
  { t: '拿到清晰报告', d: '风险发现率与参考等级，一键导出 HTML 与对话存档' },
]

const nums = [
  { v: '208', k: '内置测试场景（中英双题库）' },
  { v: '3', k: '黑盒 API 协议' },
  { v: '4', k: '协同智能体角色' },
  { v: '204+', k: '自动化测试项' },
]

async function loadDemo() {
  demoLoading.value = true
  try {
    await api.replay('stage1b_r_4060')
    await store.viewRun('stage1b_r_4060')
    goto('report')
  } catch (e) { ElMessage.error('载入失败：' + e) }
  demoLoading.value = false
}
</script>
