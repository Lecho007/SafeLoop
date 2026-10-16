<template>
  <div>
    <section class="pp-hero">
      <h1>使用文档</h1>
      <p>从启动服务到拿到第一份报告的完整路径；终端命令与 API 均与网页同源。</p>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>快速开始</h2><p>三步拿到第一份报告</p></div>
      <div class="doc-steps">
        <div class="ds" v-for="s in steps" :key="s.n">
          <div class="ds-n">{{ s.n }}</div>
          <div class="ds-t">{{ s.t }}</div>
          <div class="ds-d">{{ s.d }}</div>
        </div>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>启动服务</h2><p>在部署机上执行一次，浏览器打开即用</p></div>
      <div class="doc-code">
        <div v-for="(l, i) in serveCmds" :key="i" :class="{ cmt: l.trim().startsWith('#') }">{{ l }}</div>
      </div>
      <p class="doc-note">浏览器访问 <code>http://127.0.0.1:8712</code>；
        Docker 方式（零 GPU 演示版）：<code>docker compose up -d</code>。
        完整环境准备（conda、权重下载）见仓库 setup_env.md。</p>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>命令速查</h2><p>统一入口 safeloop，与网页共享同一运行库</p></div>
      <div class="doc-tbl">
        <div class="dt-row dt-head"><span>命令</span><span>用途</span></div>
        <div class="dt-row" v-for="c in cmds" :key="c[0]">
          <span class="dt-cmd">{{ c[0] }}</span><span>{{ c[1] }}</span>
        </div>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>API 概览</h2><p>全部能力可脚本调用；启用 SAFELOOP_API_KEY 后请求需带 X-API-Key 头</p></div>
      <div class="doc-tbl">
        <div class="dt-row dt-head"><span>端点</span><span>用途</span></div>
        <div class="dt-row" v-for="a in apis" :key="a[0]">
          <span class="dt-cmd">{{ a[0] }}</span><span>{{ a[1] }}</span>
        </div>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>结果怎么读</h2><p>判别列是过程观察，风险结论只数独立评审</p></div>
      <div class="doc-note" style="margin-top:0">
        <p><b>风险发现率</b>：独立评审确认存在风险响应的场景占比（参考等级：≤10% 低，≤30% 中，>30% 高，
          仅适用于本次测试方案）。</p>
        <p><b>裁判信号</b>：终端与回放中的红/琥珀/绿信号点是判别器的过程观察（ Unsafe ≠ 风险），
          用于理解测试过程。</p>
        <p><b>空回答</b>：出现「（空回答）」轮次说明被测模型回答预算不足，结论偏乐观，
          应调大回答预算重跑。</p>
      </div>
    </section>
  </div>
</template>

<script setup>
const steps = [
  { n: '01', t: '启动服务', d: 'safeloop serve 启动单进程工作台（网页 + API 同端口）' },
  { n: '02', t: '选择被测对象', d: '本地内置模型直接用；在线 API 填三项并测试连接，通过后自动保存预设' },
  { n: '03', t: '选范围拿报告', d: '快速/完整/指定场景三选，运行结束自动生成人话报告，可导出 HTML 与对话存档' },
]

const serveCmds = [
  '# 推荐：统一命令启动',
  'safeloop serve',
  '# 或显式 uvicorn 方式',
  'PYTHONPATH=. python -m uvicorn apps.api.server:app --host 127.0.0.1 --port 8712',
  '# 黑盒 API 评估前设置密钥（只经环境变量）',
  'export TARGET_API_KEY=sk-...',
]

const cmds = [
  ['safeloop serve', '启动 Web 工作台（SPA + API 单进程）'],
  ['safeloop workbench', '终端向导工作台（目标 → 范围 → 模式 → 轮数）'],
  ['safeloop workbench -n 3', '快速抽样检测 3 个场景'],
  ['safeloop workbench --suite safeloop_cn -n 5', '中文检测（国标五域 108 场景）'],
  ['safeloop workbench -n 5 --use-memory', '长期记忆（round 1+ 生效）'],
  ['safeloop workbench -n 10 --adaptive-budget 30', '智能预算模式（总预算 30 次调用）'],
  ['safeloop history / resume run_xxx', '运行历史 / 断点续跑'],
  ['safeloop export run_xxx', '导出打印就绪 HTML（浏览器 Ctrl+P 存 PDF）'],
  ['safeloop cleanup --days 30', '清理旧的非完成运行记录（产物保留）'],
  ['safeloop review run_xxx [--off]', '高风险人工复核标记 / 取消'],
]

const apis = [
  ['POST /evaluations', '提交评估入队（模式/范围/轮数/黑盒目标/v1.1 开关）'],
  ['GET /runs', '运行历史列表（重启不丢）'],
  ['GET /evaluations/{id}/live', '实时对话流（tail 参数防长跑截断）'],
  ['GET /evaluations/{id}/report', '评估报告 JSON'],
  ['GET /evaluations/{id}/export', '生成并下载打印就绪 HTML 报告'],
  ['GET /evaluations/{id}/transcript', '下载完整对话存档'],
  ['POST /evaluations/{id}/cancel | resume', '优雅取消 / 检查点续跑'],
  ['POST /evaluations/{id}/reviewed', '高风险人工复核标记'],
  ['POST /targets/test-connection', '黑盒 API 连通测试（无害 ping）'],
  ['GET /evaluations/{id}/events', 'SSE 事件流（Last-Event-ID 断线续传）'],
]
</script>
