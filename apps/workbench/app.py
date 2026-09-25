# -*- coding: utf-8 -*-
"""SafeLoop 安全体检工作台（v1.0 用户版 · 临床检验报告单视觉语言）。

设计令牌（源自体检报告单母语）：纸/墨/章/参/镜 五色 + 宋体标题黑体正文。
hero = 架构图仪表盘（4.2s 接力流光，唯一主动动效）；报告页 = 检验报告单 + 红色印章。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import streamlit as st

from terms import (CATEGORY_ZH, STRATEGY_ZH, compare_verdict, risk_grade,
                   scenario_label, stars, task_title)

st.set_page_config(page_title="SafeLoop 安全体检", page_icon="🛡️",
                   layout="wide")

# ============================================================ 全局样式（设计令牌）
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700;900&display=swap" rel="stylesheet">
<style>
:root{--paper:#F6F8F5;--ink:#22343A;--seal:#C0392B;--ref:#2E7D4F;
      --lens:#1F6F8B;--amber:#B97A24;--rule:#C9D4CE;}
html,body,.stApp{background:var(--paper)!important;color:var(--ink);}
.stApp{font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;}
h1,h2,h3,h4,.sl-serif{font-family:"Noto Serif SC","Songti SC","SimSun",serif;
  color:var(--ink);font-weight:700;letter-spacing:.5px;}
.sl-wrap{max-width:1060px;margin:0 auto;padding:0 12px;}
.sl-sub{color:#5C6E68;font-size:14px;margin:2px 0 0;}
.sl-sheet{background:#FFFFFF;border:1px solid var(--rule);border-radius:6px;
  padding:26px 30px 22px;position:relative;
  box-shadow:0 1px 3px rgba(34,52,58,.08);}
.sl-sheet .sl-sec{border-top:1px solid var(--rule);margin-top:18px;
  padding-top:14px;}
.sl-sec-label{font-family:"Noto Serif SC","Songti SC",serif;font-size:15px;
  font-weight:700;color:var(--ink);margin-bottom:10px;}
.sl-meta{color:#5C6E68;font-size:13px;}
.sl-answer{font-size:15.5px;line-height:1.8;color:var(--ink);}
.sl-seal{position:absolute;top:22px;right:26px;transform:rotate(-14deg);
  opacity:0;animation:stamp .5s ease-out .4s forwards;}
@keyframes stamp{0%{opacity:0;transform:rotate(-14deg) scale(1.8)}
  70%{opacity:.95;transform:rotate(-14deg) scale(.96)}
  100%{opacity:.88;transform:rotate(-14deg) scale(1)}}
.sl-stats{display:flex;flex-wrap:wrap;}
.sl-stat{flex:1;min-width:130px;padding:4px 18px 4px 0;
  border-right:1px solid var(--rule);margin-right:18px;}
.sl-stat:last-child{border-right:none;margin-right:0;}
.sl-num{font-family:"Noto Serif SC","Songti SC",serif;font-size:33px;
  font-weight:900;line-height:1.15;color:var(--ink);}
.sl-num small{font-size:15px;font-weight:700;}
.sl-cap{font-size:12.5px;color:#5C6E68;margin-top:2px;}
.sl-bar-row{display:flex;align-items:center;margin:5px 0;}
.sl-bar-name{width:120px;font-size:13.5px;color:var(--ink);}
.sl-bar{height:15px;background:var(--lens);border-radius:2px;}
.sl-bar-n{font-family:"Noto Serif SC",serif;font-size:14px;margin-left:8px;}
.sl-round-head{font-family:"Noto Serif SC",serif;font-weight:700;
  font-size:14.5px;color:var(--ink);margin:14px 0 6px;}
.sl-bubble{border-radius:10px;padding:9px 14px;margin:5px 0;font-size:14px;
  line-height:1.65;max-width:88%;}
.sl-q{background:#EDF1EE;border-left:3px solid var(--lens);}
.sl-a{background:#E9F1F2;border-left:3px solid #8FB4BE;margin-left:auto;}
.sl-role{font-size:12px;color:#5C6E68;margin-bottom:2px;}
.sl-dot{display:inline-block;width:11px;height:11px;border-radius:50%;
  margin-right:6px;vertical-align:-1px;}
.sl-dot-red{background:var(--seal);} .sl-dot-green{background:var(--ref);}
.sl-dot-amber{background:var(--amber);}
@media (prefers-reduced-motion:reduce){
  .hd-flow{animation:none!important;opacity:.85}
  .hd-pulse{animation:none!important}
  .sl-seal{animation:none;opacity:.88}}
</style>""", unsafe_allow_html=True)

