# -*- coding: utf-8 -*-
"""构建 Judge 校准集 D_cal（V0.3 设计 §20/§41-9）。

从 Stage 1A 轨迹（已含 Judge 与 E 标签）中分层抽取 response，
供 J_f 与 E 的一致性分析及人工 audit。
用法：
    python scripts/build_calibration_set.py outputs/evaluations/stage1a_smoke_C3.jsonl \
        --size 100 --out data/calibration/d_cal.jsonl
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory.trajectory_store import TrajectoryStore


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trajectories", nargs="+", help="已评估的轨迹 JSONL")
    parser.add_argument("--size", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/calibration/d_cal.jsonl")
    args = parser.parse_args()

    trajs = []
    for p in args.trajectories:
        trajs.extend(TrajectoryStore.load(p))
    # 按 Judge outcome 分层（明确拒绝/部分拒绝/模糊执行/部分执行/明显执行）
    strata = {}
    for t in trajs:
        for s in t.steps:
            key = s.judge_output.outcome or "UNKNOWN"
            strata.setdefault(key, []).append({
                "condition_id": t.condition_id,
                "task_id": t.task.task_id,
                "harm_category": t.task.harm_category,
                "round_id": s.round_id,
                "strategy": s.action.strategy,
                "prompt": s.action.prompt,
                "response": s.response.text,
                "judge_outcome": s.judge_output.outcome,
                "judge_jailbreak": s.judge_output.jailbreak_score,
                "evaluator_success": bool(
                    s.external_evaluation and s.external_evaluation.success),
                "evaluator_outcome": (
                    s.external_evaluation.outcome if s.external_evaluation else None),
            })
    rng = random.Random(args.seed)
    per_stratum = max(1, args.size // max(1, len(strata)))
    sampled = []
    for key, items in sorted(strata.items()):
        rng.shuffle(items)
        sampled.extend(items[:per_stratum])
    rng.shuffle(sampled)
    sampled = sampled[:args.size]

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for rec in sampled:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print("wrote {} calibration samples -> {} (strata: {})".format(
        len(sampled), args.out,
        {k: min(len(v), per_stratum) for k, v in sorted(strata.items())}))


if __name__ == "__main__":
    main()
