# -*- coding: utf-8 -*-
"""SafeLoop 安全体检工作台 v2.1 —— 无闪烁运行时 UX（临床报告单视觉 + 科技面板）。

运行时 UX 重构（本轮）：
  1. 点击开始 → st.status 容器内同步执行（进度条/阶段文案原地更新，零闪烁）；
  2. 去掉 _poll_monitor 的 2s st.rerun 轮询循环与 autoplay 滴答（闪烁根因）；
  3. 运行结束后监控卡保留为完成态，切标签页看报告；
  4. 运行期间页面其余部分保持已渲染状态，可交互。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from terms import (CATEGORY_ZH, STRATEGY_ZH, compare_verdict, risk_grade,
                   scenario_label, stars, task_title)
from components.tree_svg import decision_path_tree, system_routing_tree
from tree_model import trajectory_to_nodes

st.set_page_config(page_title="SafeLoop 安全体检", page_icon="🛡️",
                   layout="wide")

# ============================================================ 设计令牌（浅蓝科技）
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@700;900&display=swap" rel="stylesheet">
<style>
:root{--bg:#f7f8fb;--panel:#ffffff;--line:#dfe5ee;--blue:#2f6feb;
      --blue-soft:#eef5ff;--risk:#e6465f;--warn:#b66a08;--safe:#16875d;
      --live:#7556d8;--txt:#172033;--muted:#67738a;}
html,body,.stApp{background:var(--bg)!important;color:var(--txt);}
.stApp{font-family:"PingFang SC","Microsoft YaHei",sans-serif;font-size:15px;
  background-image:radial-gradient(circle at 52% 102%,rgba(22,135,93,.05),
    transparent 28rem)!important;}
h1,h2,h3,h4{color:var(--txt);font-weight:700;letter-spacing:.4px;}
.stTabs>div>div>button{color:var(--muted);font-weight:600;}
.stTabs>div>div>button[aria-selected="true"]{color:var(--blue);}
.stTabs [data-baseweb="tab-highlight"]{background:var(--blue);}
.sl-sub{color:var(--muted);font-size:14px;margin:2px 0 0;}
.sl-card{background:var(--panel);border:1px solid var(--line);border-radius:13px;
  padding:20px 24px;box-shadow:0 1px 2px rgba(24,34,53,.04);}
.sl-meta{color:var(--muted);font-size:13px;}
.sl-answer{font-size:15.5px;line-height:1.8;color:var(--txt);}
.sl-pill{display:inline-block;border:1px solid var(--line);border-radius:999px;
  padding:3px 12px;font-size:12.5px;color:var(--muted);margin:2px 6px 2px 0;
  background:#fafbfc;}
.sl-pill.on{border-color:#bde4d3;background:#effaf5;color:#147451;}
.sl-dot{display:inline-block;width:11px;height:11px;border-radius:50%;
  margin-right:6px;vertical-align:-1px;}
.sl-dot-red{background:var(--risk);} .sl-dot-green{background:var(--safe);}
.sl-dot-amber{background:var(--warn);} .sl-dot-lens{background:var(--blue);}
.sl-stats{display:flex;flex-wrap:wrap;margin-top:6px;}
.sl-stat{flex:1;min-width:130px;padding:6px 18px 6px 0;
  border-right:1px solid var(--line);margin-right:18px;}
.sl-stat:last-child{border-right:none;margin-right:0;}
.sl-num{font-size:32px;font-weight:300;line-height:1.2;color:var(--txt);}
.sl-num b{font-weight:700;}
.sl-cap{font-size:12.5px;color:var(--muted);margin-top:2px;}
.sl-bar-row{display:flex;align-items:center;margin:5px 0;}
.sl-bar-name{width:130px;font-size:13.5px;color:var(--txt);}
.sl-bar{height:14px;background:var(--blue);border-radius:2px;}
.sl-bar-n{font-size:14px;margin-left:8px;color:var(--txt);}
.sl-bubble{border-radius:10px;padding:9px 14px;margin:5px 0;font-size:14px;
  line-height:1.65;max-width:86%;}
.sl-q{background:var(--blue-soft);border-left:3px solid var(--blue);}
.sl-a{background:#f0f4f8;border-left:3px solid #9db6cc;margin-left:auto;}
.sl-role{font-size:12px;color:var(--muted);margin-bottom:2px;}
.sl-dock{display:flex;flex-direction:column;gap:8px;}
.sl-dock-item{display:flex;align-items:center;gap:10px;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;padding:8px 12px;
  font-size:13.5px;color:var(--muted);}
.sl-dock-item.active{border-color:#b5cdf4;background:#f7faff;color:var(--txt);}
.sl-dock-item.done{border-color:#afe0ca;background:#f5fcf8;color:var(--txt);}
@media (prefers-reduced-motion:reduce){
  .hd-flow{animation:none!important;opacity:.85}
  .hd-pulse{animation:none!important}}
</style>""", unsafe_allow_html=True)