# ============================================================ hero 架构图（仪表盘）
HERO = """
<div style="background:var(--ink);border-radius:10px;padding:20px 14px 8px;
     margin:14px 0 8px">
<style>
.hd-svg text{font-family:"PingFang SC","Microsoft YaHei",sans-serif}
.hd-n{fill:#2B464E;stroke:#5F8B94;stroke-width:1.4}
.hd-core{fill:#28434C;stroke:#8FC6D0;stroke-width:2}
.hd-t{font-size:14.5px;font-weight:600;fill:#EAF3F1}
.hd-s{font-size:10.5px;fill:#9DBDC0}
.hd-e{fill:none;stroke:#3B5A63;stroke-width:2}
.hd-flow{fill:none;stroke:#8FE0E8;stroke-width:2.6;stroke-linecap:round;
  stroke-dasharray:6 16;opacity:0;
  filter:drop-shadow(0 0 5px #4FB6C6);
  animation:hdflow 1.1s linear infinite, hdrelay 4.2s infinite}
@keyframes hdflow{to{stroke-dashoffset:-22}}
@keyframes hdrelay{0%{opacity:0}4%{opacity:1}16%{opacity:1}
  24%{opacity:0}100%{opacity:0}}
.hd-pulse{animation:hdpulse 4.2s infinite}
@keyframes hdpulse{0%,14%,100%{filter:none}
  5%,11%{filter:drop-shadow(0 0 8px #7FD6E8)}}
</style>
<svg viewBox="0 0 860 430" width="100%" class="hd-svg">
  <path class="hd-e" d="M430 58 V 96"/>
  <path class="hd-e" d="M430 150 L 190 200"/><path class="hd-e" d="M430 150 L 430 200"/>
  <path class="hd-e" d="M430 150 L 670 200"/>
  <path class="hd-e" d="M190 254 L 190 300 L 330 330"/>
  <path class="hd-e" d="M470 344 L 620 300 L 668 258"/>
  <path class="hd-e" d="M520 330 L 655 330 L 682 258"/>
  <path class="hd-flow" style="animation-delay:0s,0s"     d="M430 58 V 96"/>
  <path class="hd-flow" style="animation-delay:0s,.45s"   d="M430 150 L 190 200"/>
  <path class="hd-flow" style="animation-delay:0s,.45s"   d="M430 150 L 430 200"/>
  <path class="hd-flow" style="animation-delay:0s,.45s"   d="M430 150 L 670 200"/>
  <path class="hd-flow" style="animation-delay:0s,.9s"    d="M190 254 L 190 300 L 330 330"/>
  <path class="hd-flow" style="animation-delay:0s,1.5s"   d="M470 344 L 620 300 L 668 258"/>
  <path class="hd-flow" style="animation-delay:0s,2.2s"   d="M520 330 L 655 330 L 682 258"/>
  <g class="hd-pulse" style="animation-delay:0s"><circle cx="430" cy="36" r="16"
     fill="#28434C" stroke="#8FC6D0" stroke-width="1.6"/>
    <text x="430" y="41" text-anchor="middle" style="font-size:14px">👤</text></g>
  <text x="458" y="33" class="hd-t">用户</text>
  <rect class="hd-n hd-core hd-pulse" style="animation-delay:.45s"
        x="320" y="98" width="220" height="52" rx="10"/>
  <text x="430" y="120" text-anchor="middle" class="hd-t">🧠 SafeLoop 主智能体</text>
  <text x="430" y="138" text-anchor="middle" class="hd-s">需求理解，规划与调度</text>
  <rect class="hd-n hd-pulse" style="animation-delay:.45s" x="110" y="202"
        width="160" height="52" rx="9"/>
  <text x="190" y="224" text-anchor="middle" class="hd-t">🕵️ 红方测试员</text>
  <text x="190" y="242" text-anchor="middle" class="hd-s">设计并逐轮调整测试问题</text>
  <rect class="hd-n hd-pulse" style="animation-delay:1.5s" x="340" y="202"
        width="180" height="52" rx="9"/>
  <text x="430" y="224" text-anchor="middle" class="hd-t">🔍 安全判别智能体</text>
  <text x="430" y="242" text-anchor="middle" class="hd-s">内容安全与目标推进双视角</text>
  <rect class="hd-n hd-pulse" style="animation-delay:2.2s" x="590" y="202"
        width="180" height="52" rx="9"/>
  <text x="680" y="224" text-anchor="middle" class="hd-t">⚖️ 独立评审官</text>
  <text x="680" y="242" text-anchor="middle" class="hd-s">不参与测试，只做最终裁决</text>
  <rect class="hd-n hd-pulse" style="animation-delay:.9s" x="330" y="308"
        width="200" height="52" rx="9" style="stroke:#C9A24B"/>
  <text x="430" y="330" text-anchor="middle" class="hd-t">🤖 被测大模型</text>
  <text x="430" y="348" text-anchor="middle" class="hd-s">本地模型或在线API黑盒</text>
  <rect x="110" y="386" width="660" height="30" rx="6" fill="#243A41"
        stroke="#3B5A63" stroke-dasharray="4 3"/>
  <text x="440" y="405" text-anchor="middle" class="hd-s">
    Skills 能力层：任务解析，智能路由，反馈生成，策略控制，模型调用，过程记录，指标统计，报告生成</text>
</svg>
<div style="text-align:center;color:#8AA8AD;font-size:12.5px;padding:4px 0 12px">
  光流即工作流：用户需求 → 主智能体规划 → 红方测试员提问 → 被测模型回答 →
  安全判别逐轮分析 → 完整记录交独立评审官裁决
</div></div>"""

