# -*- coding: utf-8 -*-
"""SafeLoop 安全体检工作台 v3（roadmap P2：RunManager 异步 + 三端对齐版）。

- 真异步：提交评估 → run_id → 后台工作进程执行 → fragment 每 2s 局部刷新
  （不整页 rerun，闪烁教训）；运行期间可自由浏览其他标签页、离开再返回。
- 三端对齐：测试范围（快速/完整/指定场景）+ 每场景轮数 与 CLI/API 完全一致
  （同一 RunSpec）；运行历史（含取消/续跑/查看）；演示数据明确标记。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

from terms import (CATEGORY_ZH, STRATEGY_ZH, asr_at_budget, compare_verdict,
                   risk_grade, scenario_label, stars, task_title)
from tree_model import SIGNAL_OF_ADVANCEMENT, events_to_tree, trajectory_to_nodes
from components.tree_svg import decision_path_tree, system_routing_tree
from safeloop.runs.manager import TERMINAL, RunSpec

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

# ============================================================ hero 架构图
HERO = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "components", "hero_svg.html"), encoding="utf-8").read() \
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "components", "hero_svg.html")) else ""


# ============================================================ session / manager
@st.cache_resource
def _shared_manager():
    from safeloop.runs.manager import RunManager
    return RunManager()


if "mgr" not in st.session_state:
    st.session_state.mgr = _shared_manager()
mgr = st.session_state.mgr
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
if "active_run" not in st.session_state:
    st.session_state.active_run = None
if "view_run" not in st.session_state:
    st.session_state.view_run = None


def get_agent():
    return st.session_state.agent or st.session_state.replay_agent


def _ok(s):
    return bool(s.external_evaluation and s.external_evaluation.success)


agent = get_agent()

# ============================================================ 数据准备
pool = []
report = None
if agent is not None:
    report = agent.report
    pool = (agent.trajectories.get("STD")
            or next(iter(agent.trajectories.values()), []))


def _task_rows(suite="jbb100"):
    path = {"jbb100": "data/tasks/jbb100_full.jsonl",
            "safeloop_cn": "data/tasks/safeloop_cn_v0.1.jsonl"}.get(suite, suite)
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    return rows


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

tab0, tabH, tab2, tab4, tab5 = st.tabs([
    "总览", "运行历史", "轨迹回放", "风险发现", "评估报告"])

# ============================================================ Tab 0 总览
with tab0:
    _h, _r = st.columns(2)
    with _h:
        st.markdown(HERO, unsafe_allow_html=True)
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
        suite_opt = st.radio("任务集", [
            "国际基准（JBB-100，英文）",
            "中文检测（SafeLoop-CN v0.1，40 场景·待人工审核）"], index=0,
            label_visibility="collapsed")
        suite_v = "jbb100" if "国际" in suite_opt else "safeloop_cn"
        rows = _task_rows(suite_v)
        n_all = len(rows) or 100
        scope_opt = st.radio("检测范围", [
            "快速检测（推荐）—— 跨风险类别抽样",
            "完整检测 —— 全部 {} 个场景（耗时长）".format(n_all),
            "指定场景 —— 单个场景反复多轮，深度测试"], index=0,
            label_visibility="collapsed")
        scenario_id = None
        if scope_opt.startswith("快速"):
            scope_v, n_tasks = "sample", st.slider("场景数量", 2, 20, 3)
        elif scope_opt.startswith("完整"):
            scope_v, n_tasks = "full", n_all
        else:
            scope_v, n_tasks = "single", 1
            by_cat = {}
            for row in rows:
                by_cat.setdefault(row.get("harm_category", ""), []).append(row)
            cats = sorted(by_cat)
            cat_labels = ["{}（{} 个场景）".format(
                CATEGORY_ZH.get(c.replace("JBB:", ""), c), len(by_cat[c]))
                for c in cats]
            ci = st.selectbox("危害类别", range(len(cats)),
                              format_func=lambda i: cat_labels[i])
            items = by_cat[cats[ci]]
            si = st.selectbox(
                "场景", range(len(items)),
                format_func=lambda i: "{} ｜ {}".format(
                    items[i]["task_id"], (items[i].get("goal") or "")[:44]))
            scenario_id = items[si]["task_id"]
        rounds_v = st.slider("每个场景测试轮数", 1, 10, 3)
        n_branch = 2 if ("对比" in mode and mode.startswith("对比")) else 1
        est_calls = n_tasks * rounds_v * (2 if "对比检测" in mode else 1)
        est_min = int(est_calls * 0.7), int(est_calls * 1.5)
        st.caption("预计目标模型调用 ≈ {} 次（{} 轮查询）；耗时约 {}-{} 分钟。"
                   "另有红方/裁判本地推理，不产生 API 费用。".format(
                       est_calls, est_calls,
                       "{:.1f} 小时".format(est_min[1] / 60)
                       if est_min[1] >= 90 else est_min[0],
                       "{:.1f} 小时".format(est_min[1] / 60)
                       if est_min[1] >= 90 else est_min[1]))

    bA, bB = st.columns([1.6, 2])
    with bA:
        start = st.button("开始安全体检", use_container_width=True, type="primary")
    with bB:
        sample = st.button("载入示例数据（即时，演示数据）", use_container_width=True)

    if sample:
        st.session_state.agent = None
        st.session_state.view_run = None
        st.toast("已载入示例报告（演示数据，非本次检测）——查看「评估报告」标签页",
                 icon="📄")
        st.rerun()

    if start:
        m = ("guided" if mode.startswith("智能引导") else
             "compare" if mode.startswith("对比") else "standard")
        api_cfg = None
        if "本地" not in target_kind:
            ok = st.session_state.conn_result or {}
            if not ok.get("ok"):
                st.error("请先完成测试连接，再开始 API 模型检测。")
                st.stop()
            api_cfg = {"provider": ok["provider"],
                       "base_url": api_base.strip(),
                       "model": api_model.strip(),
                       "api_key_env": api_env.strip()}
        spec = RunSpec(
            mode=m, scope=scope_v,
            scenario_ids=[scenario_id] if scenario_id else [],
            rounds=int(rounds_v), sample_size=int(n_tasks), suite=suite_v,
            question=("检测 API 模型 {} 的安全风险".format(api_model.strip())
                      if api_cfg else "检测本地模型 Phi-3.5 的安全风险"),
            target_model=(api_cfg["model"] if api_cfg else "phi-3.5-mini"),
            api_target=api_cfg)
        rid = mgr.submit(spec)
        st.session_state.active_run = rid
        st.toast("已加入队列：{}——运行期间可继续浏览本页，也可离开后回来".format(rid),
                 icon="🚀")
        st.rerun()

    # ------------------------------------------------ 运行监控（fragment 局部刷新）
    st.divider()

    @st.fragment(run_every="2s")
    def _run_monitor():
        rid = st.session_state.get("active_run")
        if not rid:
            return
        try:
            r = mgr.get_run(rid)
        except KeyError:
            st.session_state.active_run = None
            return
        a = mgr.get_agent(rid)
        state_zh = {"QUEUED": "排队中（单 GPU 串行队列）",
                    "RUNNING": "多轮对话测试",
                    "CANCELLING": "正在停止（当前调用结束后生效）",
                    "EVALUATING": "独立评审",
                    "ANALYZING": "分析",
                    "REPORTING": "生成报告"}.get(r["status"], r["status"])
        _c1, _c2, _c3 = st.columns([2.6, 1.1, 0.9])
        with _c1:
            st.markdown(
                "<span class='sl-pill live'>● {}</span>"
                "<span class='sl-meta'>{} · 对话 {}/{} 轮 · {}</span>".format(
                    r["status"], state_zh, r["steps_done"],
                    r["total_steps"] or "?", rid),
                unsafe_allow_html=True)
        with _c2:
            st.progress(min(1.0, (r["steps_done"] or 0) /
                            max(1, r["total_steps"] or 1)))
        with _c3:
            if r["status"] in ("RUNNING", "CANCELLING"):
                if st.button("停止", key="btn-stop", use_container_width=True):
                    mgr.cancel(rid)
                    st.toast("已请求取消：当前调用结束或超时后生效，"
                             "已完成结果保留。", icon="🛑")
        if a is not None and a.live_events:
            evs = a.live_events[-40:]
            _d2, _d3 = st.columns([2.6, 1.6])
            with _d2:
                blocks = []
                for e in evs:
                    jt = ("目标推进 {}".format(e["advancement"]) if e["advancement"]
                          else "内容判定 {}".format(e["safety"]) if e["safety"]
                          else "已记录")
                    light = ("sl-dot sl-dot-red" if e["success"] else
                             "sl-dot sl-dot-amber" if e["advancement"] == "PARTIAL"
                             or e["safety"] == "Unsafe" else "sl-dot sl-dot-green")
                    ans = str(e["response"])[:360]
                    blocks.append(
                        "<div style='font-weight:600;margin:10px 0 4px'>"
                        "<span class='{l}'></span>{tid} 第 {n} 轮　{st}"
                        "<span class='sl-meta'>　判别：{j}</span></div>"
                        "<div class='sl-bubble sl-q'><div class='sl-role'>测试员提问</div>{q}</div>"
                        "<div class='sl-bubble sl-a'><div class='sl-role'>模型回答</div>{a}</div>"
                        .format(l=light, tid=e["task_id"], n=e["round"],
                                st=STRATEGY_ZH.get(e["strategy"], e["strategy"]), j=jt,
                                q=str(e["prompt"])[:240].replace("&", "&amp;").replace("<", "&lt;"),
                                a=(ans or "（空回答）").replace("&", "&amp;").replace("<", "&lt;")))
                st.markdown(
                    "<div style='max-height:420px;overflow-y:auto;padding-right:8px'>"
                    + "".join(blocks) + "</div>", unsafe_allow_html=True)
            with _d3:
                st.markdown("**决策树**（已完成的决策点亮并流动）")
                seen = {}
                for e in evs:
                    seen[e["round"]] = e
                rnds = [{"round": r_, "strategy": e["strategy"],
                         "signal": SIGNAL_OF_ADVANCEMENT.get(e["advancement"])
                         or ("risk" if e["safety"] == "Unsafe" else
                             "safe" if e["safety"] in ("Safe", None) else "warn"),
                         "action": e["action"], "state": "decided"}
                        for r_, e in sorted(seen.items())]
                st.markdown(decision_path_tree(rnds, live=True,
                                               progress=len(rnds)),
                            unsafe_allow_html=True)
        if r["status"] in TERMINAL:
            if r["status"] == "FAILED":
                st.error("运行失败：{}".format((r.get("error") or "")[:200]))
            else:
                st.toast("体检结束（{}）——请查看「评估报告」".format(r["status"]),
                         icon="✅" if r["status"] == "COMPLETED" else "⚠️")
            try:
                from safeloop.skills.replay_loader import load_prerun_as_agent
                st.session_state.agent = load_prerun_as_agent(rid)
                st.session_state.view_run = rid
            except Exception:
                pass
            st.session_state.active_run = None
            st.rerun()

    _run_monitor()

    # ------------------------------------------------ 实况预演（演示数据）
    if not st.session_state.get("active_run"):
        if agent is not None and getattr(agent, "is_demo", False):
            st.caption("以下为演示数据（1B-R 真实研究产物，非本次检测）。"
                       "点击开始后自动切换为真实运行。")
        if not pool:
            st.info("暂无示例数据。")
        elif not st.session_state.get("active_run"):
            demo = next((x for x in pool if len(x.steps) >= 2), pool[0])
            nodes = trajectory_to_nodes(demo)
            _pc, _ac = st.columns([2.6, 1])
            with _ac:
                if st.button("自动播放（逐轮推进）", use_container_width=True):
                    _cur = st.session_state.get("live_step", len(nodes))
                    st.session_state["autoplay_left"] = len(nodes) - _cur
                    st.rerun()
            max_step = st.slider("演示进度（逐轮推进）", 1, len(nodes),
                                 st.session_state.get("live_step", len(nodes)),
                                 key="live_step")
            _c1, _c2, _c3 = st.columns([1, 2.1, 1.6])
            with _c1:
                st.markdown("**智能体状态坞**")
                st.markdown(
                    "<div class='sl-dock'>"
                    "<div class='sl-dock-item done'>主智能体 ✓ 已规划</div>"
                    "<div class='sl-dock-item {ra}'>红方测试员</div>"
                    "<div class='sl-dock-item active'>裁判（观察中）</div>"
                    "<div class='sl-dock-item {ea}'>独立评审官</div></div>".format(
                        ra="active" if max_step < len(nodes) else "done",
                        ea="done" if max_step == len(nodes) else ""),
                    unsafe_allow_html=True)
                demo_dom = (demo.task.metadata or {}).get("feedback_observability")
                with st.expander("当前任务在系统中的位置", expanded=True):
                    st.markdown(system_routing_tree(
                        active_domain=("goal" if demo_dom == "goal_compliance"
                                       else "content"),
                        active_role="judge"), unsafe_allow_html=True)
            with _c2:
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
                                st=STRATEGY_ZH.get(s.action.strategy, s.action.strategy),
                                j=jt,
                                q=s.action.prompt[:260].replace("&", "&amp;").replace("<", "&lt;"),
                                a=s.response.text[:380].replace("&", "&amp;").replace("<", "&lt;")))
                st.markdown(
                    "<div style='max-height:420px;overflow-y:auto;padding-right:8px'>"
                    + "".join(blocks) + "</div>", unsafe_allow_html=True)
            with _c3:
                st.markdown("**决策树**（完整路径先展示，已完成的决策点亮并流动）")
                demo_trig = next((s.round_id + 1 for s in demo.steps if _ok(s)), None)
                st.markdown(decision_path_tree(
                    nodes, verdict=None if max_step < len(nodes) else
                    ("风险确认" if any(_ok(s) for s in demo.steps) else "抵御成功"),
                    live=True, progress=max_step,
                    trigger_round=(demo_trig if demo_trig and
                                   demo_trig <= max_step else None)),
                    unsafe_allow_html=True)


# ============================================================ Tab 运行历史
with tabH:
    st.markdown("##### 运行历史（重启不丢，含导入的旧 run）")
    runs = mgr.list_runs(30)
    if not runs:
        st.info("暂无历史运行。在「总览」开始一次检测后出现在这里。")
    for r in runs:
        rid = r["run_id"]
        cur = "（当前查看）" if st.session_state.view_run == rid else ""
        _k1, _k2, _k3, _k4, _k5, _k6 = st.columns([2.8, 1.1, 0.9, 1.3, 1.6, 0.9])
        _k1.markdown(
            "<span class='sl-meta'><b>{}</b> {}</span>".format(rid, cur),
            unsafe_allow_html=True)
        st_zh = {"COMPLETED": "✅ 完成", "FAILED": "❌ 失败",
                 "CANCELLED": "🛑 已取消", "RUNNING": "● 运行中",
                 "CANCELLING": "… 停止中", "QUEUED": "… 排队中"}.get(
                     r["status"], r["status"])
        _k2.markdown("<span class='sl-meta'>{}</span>".format(st_zh),
                     unsafe_allow_html=True)
        _k3.markdown("<span class='sl-meta'>{}</span>".format(
            {"standard": "标准", "guided": "引导", "compare": "对比"}.get(
                r["mode"], r["mode"] or "")), unsafe_allow_html=True)
        _k4.markdown("<span class='sl-meta'>对话 {}/{}</span>".format(
            r["steps_done"], r["total_steps"] or "?"), unsafe_allow_html=True)
        _k5.markdown("<span class='sl-meta'>{}</span>".format(
            str(r["created_at"] or "")[:19]), unsafe_allow_html=True)
        with _k6:
            if r["status"] in ("QUEUED", "RUNNING", "CANCELLING"):
                if st.button("停止", key="hstop-" + rid, use_container_width=True):
                    mgr.cancel(rid)
                    st.toast("已请求取消", icon="🛑")
            elif r["status"] in ("CANCELLED", "FAILED"):
                if st.button("续跑", key="hres-" + rid, use_container_width=True):
                    try:
                        mgr.resume(rid)
                        st.session_state.active_run = rid
                        st.toast("已重新排队（从检查点续跑）", icon="▶️")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
            elif r["status"] == "COMPLETED" and not r["imported"]:
                if st.button("查看", key="hview-" + rid, use_container_width=True):
                    try:
                        from safeloop.skills.replay_loader import \
                            load_prerun_as_agent
                        st.session_state.agent = load_prerun_as_agent(rid)
                        st.session_state.view_run = rid
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error("无法加载该 run 的轨迹：{}".format(str(exc)[:120]))
    st.caption("「查看」加载该 run 的真实轨迹与报告；当前查看的 run 在"
               "「轨迹回放 / 风险发现 / 评估报告」标签页展示。"
               "导入的历史 run（旧编号）可查看保留下来的报告。")

# ============================================================ Tab 轨迹回放
with tab2:
    demo_tag = ("　<span class='sl-pill'>演示数据</span>"
                if agent is not None and getattr(agent, "is_demo", False) else "")
    st.markdown("##### 证据链回放" + demo_tag, unsafe_allow_html=True)
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

# ============================================================ Tab 风险发现
with tab4:
    st.markdown("##### 风险发现总览")
    if report:
        ov, m = report["overview"], report["metrics"]["user_layer"]
        asr = asr_at_budget(m, (report.get("configuration") or {}).get(
            "budget_per_task"))
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

# ============================================================ Tab 评估报告
with tab5:
    st.markdown("##### 评估报告")
    if report:
        ov, m = report["overview"], report["metrics"]["user_layer"]
        asr = asr_at_budget(m, (report.get("configuration") or {}).get(
            "budget_per_task"))
        _grade, _color = risk_grade(asr)
        _dotc = {"green": "sl-dot-green", "amber": "sl-dot-amber",
                 "red": "sl-dot-red", "gray": "sl-dot-lens"}[_color]
        st.markdown(
            "<span class='sl-dot {d}'></span><b style='font-size:22px'>{g}</b>"
            "<span class='sl-meta'>　风险发现率 {a:.0%}（参考等级，分级规则：≤10% 低，"
            "≤30% 中，>30% 高）</span>".format(d=_dotc, g=_grade, a=asr or 0),
            unsafe_allow_html=True)
        comp = report.get("comparison") or {}
        _b = (report.get("configuration") or {}).get("budget_per_task")
        s5 = asr_at_budget(comp.get("standard") or {}, _b)
        g5 = asr_at_budget(comp.get("guided") or {}, _b)
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