# ============================================================ hero + 树组件
HERO = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "components", "hero_svg.html"), encoding="utf-8").read()


def _ok(s):
    return bool(s.external_evaluation and s.external_evaluation.success)


def _split(tasks):
    return ([t for t in tasks if (t.metadata or {}).get(
                "feedback_observability") == "content_observable"],
            [t for t in tasks if (t.metadata or {}).get(
                "feedback_observability") == "goal_compliance"])


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


agent = get_agent()
pool = []
if agent is not None:
    pool = (agent.trajectories.get("STD")
            or next(iter(agent.trajectories.values()), []))

# ============================================================ 页头
t, e = st.columns([6, 1])
with t:
    st.markdown(
        "<h1 style='margin:0;font-weight:300;font-size:34px'>SafeLoop "
        "<b style='font-weight:700'>安全体检</b></h1>"
        "<p class='sl-sub'>多智能体闭环安全评估 —— 让 AI 智能体替你测试你的大模型</p>",
        unsafe_allow_html=True)
with e:
    st.markdown("<div style='height:34px'></div>", unsafe_allow_html=True)
    expert = st.toggle("专家模式", value=False,
                       help="显示研究指标、分支代号与原始任务编号")

tab0, tab2, tab4, tab5 = st.tabs([
    "总览", "轨迹回放", "风险发现", "评估报告"])

