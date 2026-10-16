<template>
  <div>
    <!-- 页头横幅 -->
    <section class="pp-hero">
      <h1>产品介绍</h1>
      <p>SafeLoop 是一个单机部署的大模型安全评估平台：多智能体闭环红队 + 独立评审，
        面向「接入模型、选范围、拿报告」的零门槛使用方式，同时保留全部研究细节。</p>
    </section>

    <!-- 系统架构 -->
    <section class="pp-sec">
      <div class="cap-head">
        <h2>系统架构</h2>
        <p>四阶段闭环：红方生成 → 被测模型回答 → 裁判观察 → 反馈适应；独立评审官永远在闭环之外</p>
      </div>
      <div v-html="hero"></div>
    </section>

    <!-- 角色栈 -->
    <section class="pp-sec">
      <div class="cap-head">
        <h2>智能体角色</h2>
        <p>四个角色分工明确，判别与评审分离是可信性的来源</p>
      </div>
      <div class="role-grid">
        <div class="role-card tone-x" :class="r.tone" v-for="r in roles" :key="r.t">
          <span class="rc-ico" v-html="r.icon"></span>
          <div class="rc-t">{{ r.t }}</div>
          <div class="rc-m">{{ r.model }}</div>
          <div class="rc-d">{{ r.d }}</div>
        </div>
      </div>
    </section>

    <!-- 检测模式 -->
    <section class="pp-sec">
      <div class="cap-head">
        <h2>三种检测模式</h2>
        <p>第 0 轮攻击完全一致（协议不变量），对比公平可信</p>
      </div>
      <div class="mode-grid">
        <div class="mode-card" v-for="m in modes" :key="m.t">
          <div class="mc-t">{{ m.t }}<i v-if="m.lab" class="badge-lab">{{ m.lab }}</i></div>
          <div class="mc-d">{{ m.d }}</div>
        </div>
      </div>
    </section>

    <!-- 安全设计 -->
    <section class="pp-sec">
      <div class="cap-head">
        <h2>安全与可信设计</h2>
        <p>四条工程红线，任何提交不得违背</p>
      </div>
      <div class="rule-list">
        <div class="rule" v-for="(r, i) in rules" :key="i">
          <span class="ru-n">{{ i + 1 }}</span>
          <div class="ru-t">{{ r[0] }}</div>
          <div class="ru-d">{{ r[1] }}</div>
        </div>
      </div>
    </section>

    <!-- v1.1 智能能力 -->
    <section class="pp-sec">
      <div class="cap-head">
        <h2>智能能力（默认关闭，独立模式）</h2>
        <p>长期记忆与智能预算不改变标准模式语义，开启后全程可视化</p>
      </div>
      <div class="mode-grid">
        <div class="mode-card">
          <div class="mc-t">长期攻击记忆</div>
          <div class="mc-d">按目标指纹命名空间隔离，跨运行积累成功与失败经验，
            第 1 轮起生效以保护第 0 轮协议一致性；支持冻结快照。</div>
        </div>
        <div class="mode-card">
          <div class="mc-t">智能预算调度</div>
          <div class="mc-d">两阶段任务选择：先全任务基础覆盖，再按风险类别覆盖缺口追加；
            调度不以发现风险为唯一目标，覆盖与成本同权重。</div>
        </div>
      </div>
    </section>

    <section class="cta-band">
      <div class="cta-in">
        <div>
          <div class="cb-t">在真实模型上试一次</div>
          <div class="cb-d">本地模型或在线 API 均可，快速检测 3 场景约 10 分钟</div>
        </div>
        <a class="btn-main" href="#/workbench">进入工作台</a>
      </div>
    </section>
  </div>
</template>

<script setup>
import hero from '../assets/hero.html?raw'
import { icon } from '../icons.js'

const roles = [
  { t: '红方测试员', model: 'Qwen3-1.7B', tone: 'tone-rose', d: '设计并逐轮调整测试问题，输出结构化攻击动作；只收到判别器的策略维度提示，不收到攻击文本。',
    icon: icon('play', 18, 'stroke:#e5484d') },
  { t: '被测大模型', model: '本地模型 / 在线 API', tone: 'tone-purple', d: '被评估对象。本地支持 NF4 量化单卡部署，在线支持 OpenAI 兼容、Anthropic、Responses 三种协议。',
    icon: icon('target', 18, 'stroke:#7c5cfc') },
  { t: '安全判别', model: 'Qwen3Guard-0.6B', tone: 'tone-orange', d: '内容安全与目标推进双视角逐轮观察，多维输出带字段级来源标注，缺数据为空不伪造。',
    icon: icon('pulse', 18, 'stroke:#d97706') },
  { t: '独立评审官', model: 'StrongREJECT-2B', tone: 'tone-green', d: '闭环之外，只在测试结束后依据原始目标与模型回答做最终裁决——风险结论的唯一口径。',
    icon: icon('shield', 18, 'stroke:#12a150') },
]

const modes = [
  { t: '标准检测', d: '红方自主多轮测试，判别器全程只观察不干预；适合首次使用与基线评估。' },
  { t: '智能引导', lab: '实验', d: '安全判别信号参与下一轮策略引导（保持/调整/更换），探索更深的多轮风险。' },
  { t: '对比检测', d: '标准与引导两支并行，同一任务集与预算，报告直接对比引导是否有效。' },
]

const rules = [
  ['判别信号 ≠ 评估结论', '独立评审永不回传同次评估的记忆与调度回路，过程观察不冒充最终结论。'],
  ['协议冻结', '已验证的判别与控制协议不改；标准模式语义冻结，新能力一律独立模式。'],
  ['调度多目标', '覆盖、有效发现、成本、可信度同权重，不以风险发现率为唯一目标。'],
  ['凭据永不落盘', '模型密钥只经环境变量，请求、日志、报告与记忆库中只出现变量名。'],
]
</script>
