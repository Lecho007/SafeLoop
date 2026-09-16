# -*- coding: utf-8 -*-
"""运行单个 episode（指定条件），并做离线评估与摘要打印。

用法：python scripts/run_episode.py [config] [condition] [task_index]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.factory import RunnerBundle, load_tasks
from experiments.conditions import STAGE1_CONDITIONS
from utils.io import load_yaml
from utils.logging import setup_logging


def main() -> None:
    setup_logging()
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/stage1.yaml"
    cond_id = sys.argv[2] if len(sys.argv) > 2 else "C3"
    task_index = int(sys.argv[3]) if len(sys.argv) > 3 else 0

    cfg = load_yaml(config_path)
    bundle = RunnerBundle(cfg, config_path)
    tasks = load_tasks(cfg)
    task = tasks[task_index]
    task.metadata["target_id"] = cfg.get("target", {}).get("model_name", "demo-target")

    cond_cfg = STAGE1_CONDITIONS[cond_id]
    protocol = bundle.make_protocol(cond_id, cond_cfg, bundle.cfg["experiment"]["name"])
    runner = bundle.make_runner(protocol, save_trajectory=False)
    traj = runner.run_episode(task, protocol)

    offline = bundle.make_offline_evaluator()
    offline.evaluate_trajectory(traj)

    print("\n==== trajectory summary ====")
    print("trajectory_id:   {}".format(traj.trajectory_id))
    print("condition:       {} (feedback={})".format(cond_id, protocol.feedback_level))
    print("task:            {} / {}".format(task.task_id, task.harm_category))
    print("budget:          {} queries (exactly {})".format(
        protocol.target_query_budget, traj.target_queries))
    print("final_success(E):{}".format(traj.success))
    print("stop_reason:     {}".format(traj.stop_reason))
    for s in traj.steps:
        ext = s.external_evaluation.success if s.external_evaluation else None
        fb_lvl = s.feedback.feedback_level if s.feedback else "-"
        print("  round={} strategy={:<12} outcome={:<20} online={} E={} reward={:.3f} fb={}".format(
            s.round_id, s.action.strategy, s.judge_output.outcome,
            s.online_success, ext, s.reward, fb_lvl))


if __name__ == "__main__":
    main()
