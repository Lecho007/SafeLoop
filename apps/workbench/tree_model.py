# -*- coding: utf-8 -*-
"""决策树节点模型（纯函数，无 streamlit 依赖 —— GUI 与单测共用）。

两个数据源归一化到同一"树节点/边"模型：
  trajectory steps（control_log/routing/advancement/strategy）
  实况 events.jsonl（run_live_session.py 的事件流）
Tab 1（实况）与 Tab 3（回放）共用组件。
"""
from typing import Any, Dict, List, Optional

# 信号 → 语义色（与设计令牌对应，由 UI 层映射到具体 hex）
SIGNAL_OF_ADVANCEMENT = {"STRONG": "risk", "PARTIAL": "warn", "NONE": "safe"}

# 决策动作中文化（实况事件枚举 → 人话）
ACTION_ZH = {"KEEP": "保持", "REFINE": "细化", "SWITCH": "换策略",
             "REALIGN": "回正", "UNCERTAIN": "不确定"}
EVENT_ACTION_KEYS = ("action", "decision")


def _signal_from_event(ev: Dict[str, Any]) -> Optional[str]:
    sig = ev.get("signal") or ""
    if "GOAL_ADVANCEMENT" in sig and "NO_GOAL" not in sig:
        return "risk"
    if "PARTIAL" in sig or "CONTROVERSIAL" in sig or "UNSAFE" == sig:
        return "warn"
    if sig in ("NO_GOAL_ADVANCEMENT", "SAFE", "REFUSAL", "NO_UNSAFE"):
        return "safe"
    out = (ev.get("outcome") or "").upper()
    if "FULL_COMPLIANCE" in out or "LIKELY" in out:
        return "risk"
    if "PARTIAL" in out:
        return "warn"
    if "REFUSAL" in out or "SAFE" in out:
        return "safe"
    return None


def trajectory_to_nodes(traj) -> List[Dict[str, Any]]:
    """trajectory（AttackTrajectory 对象）→ 节点/边列表（回放态，全路径）。"""
    nodes = []
    for s in traj.steps:
        routing = s.action.metadata.get("routing", {}) or {}
        adv = s.judge_output.metadata.get("advancement")
        nodes.append({
            "round": s.round_id + 1,
            "strategy": s.action.strategy,
            "signal": SIGNAL_OF_ADVANCEMENT.get(adv),
            "action": (s.feedback.adaptation_action
                       if s.feedback else None),
            "success": bool(s.external_evaluation
                            and s.external_evaluation.success),
        })
    return nodes


def events_to_tree(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """实况事件流 → 树状态（根信息 + 逐轮节点 + 活跃相位）。"""
    root = {"task_id": None, "domain": None, "done": False,
            "success": None, "verdict": None}
    rounds: Dict[int, Dict[str, Any]] = {}
    active = None
    for ev in events:
        et = ev.get("type")
        if et == "session_started":
            root["task_id"] = ev.get("task_id")
            cat = (ev.get("harm_category") or "")
            root["domain"] = ("goal" if "goal" in cat.lower()
                              or cat in ("JBB:Economic harm", "JBB:Expert advice",
                                         "JBB:Government decision-making")
                              else "content")
        elif et == "round_started":
            r = ev.get("round", 1)
            rounds.setdefault(r, {"round": r, "strategy": None, "signal": None,
                                  "action": None, "state": "red"})
            active = r
        elif et in ("red_message", "role_working"):
            r = ev.get("round") or active
            if r:
                rounds.setdefault(r, {"round": r})
                rounds[r]["state"] = "red"
        elif et == "judge_message":
            r = ev.get("round") or active
            if r:
                rounds.setdefault(r, {"round": r})
                rounds[r]["signal"] = _signal_from_event(ev)
                rounds[r]["judge"] = ev.get("selected_judge")
                rounds[r]["state"] = "judged"
        elif et == "control_message":
            r = ev.get("round") or active
            act = next((ev.get(k) for k in EVENT_ACTION_KEYS if ev.get(k)), None)
            if r and act:
                rounds.setdefault(r, {"round": r})
                rounds[r]["action"] = act
                rounds[r]["state"] = "decided"
        elif et == "session_complete":
            root["done"] = True
            root["success"] = bool(ev.get("success"))
    ordered = [rounds[r] for r in sorted(rounds)]
    if root["success"] is not None:
        root["verdict"] = ("风险确认" if root["success"] else "抵御成功")
    return {"root": root, "rounds": ordered, "active": active}


def node_css_state(node: Dict[str, Any]) -> str:
    """节点视觉状态：新出现(red) → 已判定(judged) → 已决策(decided)。"""
    return node.get("state") or "decided"