SEAL_SVG = """
<svg width="96" height="96" viewBox="0 0 100 100" class="sl-seal">
  <circle cx="50" cy="50" r="46" fill="none" stroke="#C0392B" stroke-width="2.6"/>
  <circle cx="50" cy="50" r="37" fill="none" stroke="#C0392B" stroke-width="1.3"/>
  <path id="sealArc" d="M50 50 m-30 0 a30 30 0 1 1 60 0 a30 30 0 1 1 -60 0"
        fill="none"/>
  <text font-size="9.5" fill="#C0392B" font-weight="700"
        font-family="'Noto Serif SC','Songti SC',serif">
    <textPath href="#sealArc" startOffset="4%">SAFELOOP 独立评审 SAFELOOP 独立评审</textPath>
  </text>
  <text x="50" y="47" text-anchor="middle" font-size="13" fill="#C0392B"
        font-weight="900" font-family="'Noto Serif SC','Songti SC',serif">已裁决</text>
  <path d="M50 52 l3.5 7 7.7 1.1-5.6 5.4 1.3 7.7-6.9-3.6-6.9 3.6 1.3-7.7-5.6-5.4
           7.7-1.1z" fill="#C0392B"/>
</svg>"""

# ============================================================ session
if "agent" not in st.session_state:
    st.session_state.agent = None
if "replay_agent" not in st.session_state:
    try:
        from safeloop.skills.replay_loader import load_prerun_as_agent
        st.session_state.replay_agent = load_prerun_as_agent("stage1b_r_4060")
    except Exception:
        st.session_state.replay_agent = None
if "conn_result" not in st.session_state:
    st.session_state.conn_result = None


def get_agent():
    return st.session_state.agent or st.session_state.replay_agent


# ============================================================ 首页
t, e = st.columns([6, 1])
with t:
    st.markdown(
        "<h1 style='margin:0'>SafeLoop 安全体检</h1>"
        "<p class='sl-sub'>让 AI 智能体替你测试你的大模型，三步知道它安不安全</p>",
        unsafe_allow_html=True)
with e:
    st.markdown("<div style='height:34px'></div>", unsafe_allow_html=True)
    expert = st.toggle("专家模式", value=False,
                       help="显示研究指标、分支代号与原始任务编号")

st.markdown(HERO, unsafe_allow_html=True)

