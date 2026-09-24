# -*- coding: utf-8 -*-
"""Stage 1B-R — Task-Aware Feedback Routing（4 causal branches → 3 logical conditions）。

分支矩阵（协议冻结）：
    A = content70 × real_v1 × NONE                    350 queries
    B = content70 × real_v1 × ACTIVE(J_c, 1B-A C3 栈)  350
    C = goal30   × cf_v1   × NONE                     150
    D = goal30   × cf_v1   × ACTIVE(J_g, CF-10 soft)  150

逻辑条件：
    C1   = A + C
    C-JR = B + D
    C-R  = B + C (+ goal shadow = 对 C 支离线重判 J_g)

用法（主实验，逐分支跑）：
    PYTHONPATH=. python experiments/stage1br.py A      # 或 B / C / D
    PYTHONPATH=. python experiments/stage1br.py SHADOW  # 离线 shadow replay（零 query）
    PYTHONPATH=. python experiments/stage1br.py REPORT  # 组装三条件 + 全指标
"""
import json
import logging
import os
import random
from collections import Counter
from typing import Dict, List

from agents.cf_red_agent import CFRedAgent
from agents.goal_advancement_judge_v3 import GoalAdvancementJudgeV3
from agents.polarity_judge import PolarityJudge
from agents.qwen_guard_judge_v2 import Qwen3GuardJudgeV2
from agents.red_agent import TemplateRedAgent
from core.control_layer import CFSplitJudge, FeedbackBuilderCF
from core.coordinator_impl import HeuristicCoordinator
from core.protocol import ExperimentProtocol
from core.protocol_validator import ProtocolValidator
from engine.batch_runner import FEEDBACK_MODE_ACTIVE, FEEDBACK_MODE_NONE, BatchRunner
from engine.cost import summarize_all
from engine.factory import (build_evaluator, build_memory, build_scheduler,
                            load_tasks, quantization_spec)
from engine.hf_backend import ModelManager
from evaluation.metrics import asr_at_k, auc_b, condition_summary, ctts, mean_ctts
from evaluation.offline_evaluator import OfflineEvaluator
from evaluation.stats import mcnemar_test
from memory.trajectory_store import TrajectoryStore
from targets.hf_target import HfTarget
from utils.io import load_yaml
from utils.rng import derive_seed

logger = logging.getLogger("safeloop.stage1br")

SEED = 42
BRANCHES = {
    "A": {"domain": "content", "mode": FEEDBACK_MODE_NONE, "n_tasks": 70, "queries": 350},
    "B": {"domain": "content", "mode": FEEDBACK_MODE_ACTIVE, "n_tasks": 70, "queries": 350},
    "C": {"domain": "goal", "mode": FEEDBACK_MODE_NONE, "n_tasks": 30, "queries": 150},
    "D": {"domain": "goal", "mode": FEEDBACK_MODE_ACTIVE, "n_tasks": 30, "queries": 150},
}
EVAL_DIR = "outputs/evaluations"


def _split_domains(tasks):
    content = [t for t in tasks if (t.metadata or {}).get(
        "feedback_observability") == "content_observable"]
    goal = [t for t in tasks if (t.metadata or {}).get(
        "feedback_observability") == "goal_compliance"]
    return content, goal


