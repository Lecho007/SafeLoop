# -*- coding: utf-8 -*-
"""SafeLoop 安全体检工作台 v2（科技皮 + 人话心 · 六 Tab 融合版）。

设计令牌（docs/design/gui-v2-fusion-tech.md）：深空青底/镜青主光/信号三色/紫外实况。
默认友好术语，专家键切换专业视图。双决策树（系统路由树 + 单任务路径树），
实况/回放共用组件。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from terms import (CATEGORY_ZH, STRATEGY_ZH, compare_verdict, risk_grade,
                   scenario_label, stars, task_title)
from tree_model import events_to_tree, trajectory_to_nodes
from components.tree_svg import decision_path_tree, system_routing_tree

st.set_page_config(page_title="SafeLoop 安全体检", page_icon="🛡️",
                   layout="wide")

# ============================================================ 设计令牌 + 全局样式
st.markdown("""
<style>
:root{--bg:#f7f8fb;--panel:#ffffff;--panel2:#f5f7fb;--line:#dfe5ee;
      --blue:#2f6feb;--blue-soft:#eef5ff;--risk:#e6465f;--warn:#b66a08;
      --safe:#16875d;--live:#7556d8;--txt:#172033;--muted:#67738a;}
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
.sl-pill.live{border-color:#d6caf5;background:#f7f4ff;color:#684bc3;}
.sl-dot{display:inline-block;width:11px;height:11px;border-radius:50%;
  margin-right:6px;vertical-align:-1px;}
.sl-dot-red{background:var(--risk);} .sl-dot-green{background:var(--safe);}
.sl-dot-amber{background:var(--warn);} .sl-dot-lens{background:var(--blue);}
.sl-stats{display:flex;flex-wrap:wrap;margin-top:6px;}
.sl-stat{flex:1;min-width:130px;padding:6px 18px 6px 0;
  border-right:1px solid var(--line);margin-right:18px;}
.sl-stat:last-child{border-right:none;margin-right:0;}
.sl-num{font-size:32px;font-weight:300;line-height:1.2;color:var(--txt);
  font-variant-numeric:tabular-nums;}
.sl-num b{font-weight:700;}
.sl-cap{font-size:12.5px;color:var(--muted);margin-top:2px;}
.sl-bar-row{display:flex;align-items:center;margin:5px 0;}
.sl-bar-name{width:130px;font-size:13.5px;color:var(--txt);}
.sl-bar{height:14px;background:var(--blue);border-radius:2px;}
.sl-bar-n{font-size:14px;margin-left:8px;color:var(--txt);
  font-variant-numeric:tabular-nums;}
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

# ============================================================ hero 架构图（v2 令牌重着色）
HERO = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "components", "hero_svg.html"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "components", "hero_svg.html")) else ""

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
if "live_rounds" not in st.session_state:
    st.session_state.live_rounds = None


def get_agent():
    return st.session_state.agent or st.session_state.replay_agent


agent = get_agent()

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

tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "总览", "实况演示", "轨迹回放", "决策树", "风险发现", "评估报告"])

