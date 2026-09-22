# -*- coding: utf-8 -*-
"""Stage 1B-CP 在线实验：CP-H（refine-first + delayed switch，enforced）。

复用 stage1cf 的冻结组件栈，仅替换协调器为 HysteresisCoordinator。
"""
import json
import logging
import os
import random
from collections import Counter
from typing import Dict

from agents.cf_red_agent import CFRedAgent
from agents.goal_advancement_judge_v3 import GoalAdvancementJudgeV3
from agents.polarity_judge import PolarityJudge
from core.control_layer import CFSplitJudge, ControlPolicy, FeedbackBuilderCF
from core.cp_coordinator import HysteresisCoordinator, ADV_RANK
from core.protocol import ExperimentProtocol
from engine.batch_runner import BatchRunner
from engine.cost import summarize_all
from engine.factory import (
    RunnerBundle, build_evaluator, build_memory, build_scheduler,
    load_tasks, quantization_spec,
)
from engine.hf_backend import ModelManager
from evaluation.metrics import condition_summary
from evaluation.offline_evaluator import OfflineEvaluator
from targets.hf_target import HfTarget
from utils.io import load_yaml

logger = logging.getLogger("safeloop.stage1cp")
SEED = 42


def run_cp_h(cfg, config_path, tasks, resume=False):
    mm = ModelManager()
    red = CFRedAgent(
        model_path=cfg["red_agent"]["model_path"], model_manager=mm,
        dtype=cfg["red_agent"].get("dtype", "bfloat16"),
        device=cfg["red_agent"].get("device", "cuda"),
        do_sample=bool(cfg["red_agent"].get("do_sample", True)),
        temperature=float(cfg["red_agent"].get("temperature", 0.7)),
        top_p=float(cfg["red_agent"].get("top_p", 0.9)),
        max_new_tokens=192, rng=random.Random(SEED), enforced=True)
    adv = GoalAdvancementJudgeV3(
        model_path=cfg["goal_judge"]["model_path"], max_new_tokens=48,
        dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
        device=cfg["goal_judge"].get("device", "cuda"))
    pol = PolarityJudge(
        model_path=cfg["goal_judge"]["model_path"], max_new_tokens=24,
        dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
        device=cfg["goal_judge"].get("device", "cuda"))
    judge = CFSplitJudge(adv, pol, model_manager=mm)
    tcfg = cfg["target"]
    target = HfTarget(
        model_path=tcfg["model_path"], model_manager=mm,
        dtype=tcfg.get("dtype", "bfloat16"), device=tcfg.get("device", "cuda"),
        do_sample=bool(tcfg.get("do_sample", False)),
        max_new_tokens=int(tcfg.get("max_new_tokens", 512)),
        quantization=quantization_spec(tcfg.get("quantization"),
                                       tcfg.get("compute_dtype", "bfloat16")))
    evaluator = build_evaluator(cfg)
    policy = ControlPolicy(seed=SEED, enforced=True)

    def coordinator_factory(proto):
        return HysteresisCoordinator(
            build_scheduler(cfg, random.Random(SEED)), policy)

    def reward_factory(b):
        from core.reward import RewardConfig, RewardFunction
        return RewardFunction(RewardConfig(**(cfg.get("reward", {}) or {})), b)

    batch = BatchRunner(
        coordinator_factory=coordinator_factory, red_agent=red,
        target=target, judge=judge, memory=build_memory(cfg),
        reward_factory=reward_factory, feedback_builder=FeedbackBuilderCF(),
        model_manager=mm,
        provenance={"stage": "1B-CP", "condition": "CP_H",
                    "control_policy": "refine-first + delayed-switch(2xNONE)",
                    "execution": "enforced",
                    "advancement_version": "goal-advancement-v3",
                    "polarity_version": "polarity-v2"})
    protocol = ExperimentProtocol(
        experiment_id="stage1b_cp_4060", condition_id="CP_H",
        target_query_budget=5, feedback_level="structured",
        allow_target_response_history=True, memory_enabled=False,
        scheduler_type="uniform", training_enabled=False,
        initial_seed_policy="fixed_direct")
    trajs = batch.run(
        tasks, {"CP_H": protocol},
        checkpoint_path="outputs/checkpoints/stage1b_cp_4060_CP_H.json",
        resume=resume)["CP_H"]
    offline = OfflineEvaluator(evaluator)
    offline.disagreements = []
    offline.evaluate_all(trajs, "stage1b_cp_4060_CP_H")
    summarize_all(trajs)
    return trajs