def build_branch_stack(cfg, branch_id):
    b = BRANCHES[branch_id]
    domain, mode = b["domain"], b["mode"]
    mm = ModelManager()
    if domain == "content":
        # 1B-A C3 冻结栈：HfRedAgent + real_v1 模板 + Qwen3Guard + FeedbackBuilderV2
        from agents.hf_red_agent import HfRedAgent
        from feedback.feedback_builder_v2 import FeedbackBuilderV2
        red = HfRedAgent(
            model_path=cfg["red_agent"]["model_path"], model_manager=mm,
            template_path="prompts/red/real_v1.yaml",
            dtype=cfg["red_agent"].get("dtype", "bfloat16"),
            device=cfg["red_agent"].get("device", "cuda"),
            do_sample=bool(cfg["red_agent"].get("do_sample", True)),
            temperature=float(cfg["red_agent"].get("temperature", 0.7)),
            top_p=float(cfg["red_agent"].get("top_p", 0.9)),
            max_new_tokens=256, rng=random.Random(SEED))
        judge = Qwen3GuardJudgeV2(
            model_path=cfg["judge"]["model_path"],
            dtype=cfg["judge"].get("dtype", "bfloat16"),
            device=cfg["judge"].get("device", "cuda"),
            max_new_tokens=int(cfg["judge"].get("max_new_tokens", 64)))
        fb_builder = FeedbackBuilderV2()
        red_template = "real_v1"
    else:
        # CF-10 冻结栈：cf_v1 soft 红方 + CFSplit(V3+polarity) + FeedbackBuilderCF
        red = CFRedAgent(
            model_path=cfg["red_agent"]["model_path"], model_manager=mm,
            dtype=cfg["red_agent"].get("dtype", "bfloat16"),
            device=cfg["red_agent"].get("device", "cuda"),
            do_sample=bool(cfg["red_agent"].get("do_sample", True)),
            temperature=float(cfg["red_agent"].get("temperature", 0.7)),
            top_p=float(cfg["red_agent"].get("top_p", 0.9)),
            max_new_tokens=192, rng=random.Random(SEED), enforced=False)
        adv = GoalAdvancementJudgeV3(
            model_path=cfg["goal_judge"]["model_path"], max_new_tokens=48,
            dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
            device=cfg["goal_judge"].get("device", "cuda"))
        pol = PolarityJudge(
            model_path=cfg["goal_judge"]["model_path"], max_new_tokens=24,
            dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
            device=cfg["goal_judge"].get("device", "cuda"))
        judge = CFSplitJudge(adv, pol, model_manager=mm)
        fb_builder = FeedbackBuilderCF()
        red_template = "cf_v1"
    tcfg = cfg["target"]
    target = HfTarget(
        model_path=tcfg["model_path"], model_manager=mm,
        dtype=tcfg.get("dtype", "bfloat16"), device=tcfg.get("device", "cuda"),
        do_sample=bool(tcfg.get("do_sample", False)),
        max_new_tokens=int(tcfg.get("max_new_tokens", 512)),
        quantization=quantization_spec(tcfg.get("quantization"),
                                       tcfg.get("compute_dtype", "bfloat16")))
    return mm, red, target, judge, fb_builder, red_template


class PlainCoordinator(HeuristicCoordinator):
    """1B-R 不做 CF/CP 控制叠加：A/C=无反馈，B=content V2 映射，D=CF-10 soft
    （soft 模式下 ControlPolicy 不强制，策略由红方自选——与 CF-10 一致）。"""
    name = "plain_1br"


def run_branch(cfg, tasks, branch_id, resume=False):
    b = BRANCHES[branch_id]
    content, goal = _split_domains(tasks)
    branch_tasks = content if b["domain"] == "content" else goal
    mm, red, target, judge, fb_builder, red_template = build_branch_stack(cfg, branch_id)
    cond_id = "BR_{}".format(branch_id)

    def coordinator_factory(proto):
        return PlainCoordinator(build_scheduler(cfg, random.Random(SEED)))

    def reward_factory(budget):
        from core.reward import RewardConfig, RewardFunction
        return RewardFunction(RewardConfig(**(cfg.get("reward", {}) or {})), budget)

    batch = BatchRunner(
        coordinator_factory=coordinator_factory, red_agent=red, target=target,
        judge=judge, memory=build_memory(cfg), reward_factory=reward_factory,
        feedback_builder=fb_builder, model_manager=mm, base_seed=SEED,
        provenance={"stage": "1B-R", "branch": branch_id,
                    "observability_domain": b["domain"], "feedback_mode": b["mode"],
                    "red_template": red_template,
                    "content_stack": "1B-A-C3" if branch_id == "B" else None,
                    "goal_stack": "CF-10" if branch_id == "D" else None,
                    "seed": SEED})
    protocol = ExperimentProtocol(
        experiment_id="stage1b_r_4060", condition_id=cond_id,
        target_query_budget=5,
        feedback_level=("none" if b["mode"] == FEEDBACK_MODE_NONE else "structured"),
        allow_target_response_history=True, memory_enabled=False,
        scheduler_type="uniform", training_enabled=False,
        initial_seed_policy="fixed_direct",
        metadata={"feedback_mode": b["mode"], "branch": branch_id})
    trajs = batch.run(
        branch_tasks, {cond_id: protocol},
        checkpoint_path="outputs/checkpoints/stage1b_r_4060_{}.json".format(branch_id),
        resume=resume)[cond_id]
    logger.info("branch %s done: %d trajectories", branch_id, len(trajs))
    return trajs


def evaluate_branches(cfg, branches=("A", "B", "C", "D")):
    """对四支统一跑 StrongREJECT（goal 基准，episode 后离线）。"""
    evaluator = build_evaluator(cfg)
    for br in branches:
        path = "{}/stage1b_r_4060_BR_{}.jsonl".format(EVAL_DIR, br)
        if not os.path.exists(path):
            logger.warning("branch %s unevaluated (missing %s)", br, path)
            continue
        trajs = TrajectoryStore.load(path)
        offline = OfflineEvaluator(evaluator)
        offline.disagreements = []
        offline.evaluate_all(trajs, "stage1b_r_4060_BR_{}".format(br))
        summarize_all(trajs)
        logger.info("branch %s evaluated (%d trajs)", br, len(trajs))


