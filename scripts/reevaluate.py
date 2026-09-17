# -*- coding: utf-8 -*-
"""离线重评（V0.3-J 审计后）：用修复后的 Evaluator 重评已冻结的响应。

用法：python scripts/reevaluate.py outputs/trajectories/<exp>_C1.jsonl [more.jsonl ...]
- 备份原文件为 .bak
- 以 goal 为基准重跑 StrongREJECT，覆写 external_evaluation / success / final_evaluation
- 重算 trajectory.cost 并打印新旧指标对比
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.cost import summarize_trajectory
from engine.factory import build_evaluator
from evaluation.metrics import condition_summary
from evaluation.offline_evaluator import OfflineEvaluator
from memory.trajectory_store import TrajectoryStore
from utils.io import load_yaml
from utils.logging import setup_logging


def main() -> None:
    setup_logging()
    cfg = load_yaml("configs/hardware/rtx4060_8g_r2.yaml")
    evaluator = build_evaluator(cfg)   # score_reference=goal（默认）
    offline = OfflineEvaluator(evaluator, output_dir="outputs/evaluations_reeval",
                               disagreement_dir="outputs/disagreement_reeval")

    paths = sys.argv[1:]
    if not paths:
        raise SystemExit("usage: reevaluate.py <traj.jsonl> [...]")
    budget = 0
    grouped = {}
    for path in paths:
        trajs = TrajectoryStore.load(path)
        if not trajs:
            print("skip empty:", path)
            continue
        b = max(t.target_queries for t in trajs)
        budget = max(budget, b)
        name = os.path.basename(path).replace(".jsonl", "")
        offline.disagreements = []
        offline.evaluate_all(trajs, name)
        for t in trajs:
            summarize_trajectory(t, include_evaluator=True)
        # 原文件备份后原地覆写（保留全部原始字段 + 新 E 标签）
        os.replace(path, path + ".bak")
        from memory.trajectory_store import TrajectoryStore as TS
        store = TS()
        for t in trajs:
            store.save(t, name)
        grouped[name] = trajs

    print("\n==== re-evaluated metrics (score_reference=goal) ====")
    for name, trajs in grouped.items():
        m = condition_summary(trajs, budget)
        print(name, "->", {k: m[k] for k in
                           ("asr_at_k", "auc_b", "mean_ctts", "strategy_switch_rate",
                            "harmful_switch_rate", "effective_strategy_switch_rate")})


if __name__ == "__main__":
    main()
