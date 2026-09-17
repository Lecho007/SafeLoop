# -*- coding: utf-8 -*-
"""断点续跑检查点（V0.3-B）：每个 round 完成后原子落盘全部 episode 状态。

用途：10 小时级实验（如 Stage 1B-A）中断后 --resume 续跑，不丢已完成轮次。
"""
import json
import os
from typing import Any, Dict, List, Optional

from core.schemas import (
    AttackStep,
    AttackTrajectory,
    Feedback,
    SafetyTask,
)


def slot_to_payload(condition_id: str, task: SafetyTask, state, traj: AttackTrajectory,
                    done: bool) -> Dict[str, Any]:
    return {
        "condition_id": condition_id,
        "task": task.to_dict(),
        "trajectory_id": traj.trajectory_id,
        "done": done or state.done,
        "steps": [s.to_dict() for s in state.history],
        "state": {
            "round_id": state.round_id,
            "target_queries_used": state.target_queries_used,
            "current_strategy": state.current_strategy,
            "last_feedback": state.last_feedback.to_dict() if state.last_feedback else None,
        },
    }


def save_checkpoint(path: str, payloads: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "slots": payloads}, f, ensure_ascii=False)
    os.replace(tmp, path)  # 原子替换，崩溃时不产生半写文件


def load_checkpoint(path: str) -> Optional[List[Dict[str, Any]]]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") != 1:
            return None
        return data["slots"]
    except (json.JSONDecodeError, OSError):
        return None  # 半写/损坏文件（原子替换下不应出现，双保险）


def rebuild_from_payload(payload: Dict[str, Any], budget: int):
    """恢复 (task, state, trajectory, done)。coordinator 由调用方重建。"""
    task = SafetyTask.from_dict(payload["task"])
    steps = [AttackStep.from_dict(s) for s in payload["steps"]]
    st = payload["state"]
    from core.schemas import AttackState
    state = AttackState(
        task=task,
        target_id=task.metadata.get("target_id", "default-target"),
        round_id=int(st["round_id"]),
        target_queries_used=int(st["target_queries_used"]),
        target_query_budget=budget,
        current_strategy=st.get("current_strategy", ""),
        history=steps,
        last_feedback=(
            Feedback.from_dict(st["last_feedback"]) if st.get("last_feedback") else None),
        stop_reason="budget_exhausted" if payload.get("done") else None,
    )
    traj = AttackTrajectory(
        trajectory_id=payload["trajectory_id"],
        experiment_id="",
        condition_id=payload["condition_id"],
        task=task,
        target_id=state.target_id,
        steps=list(steps),  # 拷贝：与 state.history 分离，避免双写
        target_queries=len(steps),
    )
    return task, state, traj, bool(payload.get("done"))