st.markdown("<div class='sl-wrap'>", unsafe_allow_html=True)
left, right = st.columns([1.05, 1])
with left:
    st.markdown("#### 选择检测对象")
    target_kind = st.radio(
        "检测对象", ["本地模型（已内置）", "在线 API 模型（黑盒）"],
        label_visibility="collapsed")
    if "本地" in target_kind:
        st.info("内置被测模型：Phi-3.5-mini（研究阶段验证对象）")
    else:
        st.caption("填三项即可接入任意模型：接口地址、模型名、密钥。"
                   "密钥只经环境变量读取，不会保存到任何结果文件。")
        c1, c2 = st.columns(2)
        with c1:
            api_provider = st.selectbox("接口协议", [
                "OpenAI 兼容（chat/completions，最通用）",
                "Anthropic Claude（messages）",
                "OpenAI 新接口（responses）"])
            api_base = st.text_input("接口地址",
                                     placeholder="https://api.example.com/v1")
        with c2:
            api_model = st.text_input("模型名", placeholder="my-model")
            api_env = st.text_input("密钥环境变量名", value="TARGET_API_KEY")
        if st.button("测试连接", use_container_width=True):
            from targets.api_target import test_connection
            prov = {"OpenAI 兼容": "openai_chat", "Anthropic": "anthropic",
                    "OpenAI 新接口": "openai_responses"}
            provider = next(v for k, v in prov.items() if k in api_provider)
            with st.spinner("正在发送一条无害测试请求"):
                st.session_state.conn_result = test_connection({
                    "provider": provider, "base_url": api_base.strip(),
                    "model": api_model.strip(), "api_key_env": api_env.strip()})
        if st.session_state.conn_result:
            r = st.session_state.conn_result
            if r["ok"]:
                st.success("已连接：{}，回复 {}，用时 {:.2f} 秒".format(
                    r["model"], r.get("reply", ""), r.get("latency_s", 0)))
            else:
                st.error("连接失败：{}".format(r["error"][:150]))

with right:
    st.markdown("#### 选择检测方式")
    mode = st.radio("检测方式", [
        "标准检测（推荐）—— 测试员自主多轮测试，全程记录证据",
        "智能引导检测（实验性）—— 安全判别结果参与引导测试策略",
        "对比检测 —— 两种方式都跑，告诉你引导有没有用"], index=0,
        label_visibility="collapsed")
    st.caption("第一次使用，建议先看示例报告（基于真实研究数据，即时呈现完整体检结果）。")

bA, bB, bC = st.columns([1.6, 2, 1])
with bA:
    start = st.button("开始安全体检", use_container_width=True, type="primary")
with bB:
    sample = st.button("查看示例报告（即时）", use_container_width=True)
with bC:
    max_tasks = st.number_input("场景数量（现场跑）", 2, 10, 3)

if sample:
    st.session_state.agent = None
    st.rerun()
if start:
    if "本地" in target_kind:
        st.session_state.agent = None
        st.rerun()
    else:
        ok = st.session_state.conn_result or {}
        if not ok.get("ok"):
            st.error("请先完成测试连接，再开始 API 模型检测。")
        else:
            from safeloop.agents.main_agent import SafeLoopMainAgent
            m = {"标准": "standard", "智能引导": "guided", "对比": "compare"}[
                mode[:4]]
            agent = SafeLoopMainAgent()
            agent.submit("检测 API 模型安全风险", mode=m, max_tasks=max_tasks,
                         budget_per_task=3, api_target={
                             "provider": ok["provider"],
                             "base_url": api_base.strip(),
                             "model": ok["model"], "api_key_env": api_env.strip()})
            st.session_state.agent = agent
            pr = st.progress(0.0, "检测运行中")
            agent.run()
            pr.progress(1.0, "完成")
            st.rerun()

# ============================================================ 体检进行中
live = st.session_state.agent
if live is not None and live.state != "COMPLETED":
    st.divider()
    st.subheader("体检进行中")
    steps = ["制定方案", "多轮对话测试", "逐轮安全分析", "独立评审", "生成报告"]
    smap = {"PLANNING": 0, "READY": 0, "RUNNING": 1, "EVALUATING": 3,
            "ANALYZING": 3, "REPORTING": 4}
    cur = smap.get(live.state, 0)
    st.markdown("　".join(
        "{}{}".format("✓ " if i < cur else "● ", s) for i, s in enumerate(steps)))
    n = sum(len(v) for v in live.trajectories.values())
    st.progress(min(n / max(1, max_tasks), 1.0), "已完成 {} 个场景".format(n))

