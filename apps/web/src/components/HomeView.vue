<template>
  <div>
    <!-- Hero(智谱式:深蓝黑渐变 + 光斑 + 网格) -->
    <section class="hero">
      <div class="hero-in">
        <div class="hero-tag">多智能体闭环安全评估</div>
        <h1>让 AI 智能体<br/>替你测试你的大模型</h1>
        <p class="hero-sub">红方测试员多轮自适应提问 · 安全判别逐轮观察 · 独立评审官最终裁决
          <br/>接入本地模型或在线 API，选范围、拿人话报告</p>
        <div class="hero-cta">
          <a class="btn-main" href="#/workbench">开始安全检测 →</a>
          <button class="btn-ghost" :disabled="demoLoading" @click="loadDemo">
            {{ demoLoading ? '载入中…' : '查看演示报告' }}</button>
        </div>
        <div class="hero-loop">
          <span class="hl-chip"><i class="r"></i>红方测试员</span><i class="hl-ar"></i>
          <span class="hl-chip"><i class="p"></i>被测大模型</span><i class="hl-ar"></i>
          <span class="hl-chip"><i class="a"></i>安全判别</span>
          <i class="hl-back"></i><span class="hl-note">反馈适应 · 多轮闭环</span>
          <i class="hl-ar green"></i>
          <span class="hl-chip"><i class="g"></i>独立评审官</span>
        </div>
      </div>
    </section>

    <!-- 能力卡片(白区,智谱式网格) -->
    <section class="cap">
      <div class="cap-head">
        <h2>核心能力</h2>
        <p>从接入到报告的完整闭环，每一环都可追溯 ·
          <a class="cap-more" href="#/product">了解系统架构 →</a></p>
      </div>
      <div class="cap-grid">
        <a v-for="c in caps" :key="c.t" class="cap-card tone-x" :class="c.tone" href="#/workbench">
          <span class="cc-ico" v-html="c.icon"></span>
          <div class="cc-t">{{ c.t }}</div>
          <div class="cc-d">{{ c.d }}</div>
        </a>
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

const caps = [
  { t: '多智能体闭环检测', d: '红方测试员逐轮调整攻击策略，判别信号驱动适应，深挖多轮才暴露的风险',
    tone: 'tone-blue', icon: icon('play', 18, 'stroke:#4d6bfe') },
  { t: '独立评审官裁决', d: '闭环之外的 StrongREJECT 只依据原始目标与回答做最终裁决，过程信号不冒充结论',
    tone: 'tone-green', icon: icon('shield', 18, 'stroke:#12a150') },
  { t: '黑盒 API 接入', d: 'OpenAI 兼容 / Anthropic / Responses 三协议，连接测试通过即存预设，密钥只经环境变量',
    tone: 'tone-purple', icon: icon('target', 18, 'stroke:#7c5cfc') },
  { t: '人话评估报告', d: 'N 个场景 M 个风险的直接结论 + 参考等级 + 适用范围，一键导出打印就绪 HTML',
    tone: 'tone-rose', icon: icon('doc', 18, 'stroke:#e5484d') },
  { t: '长期记忆与智能预算', d: '跨 run 积累同目标测试经验，调度器按风险覆盖分配调用预算，全程可视化',
    tone: 'tone-orange', icon: icon('history', 18, 'stroke:#d97706') },
  { t: '断点续跑 · 历史不丢', d: '轮边界优雅取消，检查点无损续跑，SQLite 历史重启不丢，含导入的旧运行',
    tone: 'tone-teal', icon: icon('check', 18, 'stroke:#0e9f6e') },
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