# ============================================================ Tab 0 总览
with tab0:
    st.markdown(HERO, unsafe_allow_html=True)
    st.markdown("#### 系统路由树")
    st.caption("任务按风险语义分流到专业裁判；默认只观察不干预，引导反馈为实验能力；"
               "独立评审官永远在闭环之外。")
    st.markdown(system_routing_tree(), unsafe_allow_html=True)

    st.divider()
    left, right = st.columns([1.05, 1])
    with left:
        st.markdown("##### 选择检测对象")
        target_kind = st.radio(
            "检测对象", ["本地模型（已内置）", "在线 API 模型（黑盒）"],
            label_visibility="collapsed")
        if "本地" in target_kind:
            st.markdown('<span class="sl-pill on">已内置 Phi-3.5-mini</span>',
                        unsafe_allow_html=True)
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
                    st.markdown(
                        "<span class='sl-pill on'>已连接 {}，{:.2f}s</span>".format(
                            r["model"], r.get("latency_s", 0)),
                        unsafe_allow_html=True)
                else:
                    st.error("连接失败：{}".format(r["error"][:150]))
    with right:
        st.markdown("##### 选择检测方式")
        mode = st.radio("检测方式", [
            "标准检测（推荐）—— 测试员自主多轮测试，全程记录证据",
            "智能引导检测（实验性）—— 安全判别结果参与引导策略",
            "对比检测 —— 两种都跑，告诉你引导有没有用"], index=0,
            label_visibility="collapsed")
        st.caption("第一次使用，建议先在「实况演示」和「评估报告」查看内置示例（真实研究数据）。")

    bA, bB, bC = st.columns([1.6, 2, 1])
    with bA:
        start = st.button("开始安全体检", use_container_width=True, type="primary")
    with bB:
        sample = st.button("载入示例数据（即时）", use_container_width=True)
    with bC:
        max_tasks = st.number_input("场景数量（现场跑）", 2, 10, 3)
    st.caption("现场跑 = 本机真实运行多智能体检测（加载 4 个模型，标准/引导约 6-10 分钟，"
               "对比约 12-20 分钟，请保持本页打开）。示例数据 = 1B-R 真实研究产物，秒级。")
    if sample:
        st.session_state.agent = None
        st.toast("已载入示例报告（真实研究数据）——查看「评估报告」「轨迹回放」标签页",
                 icon="📄")
        st.rerun()

    def _run_with_progress(a, expected_steps, est_text):
        """后台线程跑 agent，前台轮询步数实时刷进度条。"""
        import threading
        import time as _time
        done = {"ok": False, "err": None}

        def _work():
            try:
                a.run()
                done["ok"] = True
            except Exception as exc:  # noqa: BLE001
                done["err"] = str(exc)
        th = threading.Thread(target=_work, daemon=True)
        th.start()
        pr = st.progress(0.05, "正在加载模型并运行检测（{}）…".format(est_text))
        while th.is_alive():
            _time.sleep(2)
            n = sum(len(t.steps) for ts in a.trajectories.values() for t in ts)
            pr.progress(min(0.95, 0.05 + 0.9 * n / max(1, expected_steps)),
                        "已完成 {} / {} 轮对话 · 当前阶段 {}".format(
                            n, expected_steps,
                            {"RUNNING": "多轮测试", "EVALUATING": "独立评审",
                             "REPORTING": "生成报告"}.get(a.state, a.state)))
        th.join()
        if done["err"]:
            pr.empty()
            st.error("运行出错：{}。可减少场景数重试，或先用示例数据体验。".format(
                done["err"][:220]))
            st.session_state.agent = None
        else:
            pr.progress(1.0, "体检完成")
            n_risk = a.report["overview"]["risk_tasks"] if a.report else 0
            st.toast("体检完成：{} 个场景中发现 {} 个风险。"
                     "请查看「评估报告」与「轨迹回放」".format(
                         a.report["overview"]["total_tasks"] if a.report else 0,
                         n_risk), icon="✅")
            st.rerun()  # 刷新后各标签页读取本次运行数据

    if start:
        from safeloop.agents.main_agent import SafeLoopMainAgent
        m = {"标准": "standard", "智能引导": "guided", "对比": "compare"}[mode[:4]]
        n_branch = 2 if m == "compare" else 1
        est = {"standard": "约 6-10 分钟", "guided": "约 6-10 分钟",
               "compare": "约 12-20 分钟"}[m]
        if "本地" in target_kind:
            st.toast("体检已开始：{} 个场景 × 每场景 3 轮，{}。正在加载模型…".format(
                int(max_tasks), est), icon="🚀")
            a = SafeLoopMainAgent()
            a.submit("检测本地模型 Phi-3.5 的安全风险", mode=m,
                     max_tasks=int(max_tasks), budget_per_task=3)
            st.session_state.agent = a
            _run_with_progress(a, int(max_tasks) * 3 * n_branch, est)
        else:
            ok = st.session_state.conn_result or {}
            if not ok.get("ok"):
                st.error("请先完成测试连接，再开始 API 模型检测。")
            else:
                st.toast("API 模型体检已开始（{} 个场景，{}）".format(
                    int(max_tasks), est), icon="🚀")
                a = SafeLoopMainAgent()
                a.submit("检测 API 模型安全风险", mode=m,
                         max_tasks=int(max_tasks), budget_per_task=3,
                         api_target={"provider": ok["provider"],
                                     "base_url": api_base.strip(),
                                     "model": ok["model"],
                                     "api_key_env": api_env.strip()})
                st.session_state.agent = a
                _run_with_progress(a, int(max_tasks) * 3 * n_branch, est)

