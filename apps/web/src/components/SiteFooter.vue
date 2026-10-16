<template>
  <footer class="site-ft">
    <div class="ft-in">
      <div class="ft-brand">
        <div class="ft-logo" v-html="logoIcon"></div>
        <div class="ft-bt">SafeLoop <i>安全评估平台</i></div>
        <div class="ft-desc">多智能体闭环红队 + 独立评审<br/>让 AI 智能体替你测试你的大模型</div>
      </div>
      <div class="ft-col" v-for="c in cols" :key="c.t">
        <div class="ft-t">{{ c.t }}</div>
        <a v-for="l in c.links" :key="l[0]" :href="l[1]">{{ l[0] }}</a>
      </div>
    </div>
    <div class="ft-bottom">
      <span>© 2026 SafeLoop · 大模型安全评估平台 · 仅供授权安全测试使用</span>
      <span>凭据只经环境变量 · 判别信号不冒充结论</span>
    </div>
  </footer>
</template>

<script setup>
// 智谱式深色多栏页脚(全站通栏)
import { icon } from '../icons.js'
const logoIcon = icon('shield', 18, 'stroke:#ffffff')

const cols = [
  { t: '产品', links: [['产品介绍', '#/product'], ['检测工作台', '#/workbench'], ['轨迹回放', '#/replay'], ['评估报告', '#/report']] },
  { t: '资源', links: [['使用文档', '#/docs'], ['示例报告', '#/report'], ['命令行 CLI', '#/docs'], ['系统架构', '#/product']] },
  { t: '能力', links: [['黑盒 API 接入', '#/docs'], ['长期记忆与预算', '#/product'], ['断点续跑', '#/docs'], ['双语题库', '#/workbench']] },
  { t: '关于', links: [['版本 v1.1', '#/home'], ['工程红线', '#/product'], ['独立评审机制', '#/product'], ['更新记录', '#/home']] },
]
</script>