def _metrics(trajs):
    from evaluation.metrics import strategy_switch_rate
    actions = Counter()
    frr = {a: [0, 0] for a in ("KEEP", "REFINE", "SWITCH", "REALIGN")}
    ser = [0, 0]
    cvr = [0, 0]
    sur = [0, 0]   # switch utility: 换族后 advancement 升级 或 E-success
    prr = [0, 0]   # refine 后下一轮 fail→success
    ear = [0, 0]
    hsr = [0, 0]
    for t in trajs:
        for s in t.steps:
            if s.feedback is not None and s.feedback.adaptation_action:
                actions[s.feedback.adaptation_action] += 1
        for i, s in enumerate(t.steps[:-1]):
            a = s.feedback.adaptation_action if s.feedback else None
            nxt = t.steps[i + 1]
            same = nxt.action.strategy == s.action.strategy
            changed = nxt.action.prompt != s.action.prompt
            e_ok = bool(s.external_evaluation and s.external_evaluation.success)
            n_e_ok = bool(nxt.external_evaluation and nxt.external_evaluation.success)
            adv = s.judge_output.metadata.get("advancement")
            n_adv = nxt.judge_output.metadata.get("advancement")
            if a is None:
                continue
            if a == "KEEP":
                frr[a][1] += 1; frr[a][0] += same
                ear[1] += 1; ear[0] += (e_ok)
            elif a == "REFINE":
                frr[a][1] += 1; frr[a][0] += (same and changed)
                prr[1] += 1; prr[0] += (n_e_ok and not e_ok)
                ear[1] += 1
                ear[0] += (n_e_ok and not e_ok)
            elif a == "SWITCH":
                frr[a][1] += 1; frr[a][0] += (not same)
                ser[1] += 1; ser[0] += (not same)
                sur[1] += 1
                sur[0] += ((ADV_RANK.get(n_adv, 0) > ADV_RANK.get(adv, 0)) or n_e_ok)
                ear[1] += 1
                ear[0] += ((ADV_RANK.get(n_adv, 0) > ADV_RANK.get(adv, 0)) or n_e_ok)
            elif a == "REALIGN":
                frr[a][1] += 1; frr[a][0] += (same and changed)
                ear[1] += 1
            if e_ok:
                hsr[1] += 1
                hsr[0] += (not same)
            log = nxt.action.metadata.get("control_log") or {}
            if log.get("constraint_satisfied") is not None:
                cvr[1] += 1; cvr[0] += bool(log["constraint_satisfied"])
    def _r(x):
        return round(x[0] / x[1], 4) if x[1] else None
    return {"actions": dict(actions), "SSR": round(strategy_switch_rate(trajs), 4),
            "FRR": {a: _r(v) for a, v in frr.items()},
            "SER": _r(ser), "CVR": _r(cvr), "SUR": _r(sur),
            "PRR": _r(prr), "EAR": _r(ear), "HSR_E": _r(hsr)}


def main(config_path="configs/hardware/rtx4060_8g_1bb.yaml", resume=False):
    from utils.logging import setup_logging
    setup_logging()
    cfg = load_yaml(config_path)
    tasks = load_tasks(cfg)
    trajs = run_cp_h(cfg, config_path, tasks, resume)
    report = {"experiment_id": "stage1b_cp_4060",
              "num_tasks": len(tasks),
              "CP_H": {"metrics": condition_summary(trajs, 5),
                       "control": _metrics(trajs)}}
    # 参照
    from memory.trajectory_store import TrajectoryStore
    for ref, path in (("CF_11", "outputs/evaluations/stage1b_cf_4060_CF_11.jsonl"),
                      ("CF_10", "outputs/evaluations/stage1b_cf_4060_CF_10.jsonl"),
                      ("CF_00_BG_V3", "outputs/evaluations/stage1b_gv3_4060_B_G.jsonl"),
                      ("B0", "outputs/evaluations/stage1b_b_4060_B0.jsonl")):
        if os.path.exists(path):
            report[ref] = condition_summary(TrajectoryStore.load(path), 5)
    # task-level win/loss/tie（E 成功向量）
    def _succ(path):
        return {t.task.task_id: any(
            s.external_evaluation and s.external_evaluation.success
            for s in t.steps) for t in TrajectoryStore.load(path)}
    cp = _succ("outputs/evaluations/stage1b_cp_4060_CP_H.jsonl")
    taskcmp = {}
    for ref, path in (("vs_CF_11", "outputs/evaluations/stage1b_cf_4060_CF_11.jsonl"),
                      ("vs_CF_10", "outputs/evaluations/stage1b_cf_4060_CF_10.jsonl"),
                      ("vs_B0", "outputs/evaluations/stage1b_b_4060_B0.jsonl")):
        o = _succ(path)
        ids = sorted(set(cp) & set(o))
        taskcmp[ref] = {"win": sum(1 for i in ids if cp[i] and not o[i]),
                        "loss": sum(1 for i in ids if o[i] and not cp[i]),
                        "tie": sum(1 for i in ids if cp[i] == o[i])}
    report["task_level"] = taskcmp
    os.makedirs("outputs/reports", exist_ok=True)
    json.dump(report, open("outputs/reports/stage1b_cp_4060.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"CP_H": report["CP_H"], "task_level": taskcmp},
                     ensure_ascii=False, indent=1))
    return report


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "configs/hardware/rtx4060_8g_1bb.yaml")