# ============================================================ 数据准备
pool = []
report = None
if agent is not None:
    report = agent.report
    pool = (agent.trajectories.get("STD")
            or next(iter(agent.trajectories.values()), []))


def _ok(s):
    return bool(s.external_evaluation and s.external_evaluation.success)


# ============================================================ Tab 1 实况演示
with tab1:
    st.markdown("##### 多智能体实况协作")
    st.caption("下面用内置真实轨迹驱动一次完整任务的实况重演——左侧是各智能体状态，"
               "中间是逐轮对话，右侧的决策树随事件逐轮生长。")
    if not pool:
        st.info("暂无轨迹数据。先在「总览」载入示例数据。")
    else:
        demo = next((t for t in pool if len(t.steps) >= 2), pool[0])
        c1, c2, c3 = st.columns([1, 2.1, 1.6])
        nodes = trajectory_to_nodes(demo)
        _pcol, _acol = st.columns([2.4, 1])
        with _acol:
            if st.button("自动播放（逐轮推进）", use_container_width=True):
                import time as _time
                ph = st.empty()
                for step_i in range(1, len(nodes) + 1):
                    ph.progress(step_i / len(nodes),
                                "第 {} / {} 轮".format(step_i, len(nodes)))
                    st.session_state.live_step = step_i
                    _time.sleep(1.6)
                ph.empty()
                st.rerun()
        # 阶段滑块 = 事件推进（决策树逐轮点亮的演示形态）
        max_step = st.slider("演示进度（逐轮推进）", 1, len(nodes),
                             st.session_state.get("live_step", len(nodes)),
                             key="live_step")
        with c1:
            st.markdown("**智能体状态坞**")
            cur = nodes[max_step - 1]
            st.markdown(
                "<div class='sl-dock'>"
                "<div class='sl-dock-item done'>🧠 主智能体 ✓ 已规划</div>"
                "<div class='sl-dock-item {ra}'>🕵️ 红方测试员</div>"
                "<div class='sl-dock-item {ja}'>🔍 {} 裁判</div>"
                "<div class='sl-dock-item {ca}'>🎛️ 控制器</div>"
                "<div class='sl-dock-item {ea}'>⚖️ 独立评审官</div></div>".format(
                    "目标推进" if (demo.task.metadata or {}).get(
                        "feedback_observability") == "goal_compliance" else "内容安全",
                    ra="active" if max_step < len(nodes) else "done",
                    ja="active",
                    ca="done" if cur.get("action") else "",
                    ea="done" if max_step == len(nodes) else ""),
                unsafe_allow_html=True)
            if max_step == len(nodes):
                verdict = "风险确认" if any(_ok(s) for s in demo.steps) else "抵御成功"
                st.markdown('<span class="sl-pill {}">{}</span>'.format(
                    "on" if verdict == "抵御成功" else "", "评审官终裁：" + verdict),
                    unsafe_allow_html=True)
            # 迷你系统路由树：当前任务域分支高亮 + 裁判节点脉冲（实况联动）
            demo_dom = (demo.task.metadata or {}).get("feedback_observability")
            dom = ("goal" if demo_dom == "goal_compliance" else "content")
            st.markdown("**系统路由联动**")
            with st.expander("当前任务在系统中的位置", expanded=True):
                st.markdown(system_routing_tree(
                    active_domain=dom, active_role="judge"),
                    unsafe_allow_html=True)
        with c2:
            blocks = []
            for s in demo.steps[:max_step]:
                adv = s.judge_output.metadata.get("advancement")
                sig = s.judge_output.metadata.get("safety")
                jt = ("目标推进 {}".format(adv) if adv
                      else "内容判定 {}".format(sig) if sig else "已记录")
                light = ("sl-dot sl-dot-red" if _ok(s) else
                         "sl-dot sl-dot-amber" if adv == "PARTIAL"
                         or sig == "Unsafe" else "sl-dot sl-dot-green")
                blocks.append(
                    "<div style='font-weight:600;margin:10px 0 4px'>"
                    "<span class='{l}'></span>第 {n} 轮　{st}"
                    "<span class='sl-meta'>　判别：{j}</span></div>"
                    "<div class='sl-bubble sl-q'><div class='sl-role'>测试员提问</div>{q}</div>"
                    "<div class='sl-bubble sl-a'><div class='sl-role'>模型回答</div>{a}</div>"
                    .format(l=light, n=s.round_id + 1,
                            st=STRATEGY_ZH.get(s.action.strategy,
                                               s.action.strategy), j=jt,
                            q=s.action.prompt[:260].replace("&", "&amp;")
                            .replace("<", "&lt;"),
                            a=s.response.text[:380].replace("&", "&amp;")
                            .replace("<", "&lt;")))
            st.markdown("".join(blocks), unsafe_allow_html=True)
        with c3:
            st.markdown("**实况决策树**")
            shown = []
            for i, nd in enumerate(nodes[:max_step]):
                nd2 = dict(nd)
                nd2["state"] = ("red" if i == max_step - 1 and max_step < len(nodes)
                                else "decided")
                shown.append(nd2)
            demo_trig = next((s.round_id + 1 for s in demo.steps if _ok(s)), None)
            st.markdown(decision_path_tree(
                shown, verdict=None if max_step < len(nodes) else
                ("风险确认" if any(_ok(s) for s in demo.steps) else "抵御成功"),
                live=True, trigger_round=(demo_trig if demo_trig and
                                          demo_trig <= max_step else None)),
                unsafe_allow_html=True)
            st.caption("节点色 = 裁判信号（红 推进显著 / 黄 部分推进 / 绿 未推进），"
                       "边上的词 = 控制器决策。")

