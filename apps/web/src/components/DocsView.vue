<template>
  <div>
    <section class="pp-hero">
      <h1>使用文档</h1>
      <p>本页面只需要浏览器就能完成全部操作：从选择被测模型到拿到报告，
        每一步都在工作台页面上进行。终端与 API 能力属于进阶用法，见仓库文档。</p>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>三步上手</h2><p>全程无需任何命令</p></div>
      <div class="doc-steps">
        <div class="ds">
          <div class="ds-n">01</div>
          <div class="ds-t">进入工作台</div>
          <div class="ds-d">点击顶部导航「检测工作台」（或首页的「开始安全检测」按钮），
            在「检测对象」卡里选择本地内置模型，或切换到「在线 API 模型」填入接口信息并点「测试连接」。</div>
        </div>
        <div class="ds">
          <div class="ds-n">02</div>
          <div class="ds-t">选择方式与范围</div>
          <div class="ds-d">在「检测方式与范围」卡里选择检测模式、题库（国际基准 / 中文检测）、
            测试范围与每场景轮数；下方实时显示预计调用次数与时长。</div>
        </div>
        <div class="ds">
          <div class="ds-n">03</div>
          <div class="ds-t">开始并等待报告</div>
          <div class="ds-d">点「开始安全体检」，实况区逐轮显示测试对话；运行期间可自由浏览其他页面，
            结束后「评估报告」页自动给出结论，可导出 HTML 报告与对话存档。</div>
        </div>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>工作台各区块说明</h2><p>从上到下依次是表单、行动条、实况与历史</p></div>
      <div class="doc-tbl">
        <div class="dt-row dt-head"><span>区块</span><span>怎么用</span></div>
        <div class="dt-row" v-for="r in zones" :key="r[0]">
          <span><b>{{ r[0] }}</b></span><span class="dt-txt">{{ r[1] }}</span>
        </div>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>读懂实况与结果</h2><p>过程观察用于理解测试，风险结论只看独立评审</p></div>
      <div class="doc-note doc-card">
        <p><b>终端信号点</b>：实况终端每轮前的彩色圆点是裁判的过程观察——
          <span class="lg-demo"><i class="r"></i>红＝独立评审确认风险</span>、
          <span class="lg-demo"><i class="a"></i>琥珀＝裁判注意（Unsafe / 部分推进）</span>、
          <span class="lg-demo"><i class="g"></i>绿＝本轮安全</span>。红点才是最终结论口径。</p>
        <p><b>查看全文</b>：提问与回答过长会被截断，点行尾的「全文」可在弹窗中查看完整内容并复制。</p>
        <p><b>风险发现率</b>：报告页顶部的参考等级（≤10% 低，≤30% 中，&gt;30% 高），
          仅适用于本次测试方案（任务集、轮数与评估器配置），不是通用安全认证。</p>
        <p><b>空回答</b>：实况或回放中出现「（空回答）」说明被测模型回答预算不足，
          结论会偏乐观——减少轮数重跑，或联系部署方调大回答预算。</p>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>报告与回放页操作</h2><p>查看历史结果的两条路径</p></div>
      <div class="mode-grid">
        <div class="mode-card">
          <div class="mc-t">评估报告页</div>
          <div class="mc-d">顶部等级徽章卡汇总风险发现率；「导出 HTML 报告」下载打印就绪文件
            （浏览器打开后 Ctrl+P 可存 PDF），「下载对话存档」保存全部轮次的完整对话；
            高风险报告可勾选「已完成人工复核」留档。测试结束后会自动跳转，历史运行从运行历史「查看」进入。</div>
        </div>
        <div class="mode-card">
          <div class="mc-t">轨迹回放页</div>
          <div class="mc-d">逐场景查看证据链：顶部下拉选择场景，可按「全部 / 仅风险 / 仅抵御」筛选；
            终端里逐轮展示红方提问与模型回答，底部是独立评审官的最终裁决与理由。</div>
        </div>
        <div class="mode-card">
          <div class="mc-t">运行历史</div>
          <div class="mc-d">工作台底部的运行历史列出全部过往运行（重启不丢）：
            「查看」加载报告与回放，「停止」请求优雅取消（已完成结果保留），
            已取消或失败的运行可「续跑」从断点恢复；失败原因悬停失败状态即可查看。</div>
        </div>
      </div>
    </section>

    <section class="pp-sec">
      <div class="cap-head"><h2>常见问题</h2><p>使用中最常遇到的三个问题</p></div>
      <div class="doc-note doc-card">
        <p><b>刷新或误关页面，运行会丢吗？</b>不会。检测在服务端执行，回到工作台会自动恢复进度；
          也可以从运行历史「查看」当前运行。</p>
        <p><b>在线 API 模型怎么接入？</b>切换到「在线 API 模型」，填接口协议、地址、模型名与密钥环境变量名，
          点「测试连接」——通过后配置会自动保存为预设，下次从「已保存的模型接口」一键填入。
          密钥本身只经环境变量设置，不在页面存储。</p>
        <p><b>高级选项里的两个开关是什么？</b>「使用历史测试经验」开启跨运行的长期记忆，
          「智能分配检测预算」开启自适应调度（填总调用预算）。两者都是实验能力，默认关闭，
          不影响标准检测的语义；开启后实况区会显示预算进度，使用经验的轮次带「经验」标记。</p>
      </div>
    </section>
  </div>
</template>

<script setup>
const zones = [
  ['检测对象', '二选一：本地模型开箱即用；在线 API 模型需填接口协议（OpenAI 兼容 / Anthropic / Responses 三种）、接口地址、模型名和密钥环境变量名，点「测试连接」验证连通后即可使用。测试通过的配置自动保存为预设，可随时从下拉快速切换。'],
  ['检测方式与范围', '模式三选：标准检测（首次使用推荐）/ 智能引导（实验）/ 对比检测（两模式并跑，用时约 2 倍）。题库二选：国际基准 JBB-100（100 场景）或中文检测（108 场景，国标五类风险）。范围三选：快速检测（跨类别均匀抽取 2-20 个）/ 完整检测 / 指定场景（先选危害类别再选具体场景，适合深度测试）。每场景轮数 1-10 轮。'],
  ['高级选项', '默认收起。开启长期记忆或智能预算后不影响标准模式；预计调用次数与时长在表单底部实时更新。'],
  ['行动条', '点「开始安全体检」提交（提交后进入队列，单 GPU 串行执行）；「查看示例报告」可秒级打开一份历史运行报告，了解报告的完整形态。'],
  ['运行实况', '进度条 + 已用时间 + 深色终端逐轮对话；运行中可点「停止」优雅取消（当前调用结束后生效，已完成结果保留）。终端头部有信号点图例，提示/回答可点「全文」展开。'],
  ['风险发现', 'KPI 卡展示发现风险场景数、风险发现率（参考等级）、平均首次触发轮次与探索效率；下方是风险类别分布条形图。'],
]
</script>

<style scoped>
.lg-demo { display: inline-flex; align-items: center; gap: 5px; }
.lg-demo i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.lg-demo i.r { background: #e5484d; } .lg-demo i.a { background: #d97706; }
.lg-demo i.g { background: #12a150; }
.doc-card { background: #fff; border: 1px solid var(--line); border-radius: 12px;
  padding: 18px 24px; margin-top: 0; }
.doc-card p { margin: 0 0 10px; }
.doc-card p:last-child { margin-bottom: 0; }
:deep(.dt-txt) { color: #646a73; }
</style>