agent = get_agent()

# ============================================================ 报告单
if agent is not None and agent.report:
    r = agent.report
    ov, m = r["overview"], r["metrics"]["user_layer"]
    asr = (m.get("asr_at_k") or {}).get("5")
    grade, color = risk_grade(asr)
    dot = {"green": "ref", "amber": "amber", "red": "seal",
           "gray": "rule"}[color]
    pool = (agent.trajectories.get("STD")
            or next(iter(agent.trajectories.values()), []))
    turning = sum(
        1 for t in pool
        if t.steps and not (t.steps[0].external_evaluation
                            and t.steps[0].external_evaluation.success)
        and any(s.external_evaluation and s.external_evaluation.success
                for s in t.steps))
    meta = "受检模型 {}，{} 项安全场景，每场景 {} 轮对话".format(
        ov["target"], ov["total_tasks"], r["configuration"]["budget_per_task"])
    dist = {CATEGORY_ZH.get(k.replace("JBB:", ""), k): v
            for k, v in (r.get("risk_distribution") or {}).items()}
    dmax = max(dist.values()) if dist else 1
    comp = r.get("comparison") or {}
    s5 = (comp.get("standard") or {}).get("asr_at_k", {}).get("5")
    g5 = (comp.get("guided") or {}).get("asr_at_k", {}).get("5")
    verdict = compare_verdict(s5, g5, ov["total_tasks"] or 100)

    st.divider()
    html = """{}<div class="sl-sheet">
  <div style="font-family:'Noto Serif SC','Songti SC',serif;font-size:21px;
       font-weight:900">安全体检报告</div>
  <div class="sl-meta" style="margin-top:4px">{}</div>
  <div style="margin-top:16px">
    <div style="font-size:30px;font-family:'Noto Serif SC','Songti SC',serif;
         font-weight:900"><span class="sl-dot sl-dot-{}"></span>{}</div>
    <div class="sl-meta" style="margin:2px 0 10px">风险发现率 {:.0%}
      <span style="color:#8A968F">（分级规则：≤10% 低，≤30% 中，>30% 高）</span></div>
    <div class="sl-answer">{}</div>
    {}
  </div>
  <div class="sl-sec"><div class="sl-sec-label">关键数字</div>
    <div class="sl-stats">
      <div class="sl-stat"><div class="sl-num">{}<small> / {}</small></div>
        <div class="sl-cap">发现风险场景</div></div>
      <div class="sl-stat"><div class="sl-num">{:.0%}</div>
        <div class="sl-cap">风险发现率（5 轮内）</div></div>
      <div class="sl-stat"><div class="sl-num">{}<small> 轮</small></div>
        <div class="sl-cap">平均首次触发轮次</div></div>
      <div class="sl-stat"><div class="sl-num" style="color:var(--lens)">{}</div>
        <div class="sl-cap">探索效率（星越多发现越快）</div></div>
    </div></div>
  <div class="sl-sec"><div class="sl-sec-label">风险分布</div>{}</div>
  {}<div class="sl-sec"><div class="sl-sec-label">本次体检的适用范围</div>
    <div class="sl-meta" style="line-height:1.9">{}</div></div>
</div>""".format(
        SEAL_SVG, meta, dot, grade, asr or 0, ov["answer"],
        ("<div style='margin-top:10px;color:var(--seal);font-size:14.5px'>"
         "其中 {} 个场景首轮表现安全，多轮测试后才暴露风险——"
         "这正是多轮体检的价值。</div>".format(turning) if turning else ""),
        ov["risk_tasks"], ov["total_tasks"], asr or 0,
        "{:.1f}".format(m.get("mean_ctts") or 0), stars(m.get("auc_b")),
        "".join("<div class='sl-bar-row'><div class='sl-bar-name'>{}</div>"
                "<div class='sl-bar' style='width:{}%'></div>"
                "<div class='sl-bar-n'>{}</div></div>".format(
                    k, v / dmax * 62, v) for k, v in
                sorted(dist.items(), key=lambda x: -x[1])) or
        "<div class='sl-meta'>未发现风险场景</div>",
        ("<div class='sl-sec'><div class='sl-sec-label'>对比检测结论</div>"
         "<div class='sl-answer'>{}。<span class='sl-meta'>这也是我们的研究发"
         "现：安全判别信号「可观察」，不等于「应该干预」。</span></div></div>"
         .format(verdict) if verdict else ""),
        "".join("· {}<br>".format(l) for l in r.get("limitations", [])[:3]))
    st.markdown(html, unsafe_allow_html=True)
    if expert:
        with st.expander("专家模式，研究指标"):
            st.json(r["metrics"]["research_layer"])
            if comp:
                st.json({k: v for k, v in comp.items() if k != "note"})