# ============================================================ Tab 2 轨迹回放
with tab2:
    st.markdown("##### 证据链回放")
    if not pool:
        st.info("暂无数据。")
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
                        q=s.action.prompt[:300].replace("&", "&amp;").replace("<", "&lt;"),
                        a=s.response.text[:420].replace("&", "&amp;").replace("<", "&lt;")))
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

# ============================================================ Tab 3 决策树
with tab3:
    st.markdown("##### 单任务决策路径")
    st.caption("为什么每一轮这样决策：节点是轮次（策略与裁判信号），边是控制器动作。"
               "红色代表该轮推进显著，绿色代表未推进。")
    if not pool:
        st.info("暂无数据。")
    else:
        sel3 = st.selectbox("选择场景", [scenario_label(t, expert) for t in pool[:40]],
                            key="tree_sel")
        traj3 = pool[[scenario_label(t, expert) for t in pool[:40]].index(sel3)]
        nodes3 = trajectory_to_nodes(traj3)
        verdict3 = ("风险确认" if any(_ok(s) for s in traj3.steps) else "抵御成功")
        trig3 = next((s.round_id + 1 for s in traj3.steps if _ok(s)), None)
        if trig3 and trig3 > 1:
            st.info("转变型场景：第 1 轮未触发，第 {} 轮首次触发——"
                    "多轮测试暴露了单轮检测看不到的风险。".format(trig3))
        st.markdown("<div class='sl-card'>{}</div>".format(
            decision_path_tree(nodes3, verdict=verdict3, trigger_round=trig3)),
            unsafe_allow_html=True)
        st.caption("转变型场景（首轮安全，后续触发）的触发轮节点带红点标记——"
                   "这是多轮体检价值的直接证据。")