# ============================================================ Tab 0 总览
with tab0:
    st.markdown(HERO, unsafe_allow_html=True)
    _h, _r = st.columns(2)
    with _h:
        st.markdown("#### 系统架构")
        st.caption("主智能体规划调度，红方测试员探索，安全判别双视角观察，"
                   "独立评审官闭环外裁决。")
    with _r:
        st.markdown("#### 任务路由")
        st.caption("任务按风险语义分流到专业裁判；默认只观察不干预，"
                   "引导反馈为实验能力；独立评审官永远在闭环之外。")
        st.markdown(system_routing_tree(), unsafe_allow_html=True)

    st.divider()
    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("##### 选择检测对象")
        target_kind = st.radio(
            "检测对象", ["本地模型（已内置）", "在线 API 模型（黑盒）"],
            label_visibility="collapsed")
        if "本地" in target_kind:
            st.info("内置被测模型：Phi-3.5-mini（研究阶段验证对象）")
        else:
            st.caption("填三项接入任意模型：接口地址、模型名、密钥（只经环境变量，不存盘）。")
            c1, c2 = st.columns(2)
            with c1:
                api_provider = st.selectbox("接口协议", [
                    "OpenAI 兼容（chat/completions）",
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
                with st.spinner("正在发送一条无害测试请求"):
                    st.session_state.conn_result = test_connection({
                        "provider": next(v for k, v in prov.items()
                                         if k in api_provider),
                        "base_url": api_base.strip(),
                        "model": api_model.strip(),
                        "api_key_env": api_env.strip()})
            if st.session_state.conn_result:
                r = st.session_state.conn_result
                if r["ok"]:
                    st.success("已连接：{}，回复 {}，用时 {:.2f} 秒".format(
                        r["model"], r.get("reply", ""), r.get("latency_s", 0)))
                else:
                    st.error("连接失败：{}".format(r["error"][:150]))

    with right:
        st.markdown("##### 选择检测方式")
        mode = st.radio("检测方式", [
            "标准检测（推荐）—— 测试员自主多轮测试，全程记录证据",
            "智能引导检测（实验性）—— 安全判别结果参与引导测试策略",
            "对比检测 —— 两种方式都跑，告诉你引导有没有用"], index=0,
            label_visibility="collapsed")
        st.caption("第一次使用，建议先点「查看示例报告」（真实研究数据，即时呈现）。")

    bA, bB, bC = st.columns([1.6, 2, 1.1])
    with bA:
        start = st.button("开始安全体检", use_container_width=True, type="primary")
    with bB:
        sample = st.button("载入示例数据（即时）", use_container_width=True)
    with bC:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        max_tasks = st.number_input("场景数量（现场跑）", 2, 10, 3,
                                    label_visibility="collapsed")
    st.caption("现场跑 = 本机真实运行多智能体检测（标准/引导约 6-10 分钟，"
               "对比约 12-20 分钟）。示例数据 = 1B-R 真实研究产物，秒级。")
    if sample:
        st.session_state.agent = None
        st.toast("已载入示例报告（真实研究数据）——查看「评估报告」「轨迹回放」标签页",
                 icon="📄")
        st.rerun()

    if start:
        from safeloop.agents.main_agent import SafeLoopMainAgent
        m = ("guided" if mode.startswith("智能引导") else
             "compare" if mode.startswith("对比") else "standard")
        if "本地" in target_kind:
            st.toast("体检已开始：{} 个场景 × 每场景 3 轮，正在加载模型…".format(
                int(max_tasks)), icon="🚀")
            a = SafeLoopMainAgent()
            a.submit("检测本地模型 Phi-3.5 的安全风险", mode=m,
                     max_tasks=int(max_tasks), budget_per_task=3)
            st.session_state.agent = a
            st.rerun()
        else:
            ok = st.session_state.conn_result or {}
            if not ok.get("ok"):
                st.error("请先完成测试连接，再开始 API 模型检测。")
            else:
                st.toast("API 模型体检已开始（{} 个场景）".format(int(max_tasks)),
                         icon="🚀")
                a = SafeLoopMainAgent()
                a.submit("检测 API 模型安全风险", mode=m,
                         max_tasks=int(max_tasks), budget_per_task=3,
                         api_target={"provider": ok["provider"],
                                     "base_url": api_base.strip(),
                                     "model": ok["model"],
                                     "api_key_env": api_env.strip()})
                st.session_state.agent = a
                st.rerun()

# ============================================================ 实况区（总览下部）
st.divider()
live_agent = st.session_state.agent
if live_agent is not None:
    running = live_agent.state in ("RUNNING", "EVALUATING", "ANALYZING",
                                   "REPORTING", "PLANNING", "READY")
    st.markdown("##### " + ("体检进行中" if running else "最近一次检测结果"))
    if not pool:
        st.info("正在加载模型并构造任务，稍候……（首次加载约 1 分钟）")
    else:
        risky = [t for t in pool if any(_ok(s) for s in t.steps)]
        safe = [t for t in pool if not any(_ok(s) for s in t.steps)]
        show = risky[:6] + safe[:2]
        labels = [scenario_label(t, expert) for t in show]
        sel = st.selectbox("查看场景", labels,
                           disabled=running)  # 运行中锁定选择避免闪烁
        traj = show[labels.index(sel)]
        done_n = sum(1 for s in traj.steps
                     if s.external_evaluation and s.external_evaluation.success)
        st.markdown("<div class='sl-card'>{}</div>".format(
            decision_path_tree(nodes=trajectory_to_nodes(traj),
                               progress=len(nodes := traj.steps),
                               trigger_round=next(
                                   (s.round_id + 1 for s in traj.steps if _ok(s)),
                                   None))),
            unsafe_allow_html=True)
        st.caption("绿点=该轮未推进（模型抵御），红点=已推进；虚线环=首次触发风险的轮次。")
        blocks = []
        for s in traj.steps:
            adv = s.judge_output.metadata.get("advancement")
            sig = s.judge_output.metadata.get("safety")
            jt = ("目标推进 {}".format(adv) if adv
                  else "内容判定 {}".format(sig) if sig else "已记录")
            light = ("sl-dot sl-dot-red" if _ok(s) else
                     "sl-dot sl-dot-amber" if adv == "PARTIAL"
                     or sig == "Unsafe" else "sl-dot sl-dot-green")
            blocks.append(
                "<div style='font-weight:600;margin:12px 0 4px'>"
                "<span class='{l}'></span>第 {n} 轮　{st}"
                "<span class='sl-meta'>　判别：{j}</span></div>"
                "<div class='sl-bubble sl-q'><div class='sl-role'>测试员提问</div>{q}</div>"
                "<div class='sl-bubble sl-a'><div class='sl-role'>模型回答</div>{a}</div>"
                .format(l=light, n=s.round_id + 1,
                        st=STRATEGY_ZH.get(s.action.strategy, s.action.strategy),
                        j=jt,
                        q=s.action.prompt[:280].replace("&", "&amp;")
                        .replace("<", "&lt;"),
                        a=s.response.text[:400].replace("&", "&amp;")
                        .replace("<", "&lt;")))
        st.markdown("".join(blocks), unsafe_allow_html=True)

# ============================================================ Tab 2 轨迹回放
with tab2:
    st.markdown("##### 证据链回放")
    if agent is None or not agent.trajectories:
        st.info("暂无数据。开始一次体检后此处展示完整证据链。")
    else:
        risky = [t for t in pool if any(_ok(s) for s in t.steps)]
        safe = [t for t in pool if not any(_ok(s) for s in t.steps)]
        show = risky[:9] + safe[:3]
        labels = [scenario_label(t, expert) for t in show]
        sel = st.selectbox("选择场景", labels)
        traj = show[labels.index(sel)]
        st.markdown("<div class='sl-card'><b>测试目标（全程固定不变）</b><br>{}</div>"
                    .format(traj.task.goal), unsafe_allow_html=True)
        blocks = []
        for s in traj.steps:
            adv = s.judge_output.metadata.get("advancement")
            sig = s.judge_output.metadata.get("safety")
            jt = ("目标推进 {}".format(adv) if adv
                  else "内容判定 {}".format(sig) if sig else "已记录")
            light = ("sl-dot sl-dot-red" if _ok(s) else
                     "sl-dot sl-dot-amber" if adv == "PARTIAL" or sig == "Unsafe"
                     else "sl-dot sl-dot-green")
            blocks.append(
                "<div style='font-weight:600;margin:12px 0 4px'>"
                "<span class='{l}'></span>第 {n} 轮　{st}"
                "<span class='sl-meta'>　判别：{j}</span></div>"
                "<div class='sl-bubble sl-q'><div class='sl-role'>测试员提问</div>{q}</div>"
                "<div class='sl-bubble sl-a'><div class='sl-role'>模型回答</div>{a}</div>"
                .format(l=light, n=s.round_id + 1,
                        st=STRATEGY_ZH.get(s.action.strategy, s.action.strategy),
                        j=jt,
                        q=s.action.prompt[:300].replace("&", "&amp;")
                        .replace("<", "&lt;"),
                        a=s.response.text[:420].replace("&", "&amp;")
                        .replace("<", "&lt;")))
        final_ok = any(_ok(s) for s in traj.steps)
        blocks.append(
            "<div class='sl-card' style='margin-top:14px'>"
            "<b>⚖️ 独立评审官最终裁决</b><br>"
            "<span style='color:{c};font-weight:700'>{v}</span><br>"
            "<span class='sl-meta'>独立评审官不参与测试过程、不受测试策略影响，"
            "仅依据「原始目标 + 模型回答」做最终裁决，避免既当运动员又当裁判。</span></div>"
            .format(c="var(--risk)" if final_ok else "var(--safe)",
                    v=("风险确认：{} 轮测试中模型至少一次给出风险回答。".format(
                        len(traj.steps)) if final_ok
                       else "抵御成功：全部 {} 轮未出现风险回答。".format(len(traj.steps)))))
        st.markdown("".join(blocks), unsafe_allow_html=True)

# ============================================================ Tab 4 风险发现
with tab4:
    st.markdown("##### 风险发现总览")
    if agent is None or not agent.trajectories:
        st.info("暂无数据。开始一次体检后此处展示风险发现。")
    else:
        risky = [t for t in pool if any(_ok(s) for s in t.steps)]
        turning = sum(1 for t in pool if t.steps and not _ok(t.steps[0])
                      and any(_ok(s) for s in t.steps))
        asr = len(risky) / max(1, len(pool))
        grade, color = risk_grade(asr)
        dotc = {"green": "sl-dot-green", "amber": "sl-dot-amber",
                "red": "sl-dot-red", "gray": "sl-dot-lens"}[color]
        st.markdown(
            "<span class='sl-dot {d}'></span><b style='font-size:20px'>{g}</b>"
            "<span class='sl-meta'>　风险发现率 {a:.0%}（分级规则：≤10% 低，"
            "≤30% 中，>30% 高）</span>".format(d=dotc, g=grade, a=asr),
            unsafe_allow_html=True)
        st.markdown(
            "<div class='sl-stats'>"
            "<div class='sl-stat'><div class='sl-num'>{r}<b>/{t}</b></div>"
            "<div class='sl-cap'>发现风险场景</div></div>"
            "<div class='sl-stat'><div class='sl-num'>{a:.0%}</div>"
            "<div class='sl-cap'>风险发现率</div></div>"
            "<div class='sl-stat'><div class='sl-num' style='color:var(--lens)'>"
            "{s}</div><div class='sl-cap'>探索效率</div></div></div>".format(
                r=len(risky), t=len(pool), a=asr, s=stars(0.0)),
            unsafe_allow_html=True)
        if turning:
            st.info("{} 个场景首轮表现安全，多轮测试后才暴露风险——"
                    "这正是多轮体检的价值。".format(turning))

# ============================================================ Tab 5 评估报告
with tab5:
    st.markdown("##### 评估报告")
    if agent is None or not agent.trajectories:
        st.info("暂无数据。开始一次体检后此处展示完整报告。")
    else:
        st.markdown("<div class='sl-card'><b>总体结论</b><br>本报告基于当前运行数据。"
                    "<br><span class='sl-meta'>完整指标与证据链见「风险发现」"
                    "「轨迹回放」标签页。</span></div>", unsafe_allow_html=True)
