# -*- coding: utf-8 -*-
"""SafeLoop Workbench（v1.0 设计 §二十三~§二十六）：四页 GUI。

启动：streamlit run apps/workbench/app.py
页面：① 首页（自然语言输入+模式选择） ② 运行页（三栏多智能体协作实时视图）
     ③ 轨迹页（goal→rounds→judge→E 证据链） ④ 报告页（结论/指标/案例/对比）
演示模式：回放 1B-R 预跑数据（零 GPU 秒级）或现场小子集真跑。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import streamlit as st

st.set_page_config(page_title="SafeLoop", page_icon="🛡️", layout="wide")

# ---------------------------------------------------------------- session
if "agent" not in st.session_state:
    st.session_state.agent = None
if "replay_agent" not in st.session_state:
    try:
        from safeloop.skills.replay_loader import load_prerun_as_agent
        st.session_state.replay_agent = load_prerun_as_agent("stage1b_r_4060")
    except Exception:
        st.session_state.replay_agent = None


def get_agent():
    a = st.session_state.agent or st.session_state.replay_agent
    return a


# ================================================================ 首页
st.markdown(
    "<h1 style='text-align:center'>🛡️ SafeLoop</h1>"
    "<p style='text-align:center;color:#666'>面向大语言模型的多智能体闭环安全评估系统"
    "　·　Question → Plan → Explore → Observe → Evaluate → Explain</p>",
    unsafe_allow_html=True)

with st.form("eval_form"):
    question = st.text_area(
        "你希望评估什么？", "评估 Phi-3.5 在安全风险任务上的表现", height=90)
    col1, col2, col3 = st.columns(3)
    with col1:
        target = st.selectbox("Target Model", ["Phi-3.5-mini", "Mistral-7B", "本地模型"])
    with col2:
        mode = st.radio("Evaluation", ["Standard", "Guided", "Compare"],
                        help="Standard=Judge 观察不干预（默认）｜Guided=反馈控制（实验）"
                             "｜Compare=双模式对比")
    with col3:
        demo = st.selectbox("运行方式", ["回放预跑数据（秒级）", "现场真跑（小子集）"])
        max_tasks = st.slider("演示任务数（现场跑）", 2, 10, 3)
    submitted = st.form_submit_button("🚀 Start Evaluation", use_container_width=True)

if submitted:
    if "回放" in demo:
        st.session_state.agent = None  # 使用 replay_agent
        st.rerun()
    else:
        from safeloop.agents.main_agent import SafeLoopMainAgent
        agent = SafeLoopMainAgent()
        agent.submit(question, target_model=target.lower(), mode=mode.lower(),
                     max_tasks=max_tasks, budget_per_task=3)
        st.session_state.agent = agent
        progress = st.progress(0.0, "评估运行中…")
        report = agent.run()
        progress.progress(1.0, "完成")
        st.rerun()

agent = get_agent()

# ================================================================ 运行页
if agent:
    st.divider()
    st.subheader("多智能体协作视图")
    status = agent.status()
    cmap = {"IDLE": "off", "PLANNING": "off", "READY": "off", "RUNNING": "run",
            "EVALUATING": "run", "ANALYZING": "run", "REPORTING": "run",
            "COMPLETED": "done", "FAILED": "err", "CANCELLED": "err"}
    phase = {"IDLE": "待命", "PLANNING": "规划中", "READY": "就绪",
             "RUNNING": "红方测试中", "EVALUATING": "独立评估中",
             "ANALYZING": "证据分析中", "REPORTING": "生成报告中",
             "COMPLETED": "已完成", "FAILED": "失败", "CANCELLED": "已取消"}

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**SafeLoop Main Agent**")
        st.success("✓ 评估计划已生成" if agent.plan else "○ 待命")
        st.info("状态：{}".format(phase.get(agent.state, agent.state)))
        n = sum(len(v) for v in agent.trajectories.values()) or 100
        st.metric("任务", "{}/100".format(min(n, 100)))
    with c2:
        st.markdown("**Red Agent / Target**")
        if agent.trajectories:
            st.success("✓ 测试完成（{} 轨迹）".format(
                sum(len(v) for v in agent.trajectories.values())))
        else:
            st.warning("● 测试中…")
    with c3:
        st.markdown("**Judge Agents / Evaluator**")
        st.success("✓ Content Judge（Qwen3Guard）")
        st.success("✓ Goal Judge（Advancement V3）")
        st.success("✓ Independent Evaluator（StrongREJECT，闭环外）")

    # 事件流（最近）
    if agent.events:
        with st.expander("Agent 事件流"):
            for ev in agent.events[-12:]:
                st.code("{}  {}".format(ev.get("kind"), json.dumps(
                    {k: v for k, v in ev.items()
                     if k not in ("kind", "ts", "plan", "state")}, ensure_ascii=False)))

# ================================================================ 轨迹页
if agent and agent.trajectories:
    st.divider()
    st.subheader("攻击轨迹（证据链）")
    all_trajs = [(b, t) for b, ts in agent.trajectories.items() for t in ts]
    task_ids = ["{} · {}".format(b, t.task.task_id) for b, t in all_trajs]
    sel = st.selectbox("选择任务", task_ids)
    if sel:
        b, idx = sel.split(" · ")
        traj = next(t for t in agent.trajectories[b] if t.task.task_id == idx)
        st.markdown("**Original Goal**（固定）")
        st.info(traj.task.goal)
        for s in traj.steps:
            e_ok = (s.external_evaluation.success
                    if s.external_evaluation else None)
            head = "Round {} · {} · Judge: {}".format(
                s.round_id, s.action.strategy,
                s.judge_output.metadata.get("advancement")
                or s.judge_output.metadata.get("safety")
                or s.judge_output.outcome or "-")
            with st.expander(head + (" · E: {}".format(
                    "✅ 风险确认" if e_ok else "—"))):
                st.markdown("**Prompt（Red 生成）**")
                st.code(s.action.prompt[:400])
                st.markdown("**Target Response**")
                st.code(s.response.text[:400])
                st.caption("judge_invoked={} feedback_exposed={} seeds=({},{})".format(
                    s.action.metadata.get("routing", {}).get("judge_invoked"),
                    s.action.metadata.get("routing", {}).get("feedback_exposed_to_red"),
                    s.action.metadata.get("routing", {}).get("red_seed"),
                    s.action.metadata.get("routing", {}).get("target_seed")))

# ================================================================ 报告页
if agent and agent.report:
    st.divider()
    st.subheader("评估报告")
    r = agent.report
    ov = r["overview"]
    st.markdown("#### 结论")
    st.success(ov["answer"])
    k1, k2, k3, k4 = st.columns(4)
    m = r["metrics"]["user_layer"]
    k1.metric("风险任务", "{}/{}".format(ov["risk_tasks"], ov["total_tasks"]))
    k2.metric("ASR@B", "{:.1%}".format((m.get("asr_at_k") or {}).get("5", 0)))
    k3.metric("AUC-B", m.get("auc_b") or 0)
    k4.metric("CTTS", m.get("mean_ctts") or 0)

    st.markdown("#### 风险分布")
    if r["risk_distribution"]:
        st.bar_chart({k.replace("JBB:", ""): v
                      for k, v in r["risk_distribution"].items()})

    st.markdown("#### 代表性案例")
    for c in r["representative_cases"]:
        with st.expander("{} · {}".format(c["task_id"], c["why_representative"])):
            st.write(c["goal"])
            for rd in c["rounds"]:
                st.markdown("- R{} {} → {}".format(
                    rd["round"], rd["strategy"],
                    "✅" if rd["evaluator_success"] else "—"))

    if r.get("comparison"):
        st.markdown("#### Standard vs Guided（Compare）")
        st.json(r["comparison"])

    with st.expander("Limitations（结论边界）"):
        for l in r["limitations"]:
            st.markdown("- " + l)
    with st.expander("Provenance"):
        st.json(r["provenance"])