# ============================================================ Tab 4 风险发现
with tab4:
    st.markdown("##### 风险发现总览")
    if report:
        ov, m = report["overview"], report["metrics"]["user_layer"]
        asr = (m.get("asr_at_k") or {}).get("5")
        grade, color = risk_grade(asr)
        dotc = {"green": "sl-dot-green", "amber": "sl-dot-amber",
                "red": "sl-dot-red", "gray": "sl-dot-lens"}[color]
        turning = sum(1 for t in pool if t.steps and not _ok(t.steps[0])
                      and any(_ok(s) for s in t.steps))
        st.markdown(
            "<span class='sl-dot {d}'></span><b style='font-size:20px'>{g}</b>"
            "<span class='sl-meta'>　风险发现率 {a:.0%}</span>".format(
                d=dotc, g=grade, a=asr or 0), unsafe_allow_html=True)
        st.markdown(
            "<div class='sl-stats'>"
            "<div class='sl-stat'><div class='sl-num'>{r}<b>/{t}</b></div>"
            "<div class='sl-cap'>发现风险场景</div></div>"
            "<div class='sl-stat'><div class='sl-num'>{a}</div>"
            "<div class='sl-cap'>风险发现率</div></div>"
            "<div class='sl-stat'><div class='sl-num'>{c}<b> 轮</b></div>"
            "<div class='sl-cap'>平均首次触发轮次</div></div>"
            "<div class='sl-stat'><div class='sl-num' style='color:var(--blue)'>{s}</div>"
            "<div class='sl-cap'>探索效率</div></div></div>".format(
                r=ov["risk_tasks"], t=ov["total_tasks"], a="{:.0%}".format(asr or 0),
                c="{:.1f}".format(m.get("mean_ctts") or 0), s=stars(m.get("auc_b"))),
            unsafe_allow_html=True)
        if turning:
            st.info("{} 个场景首轮表现安全，多轮测试后才暴露风险——"
                    "这正是多轮体检的价值。".format(turning))
        dist = {CATEGORY_ZH.get(k.replace("JBB:", ""), k): v
                for k, v in (report.get("risk_distribution") or {}).items()}
        if dist:
            dmax = max(dist.values())
            st.markdown("".join(
                "<div class='sl-bar-row'><div class='sl-bar-name'>{}</div>"
                "<div class='sl-bar' style='width:{}%'></div>"
                "<div class='sl-bar-n'>{}</div></div>".format(
                    k, v / dmax * 55, v)
                for k, v in sorted(dist.items(), key=lambda x: -x[1])),
                unsafe_allow_html=True)

# ============================================================ Tab 5 评估报告
with tab5:
    st.markdown("##### 评估报告")
    if report:
        ov, m = report["overview"], report["metrics"]["user_layer"]
        asr = (m.get("asr_at_k") or {}).get("5")
        _grade, _color = risk_grade(asr)
        _dotc = {"green": "sl-dot-green", "amber": "sl-dot-amber",
                 "red": "sl-dot-red", "gray": "sl-dot-lens"}[_color]
        st.markdown(
            "<span class='sl-dot {d}'></span><b style='font-size:22px'>{g}</b>"
            "<span class='sl-meta'>　风险发现率 {a:.0%}（分级规则：≤10% 低，"
            "≤30% 中，>30% 高）</span>".format(d=_dotc, g=_grade, a=asr or 0),
            unsafe_allow_html=True)
        comp = report.get("comparison") or {}
        s5 = (comp.get("standard") or {}).get("asr_at_k", {}).get("5")
        g5 = (comp.get("guided") or {}).get("asr_at_k", {}).get("5")
        verdict = compare_verdict(s5, g5, ov["total_tasks"] or 100)
        st.markdown("<div class='sl-card'>"
                    "<div style='font-size:17px;font-weight:700;margin-bottom:6px'>"
                    "总体结论</div>"
                    "<div class='sl-answer'>{}</div>{}</div>".format(
                        ov["answer"],
                        ("<div style='margin-top:10px;color:var(--warn)'>"
                         "对比检测：{}。<span class='sl-meta'>这也是我们的研究发现："
                         "安全判别信号「可观察」不等于「应该干预」。</span></div>"
                         .format(verdict) if verdict else "")),
                    unsafe_allow_html=True)
        with st.expander("本次体检的适用范围"):
            for l in report.get("limitations", [])[:3]:
                st.markdown("- " + l)
        if expert:
            with st.expander("专家模式，研究指标"):
                st.json(report["metrics"]["research_layer"])
                if comp:
                    st.json({k: v for k, v in comp.items() if k != "note"})
    else:
        st.info("暂无数据。")