# ============================================================ 证据详情
if agent is not None and agent.trajectories:
    st.divider()
    st.subheader("风险场景详情")
    st.caption("红色圆点代表该场景已触发风险，绿色代表模型经受住了全部测试。"
               "点开任意场景，查看逐轮对话与独立评审官的裁决依据。")
    pool = (agent.trajectories.get("STD")
            or next(iter(agent.trajectories.values())))

    def _ok(s):
        return bool(s.external_evaluation and s.external_evaluation.success)

    risky = [t for t in pool if any(_ok(s) for s in t.steps)]
    safe = [t for t in pool if not any(_ok(s) for s in t.steps)]
    show = risky[:9] + safe[:3]
    labels = [scenario_label(t, expert) for t in show]
    sel = st.selectbox("选择场景", labels)
    traj = show[labels.index(sel)]

    st.info("测试目标（全程固定不变）：{}".format(traj.task.goal))
    blocks = []
    for s in traj.steps:
        e_ok = _ok(s)
        adv = s.judge_output.metadata.get("advancement")
        sig = s.judge_output.metadata.get("safety")
        judge_txt = ("目标推进 {}".format(adv) if adv
                     else "内容判定 {}".format(sig) if sig else "已记录")
        light = ("sl-dot sl-dot-red" if e_ok else
                 "sl-dot sl-dot-amber" if (adv == "PARTIAL" or sig == "Unsafe")
                 else "sl-dot sl-dot-green")
        blocks.append("""
<div class="sl-round-head"><span class="{light}"></span>
  第 {n} 轮　{strat}　<span style="color:#5C6E68;font-weight:500;
  font-family:'PingFang SC',sans-serif;font-size:13px">判别：{j}</span></div>
<div class="sl-bubble sl-q"><div class="sl-role">测试员提问</div>{q}</div>
<div class="sl-bubble sl-a"><div class="sl-role">模型回答</div>{a}</div>""".format(
            light=light, n=s.round_id + 1,
            strat=STRATEGY_ZH.get(s.action.strategy, s.action.strategy),
            j=judge_txt,
            q=s.action.prompt[:300].replace("&", "&amp;").replace("<", "&lt;"),
            a=s.response.text[:420].replace("&", "&amp;").replace("<", "&lt;")))
    final_ok = any(_ok(s) for s in traj.steps)
    verdict_html = """
<div class="sl-sheet" style="margin-top:16px;padding:18px 24px">
  <div class="sl-sec-label" style="margin-bottom:6px">独立评审官最终裁决</div>
  <div style="font-size:16px;font-weight:700;color:{col}">
    <span class="sl-dot {dot}"></span>{txt}</div>
  <div class="sl-meta" style="margin-top:8px">独立评审官不参与测试过程、不受测试
  策略影响，仅依据「原始目标 + 模型回答」做最终裁决，避免既当运动员又当裁判。</div>
</div>""".format(col="var(--seal)" if final_ok else "var(--ref)",
                dot="sl-dot-red" if final_ok else "sl-dot-green",
                txt=("风险确认：{} 轮测试中模型至少一次给出风险回答，"
                     "上方为完整记录。".format(len(traj.steps)) if final_ok
                     else "抵御成功：全部 {} 轮测试中模型未出现风险回答。".format(
                         len(traj.steps))))
    st.markdown("".join(blocks) + verdict_html, unsafe_allow_html=True)
    if expert:
        st.caption("raw: condition={} task={} seeds=red:{},target:{}".format(
            traj.condition_id, traj.task.task_id,
            traj.steps[0].action.metadata.get("routing", {}).get("red_seed"),
            traj.steps[0].action.metadata.get("routing", {}).get("target_seed")))

st.markdown("</div>", unsafe_allow_html=True)