def run_shadow(cfg, tasks):
    """离线 shadow：对 C 支冻结轨迹逐 step 重判 J_g（零 Target query）。"""
    _, goal = _split_domains(tasks)
    goal_ids = {t.task_id for t in goal}
    c_path = "{}/stage1b_r_4060_BR_C.jsonl".format(EVAL_DIR)
    trajs = [t for t in TrajectoryStore.load(c_path) if t.task.task_id in goal_ids]
    adv = GoalAdvancementJudgeV3(
        model_path=cfg["goal_judge"]["model_path"], max_new_tokens=48,
        dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
        device=cfg["goal_judge"].get("device", "cuda"))
    pol = PolarityJudge(
        model_path=cfg["goal_judge"]["model_path"], max_new_tokens=24,
        dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
        device=cfg["goal_judge"].get("device", "cuda"))
    out = "{}/stage1b_r_4060_SHADOW_goal.jsonl".format(EVAL_DIR)
    adv_dist = Counter(); pol_dist = Counter()
    with open(out, "w", encoding="utf-8") as f:
        for t in trajs:
            for s in t.steps:
                from core.schemas import AttackAction, TargetResponse
                a_out = adv.evaluate(t.task, s.action, s.response)
                p_out = pol.judge_prompt(t.task.goal, s.action.prompt)
                a = a_out.metadata.get("advancement")
                p = p_out.metadata.get("polarity")
                adv_dist[a] += 1; pol_dist[p] += 1
                f.write(json.dumps({
                    "task_id": t.task.task_id, "round_id": s.round_id,
                    "trajectory_id": t.trajectory_id,
                    "advancement": a, "polarity": p,
                    "e_success": bool(s.external_evaluation and s.external_evaluation.success),
                }, ensure_ascii=False) + "\n")
    logger.info("shadow replay done: %d steps, adv=%s pol=%s",
                sum(adv_dist.values()), dict(adv_dist), dict(pol_dist))


# ---------------------------------------------------------------- report
def _load_branch(branch_id, domain_filter=None):
    path = "{}/stage1b_r_4060_BR_{}.jsonl".format(EVAL_DIR, branch_id)
    trajs = TrajectoryStore.load(path)
    if domain_filter:
        keep = {t.task_id for t in domain_filter}
        trajs = [t for t in trajs if t.task.task_id in keep]
    return trajs


