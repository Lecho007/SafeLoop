# -*- coding: utf-8 -*-
"""Replay：不调用 Target，用已保存响应重放 Judge/Feedback/Reward 并重算指标。

用法：
    python scripts/replay_trajectory.py outputs/trajectories/<exp>_C3.jsonl \
        [--level structured] [--config configs/stage1.yaml]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.factory import RunnerBundle
from engine.replay import replay_records
from evaluation.metrics import condition_summary
from memory.trajectory_store import TrajectoryStore
from utils.io import load_yaml
from utils.logging import setup_logging


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser()
    parser.add_argument("trajectories", help="JSONL 轨迹文件")
    parser.add_argument("--level", default="structured",
                        choices=["none", "score", "outcome", "structured"],
                        help="重放时使用的反馈级别（可不同于原始条件，用于 Feedback Ablation）")
    parser.add_argument("--config", default="configs/stage1.yaml")
    args = parser.parse_args()

    cfg = load_yaml(args.config)
    bundle = RunnerBundle(cfg, args.config)
    trajs = TrajectoryStore.load(args.trajectories)
    if not trajs:
        raise SystemExit("no trajectories in {}".format(args.trajectories))

    orig_cond = trajs[0].condition_id
    budget = max(t.target_queries for t in trajs)

    print("replay {} trajectories (orig condition={}, budget={}) with feedback_level='{}'".format(
        len(trajs), orig_cond, budget, args.level))
    replayed = replay_records(
        trajs, bundle.judge, bundle.feedback_builder, args.level, bundle.reward_config)

    print("\n==== stored metrics ====")
    print(condition_summary(trajs, budget))
    print("\n==== replayed metrics (level={}) ====".format(args.level))
    print(condition_summary(replayed, budget))
    print("\nreplay keeps prompts/responses fixed; judge/feedback/reward are recomputed.")


if __name__ == "__main__":
    main()
