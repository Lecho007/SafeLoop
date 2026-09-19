# -*- coding: utf-8 -*-
"""Stage 1B-CF 在线实验（设计 §18–§21）：CF-10（polarity 修复×soft 执行）与
CF-11（polarity 修复×enforced 执行）。CF-00 = B-G-V3 复用；B0 复用。

条件间唯一差异（§27）：control_execution_mode = soft / enforced。
Judge/任务/seed/初始 prompt/decoding 完全一致。
"""
import json
import logging
import os
from typing import Dict

from agents.goal_advancement_judge_v3 import GoalAdvancementJudgeV3
from agents.polarity_judge import PolarityJudge
from agents.cf_red_agent import CFRedAgent
from core.cf_coordinator import ControlFixCoordinator
from core.control_layer import CFSplitJudge, ControlPolicy, FeedbackBuilderCF
from core.protocol import ExperimentProtocol
from engine.batch_runner import BatchRunner
from engine.cost import summarize_all
from engine.factory import RunnerBundle, build_scheduler, build_memory, load_tasks
from evaluation.metrics import (
    asr_at_k, auc_b, condition_summary, mean_ctts, strategy_switch_rate)
from evaluation.offline_evaluator import OfflineEvaluator
from utils.io import load_yaml

logger = logging.getLogger("safeloop.stage1cf")

CONDITIONS = {
    "CF_10": {"enforced": False},
    "CF_11": {"enforced": True},
}


def _run_condition(cfg, config_path, tasks, cond, enforced, resume=False):
    import copy, random
    base = copy.deepcopy(cfg)
    seed = 42
    bundle_red = CFRedAgent(
        model_path=base["red_agent"]["model_path"],
        model_manager=None,
        dtype=base["red_agent"].get("dtype", "bfloat16"),
        device=base["red_agent"].get("device", "cuda"),
        do_sample=bool(base["red_agent"].get("do_sample", True)),
        temperature=float(base["red_agent"].get("temperature", 0.7)),
        top_p=float(base["red_agent"].get("top_p", 0.9)),
        max_new_tokens=320, rng=random.Random(seed), enforced=enforced)
    adv = GoalAdvancementJudgeV3(
        model_path=base["goal_judge"]["model_path"],
        dtype=base["goal_judge"].get("dtype", "bfloat16"),
        device=base["goal_judge"].get("device", "cuda"))
    pol = PolarityJudge(
        model_path=base["goal_judge"]["model_path"],
        dtype=base["goal_judge"].get("dtype", "bfloat16"),
        device=base["goal_judge"].get("device", "cuda"))
    judge = CFSplitJudge(adv, pol)
    from engine.hf_backend import ModelManager
    from targets.hf_target import HfTarget
    from engine.factory import build_evaluator, quantization_spec
    tcfg = base["target"]
    target = HfTarget(
        model_path=tcfg["model_path"], model_manager=None,
        dtype=tcfg.get("dtype", "bfloat16"), device=tcfg.get("device", "cuda"),
        do_sample=bool(tcfg.get("do_sample", False)),
        max_new_tokens=int(tcfg.get("max_new_tokens", 512)),
        quantization=quantization_spec(tcfg.get("quantization"),
                                       tcfg.get("compute_dtype", "bfloat16")))
    evaluator = build_evaluator(base)
    policy = ControlPolicy(seed=seed, enforced=enforced)

    def coordinator_factory(proto):
        sched = build_scheduler(base, random.Random(seed))
        return ControlFixCoordinator(sched, policy)

    def reward_factory(b):
        from core.reward import RewardConfig, RewardFunction
        return RewardFunction(RewardConfig(**(base.get("reward", {}) or {})), b)

    batch = BatchRunner(
        coordinator_factory=coordinator_factory, red_agent=bundle_red,
        target=target, judge=judge, memory=build_memory(base),
        reward_factory=reward_factory, feedback_builder=FeedbackBuilderCF(),
        provenance={"stage": "1B-CF", "condition": cond,
                    "control_execution_mode": "enforced" if enforced else "soft",
                    "polarity_version": "polarity-v2",
                    "advancement_version": "goal-advancement-v3"})
    protocol = ExperimentProtocol(
        experiment_id="stage1b_cf_4060", condition_id=cond,
        target_query_budget=5, feedback_level="structured",
        allow_target_response_history=True, memory_enabled=False,
        scheduler_type="uniform", training_enabled=False,
        initial_seed_policy="fixed_direct")
    result = batch.run(
        tasks, {cond: protocol},
        checkpoint_path="outputs/checkpoints/stage1b_cf_4060_{}.json".format(cond),
        resume=resume)
    trajs = result[cond]
    offline = OfflineEvaluator(evaluator)
    offline.disagreements = []
    offline.evaluate_all(trajs, "stage1b_cf_4060_{}".format(cond))
    summarize_all(trajs)
    logger.info("[%s] done: %d trajs", cond, len(trajs))
    return trajs