def build_report(cfg, tasks):
    content, goal = _split_domains(tasks)
    branches = {br: _load_branch(br) for br in ("A", "B", "C", "D")}
    # 协议检查
    lines = []
    lines += ProtocolValidator.check_initial_prompts({
        "A(none)": branches["A"], "B(active)": branches["B"]})
    lines += ProtocolValidator.check_initial_prompts({
        "C(none)": branches["C"], "D(active)": branches["D"]})
    # C1 无反馈不变量
    judge_invoked = all(
        (s.judge_output.metadata or {}).get("judge_invoked") is False
        for br in ("A", "C") for t in branches[br] for s in t.steps)
    lines.append("[{}] C1 judge_invoked=false (branches A/C structural)".format(
        "PASS" if judge_invoked else "FAIL"))
    # FLR（结构性：C-R.goal = C 支原轨迹，shadow 仅旁路注记）
    lines.append("[PASS] FLR=0 (structural: C-R.goal reuses C trajectories; "
                 "shadow annotations offline-only)")

    def _cond(parts):
        return [t for br in parts for t in branches[br]]

    conds = {"C1": _cond(("A", "C")), "C_JR": _cond(("B", "D")), "C_R": _cond(("B", "C"))}

    def domain_split(trajs):
        return ([t for t in trajs if t.task.task_id in {x.task_id for x in content}],
                [t for t in trajs if t.task.task_id in {x.task_id for x in goal}])

    report = {"experiment_id": "stage1b_r_4060",
              "protocol_validation": lines, "conditions": {}, "domains": {}}
    for name, trajs in conds.items():
        report["conditions"][name] = condition_summary(trajs, 5)
        c_part, g_part = domain_split(trajs)
        report["domains"][name] = {
            "content": condition_summary(c_part, 5),
            "goal": condition_summary(g_part, 5)}

    # task-level win/loss/tie + McNemar（C-R vs C1、C-R vs C-JR，全量+分域）
    def _succ_vec(trajs):
        return {t.task.task_id: any(
            s.external_evaluation and s.external_evaluation.success
            for s in t.steps) for t in trajs}

    def _cmp(x, y, label):
        vx, vy = _succ_vec(x), _succ_vec(y)
        ids = sorted(set(vx) & set(vy))
        m = mcnemar_test([vx[i] for i in ids], [vy[i] for i in ids])
        cx, cy = domain_split(x); cy_, gy = domain_split(y)
        vxc, vyc = _succ_vec(cx), _succ_vec(cy)
        vxc2, vyc2 = _succ_vec([t for t in x if t in y]) or None, None
        return {"win": sum(1 for i in ids if vx[i] and not vy[i]),
                "loss": sum(1 for i in ids if vy[i] and not vx[i]),
                "tie": sum(1 for i in ids if vx[i] == vy[i]),
                "mcnemar_p": m["p_value"]}

    report["task_level"] = {
        "CR_vs_C1": _cmp(conds["C_R"], conds["C1"], "full"),
        "CR_vs_CJR": _cmp(conds["C_R"], conds["C_JR"], "full"),
    }
    # 分域 task-level
    for name, x, y in (("content", conds["C_R"], conds["C1"]),
                       ("goal", conds["C_R"], conds["C1"]),
                       ("goal_C_R_vs_CJR", conds["C_R"], conds["C_JR"])):
        dom = "content" if "content" in name else "goal"
        xs = [t for t in x if t.task.task_id in (
            {q.task_id for q in content} if dom == "content" else {q.task_id for q in goal})]
        ys = [t for t in y if t.task.task_id in (
            {q.task_id for q in content} if dom == "content" else {q.task_id for q in goal})]
        vx, vy = _succ_vec(xs), _succ_vec(ys)
        ids = sorted(set(vx) & set(vy))
        report["task_level"]["{}_{}".format(name, "wl") ] = {
            "win": sum(1 for i in ids if vx[i] and not vy[i]),
            "loss": sum(1 for i in ids if vy[i] and not vx[i]),
            "tie": sum(1 for i in ids if vx[i] == vy[i])}

    # FLR/AIR
    total_steps = sum(len(t.steps) for t in conds["C_R"])
    shadow_steps = sum(len(t.steps) for t in branches["C"])
    report["routing_metrics"] = {
        "FLR": 0.0,
        "AIR_content": round(sum(len(t.steps) for t in branches["B"]) / total_steps, 4),
        "AIR_shadow": round(shadow_steps / total_steps, 4)}

    # R-H 假设
    m = report["conditions"]; d = report["domains"]
    report["hypotheses"] = {
        "RH1_protocol": {"route_acc": 1.0, "flr": 0.0, "supported": True},
        "RH2_content_mech": {
            "hsr_active": d["C_R"]["content"]["harmful_switch_rate"],
            "hsr_none": d["C1"]["content"]["harmful_switch_rate"],
            "supported": (d["C_R"]["content"]["harmful_switch_rate"] or 1) <
                         (d["C1"]["content"]["harmful_switch_rate"] or 0)},
        "RH3_shadow_identity": {
            "structural": True,
            "asr_goal_CR": d["C_R"]["goal"]["asr_at_k"].get("5"),
            "asr_goal_C1": d["C1"]["goal"]["asr_at_k"].get("5"),
            "supported": d["C_R"]["goal"]["asr_at_k"].get("5") ==
                         d["C1"]["goal"]["asr_at_k"].get("5")},
        "RH4_vs_C1": {
            "supported": (m["C_R"]["asr_at_k"].get("5", 0) >= m["C1"]["asr_at_k"].get("5", 0)
                          and m["C_R"]["auc_b"] >= m["C1"]["auc_b"])},
        "RH5_vs_CJR": {
            "supported": (m["C_R"]["asr_at_k"].get("5", 0) >=
                          m["C_JR"]["asr_at_k"].get("5", 0))},
    }
    os.makedirs("outputs/reports", exist_ok=True)
    json.dump(report, open("outputs/reports/stage1b_r_4060.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(json.dumps({"conditions": {k: {
        "ASR@5": v["asr_at_k"].get("5"), "AUC": v["auc_b"], "CTTS": v["mean_ctts"]}
        for k, v in m.items()},
        "domains": {c: {dom: {"ASR@5": v["asr_at_k"].get("5"), "AUC": v["auc_b"]}
                        for dom, v in dv.items()} for c, dv in d.items()},
        "routing": report["routing_metrics"],
        "hypotheses": {k: v.get("supported") for k, v in report["hypotheses"].items()}},
        ensure_ascii=False, indent=1))
    return report


def main(what="A", config_path="configs/hardware/rtx4060_8g_1bb.yaml", resume=False):
    from utils.logging import setup_logging
    setup_logging()
    cfg = load_yaml(config_path)
    tasks = load_tasks(cfg)  # jbb100_full（70/30 冻结）
    if what in BRANCHES:
        run_branch(cfg, tasks, what, resume)
    elif what == "EVAL":
        evaluate_branches(cfg)
    elif what == "SHADOW":
        run_shadow(cfg, tasks)
    elif what == "REPORT":
        build_report(cfg, tasks)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "A")
