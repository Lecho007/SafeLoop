# -*- coding: utf-8 -*-
"""成本核算（V0.3 设计 §14/§39）：Q_G/Q_T/Q_J/Q_E 与 token/重试记账。

约定（各 Adapter 写入的 usage 块）：
    action.metadata["usage"]          = {input_tokens, output_tokens, retries, retry_reason}
    response.input/output_tokens       = Target 用量
    judge_output.metadata["usage"]     = Judge 用量
    EvaluationResult.metadata["usage"] = Evaluator 用量（离线阶段补记）
episode_runner 不感知；由 Stage 执行器在合适时机调用 summarize() 聚合。
"""
from typing import Dict, List

from core.schemas import AttackTrajectory


def _usage(meta: Dict) -> Dict:
    u = (meta or {}).get("usage", {}) or {}
    return {
        "input_tokens": int(u.get("input_tokens", 0)),
        "output_tokens": int(u.get("output_tokens", 0)),
        "retries": int(u.get("retries", 0)),
        "retry_reason": u.get("retry_reason"),
    }


def summarize_trajectory(traj: AttackTrajectory, include_evaluator: bool = True) -> Dict:
    red_in = red_out = judge_in = judge_out = eval_in = eval_out = 0
    retries = 0
    latency = 0.0
    for s in traj.steps:
        ru = _usage(s.action.metadata)
        red_in += ru["input_tokens"]; red_out += ru["output_tokens"]
        retries += ru["retries"]
        judge_u = _usage(s.judge_output.metadata)
        judge_in += judge_u["input_tokens"]; judge_out += judge_u["output_tokens"]
        retries += judge_u["retries"]
        latency += s.response.latency
        if include_evaluator and s.external_evaluation is not None:
            eu = _usage(s.external_evaluation.metadata)
            eval_in += eu["input_tokens"]; eval_out += eu["output_tokens"]
    cost = {
        "q_g_red_calls": len(traj.steps),
        "q_t_target_queries": traj.target_queries,
        "q_j_judge_calls": len(traj.steps),
        "q_e_evaluator_calls": sum(
            1 for s in traj.steps if s.external_evaluation is not None
        ) if include_evaluator else 0,
        "red_tokens": red_in + red_out,
        "target_tokens": sum(
            s.response.input_tokens + s.response.output_tokens for s in traj.steps),
        "judge_tokens": judge_in + judge_out,
        "evaluator_tokens": (eval_in + eval_out) if include_evaluator else 0,
        "total_latency_s": round(latency, 4),
        "retries": retries,
    }
    traj.cost = cost
    return cost


def summarize_all(trajectories: List[AttackTrajectory],
                  include_evaluator: bool = True) -> Dict:
    agg: Dict = {}
    for t in trajectories:
        c = summarize_trajectory(t, include_evaluator=include_evaluator)
        for k, v in c.items():
            agg[k] = agg.get(k, 0) + (v if isinstance(v, (int, float)) else 0)
    agg["episodes"] = len(trajectories)
    return agg