def _control_metrics(trajs):
    from collections import Counter
    frr = {a: [0, 0] for a in ("KEEP", "REFINE", "SWITCH", "REALIGN")}
    actions = Counter()
    cvr = [0, 0]
    rsr = [0, 0]
    ser = [0, 0]
    for t in trajs:
        for s in t.steps:
            if s.feedback is not None and s.feedback.adaptation_action:
                actions[s.feedback.adaptation_action] += 1
        for prev, cur in zip(t.steps, t.steps[1:]):
            a = prev.feedback.adaptation_action if prev.feedback else None
            if a is None:
                continue
            same = cur.action.strategy == prev.action.strategy
            changed_prompt = cur.action.prompt != prev.action.prompt
            if a == "KEEP":
                frr[a][1] += 1; frr[a][0] += same
            elif a == "REFINE":
                frr[a][1] += 1; frr[a][0] += (same and changed_prompt)
            elif a == "SWITCH":
                frr[a][1] += 1; frr[a][0] += (not same)
                ser[1] += 1; ser[0] += (not same)
            elif a == "REALIGN":
                frr[a][1] += 1
                frr[a][0] += (same and changed_prompt)
                rsr[1] += 1
                nxt_pol = cur.judge_output.metadata.get("polarity") if cur.judge_output else None
                rsr[0] += (nxt_pol == "ALIGNED")
            log = cur.action.metadata.get("control_log") or {}
            if "constraint_satisfied" in log and log["constraint_satisfied"] is not None:
                cvr[1] += 1
                cvr[0] += bool(log["constraint_satisfied"])
    out = {"actions": dict(actions),
           "FRR": {a: (round(k/n, 4) if n else None) for a, (k, n) in frr.items()},
           "SER": round(ser[0]/ser[1], 4) if ser[1] else None,
           "RSR": round(rsr[0]/rsr[1], 4) if rsr[1] else None,
           "CVR": round(cvr[0]/cvr[1], 4) if cvr[1] else None}
    return out


def main(config_path="configs/hardware/rtx4060_8g_1bb.yaml", resume=False):
    from utils.logging import setup_logging
    setup_logging()
    cfg = load_yaml(config_path)
    tasks = load_tasks(cfg)
    report = {"experiment_id": "stage1b_cf_4060", "num_tasks": len(tasks)}
    for cond, cc in CONDITIONS.items():
        trajs = _run_condition(cfg, config_path, tasks, cond, cc["enforced"], resume)
        m = condition_summary(trajs, 5)
        report[cond] = {"metrics": m, "control": _control_metrics(trajs)}
    # 参照
    from memory.trajectory_store import TrajectoryStore
    for ref, path in (("CF_00_BG_V3", "outputs/evaluations/stage1b_gv3_4060_B_G.jsonl"),
                      ("B0", "outputs/evaluations/stage1b_b_4060_B0.jsonl")):
        if os.path.exists(path):
            report[ref] = condition_summary(TrajectoryStore.load(path), 5)
    os.makedirs("outputs/reports", exist_ok=True)
    json.dump(report, open("outputs/reports/stage1b_cf_4060.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)
    # 打印
    for cond in CONDITIONS:
        r = report[cond]
        print("\n== {} ==".format(cond))
        print(" control:", json.dumps(r["control"], ensure_ascii=False))
        print(" ASR@5 {:.1%} AUC {:.3f} CTTS {:.2f} SSR {:.3f} EAR? {:.3f}".format(
            r["metrics"]["asr_at_k"].get("5", 0), r["metrics"]["auc_b"],
            r["metrics"]["mean_ctts"], r["metrics"]["strategy_switch_rate"],
            r["metrics"].get("effective_strategy_switch_rate") or 0))
    for ref in ("CF_00_BG_V3", "B0"):
        if ref in report:
            print("{}: ASR@5 {:.1%} AUC {:.3f} CTTS {:.2f}".format(
                ref, report[ref]["asr_at_k"].get("5", 0),
                report[ref]["auc_b"], report[ref]["mean_ctts"]))
    return report


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "configs/hardware/rtx4060_8g_1bb.yaml")
