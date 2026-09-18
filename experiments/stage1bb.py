# -*- coding: utf-8 -*-
"""Stage 1B-B — Task-Aware Multi-Signal Judge（V0.3-B 1B-B）。

30 goal-compliance tasks × {B0, B-C, B-G, B-M} × B=5 = 600 Target queries。
假设（设计 §12）：
  H6 观测覆盖    UR_multi < UR_content
  H7 可行动反馈  AFC_multi > AFC_content
  H8 行为质量    HSR_multi < HSR_content（或 EAR_multi > EAR_content）
  H9 最终效果    ASR/AUC_multi > ASR/AUC_content（最后才看）
每条件按 judge_backend 装配独立 Judge（分时加载互不干扰），
provenance 记录各条件的 judge 版本。
"""
import json
import logging
import os
from typing import Dict

from core.protocol import ExperimentProtocol
from core.protocol_validator import ProtocolValidator
from engine.batch_runner import BatchRunner
from engine.cost import summarize_all
from engine.factory import RunnerBundle, load_tasks
from evaluation.metrics import condition_summary, paired_bootstrap_delta_asr
from evaluation.stats import mcnemar_test, wilcoxon_signed_rank
from experiments.conditions import MAIN_COMPARISON

logger = logging.getLogger("safeloop.stage1bb")

CONDITIONS = {
    "B0": {"target_query_budget": 5, "feedback_level": "none", "judge_backend": None},
    "B_C": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "qwen3guard_v2"},
    "B_G": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "goal_compliance"},
    "B_M": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "multi_signal"},
}


def _judge_cfg_for(cfg: Dict, backend: str) -> Dict:
    """按 backend 派生该条件的 judge 配置（multi_signal 需两路 model_path）。"""
    import copy
    base = copy.deepcopy(cfg)
    jcfg = base.get("judge", {}) or {}
    goal_path = cfg.get("goal_judge", {}).get("model_path") or jcfg["model_path"]
    if backend == "multi_signal":
        base["judge"] = {"backend": "multi_signal",
                         "content_judge": dict(jcfg, backend="qwen3guard_v2"),
                         "goal_judge": {"model_path": goal_path,
                                        "dtype": cfg.get("goal_judge", {}).get(
                                            "dtype", jcfg.get("dtype", "bfloat16")),
                                        "device": jcfg.get("device", "cuda")}}
    elif backend == "goal_compliance":
        # J_g 必须用 goal_judge 段的模型（B_G 条件曾误用 content 路径——已修复）
        base["judge"] = dict(jcfg, backend=backend, model_path=goal_path)
    else:
        base["judge"] = dict(jcfg, backend=backend)
    return base


class Stage1BBExperiment:
    def __init__(self, cfg: Dict, config_path: str) -> None:
        self.cfg = cfg
        self.experiment_id = (cfg.get("experiment", {}) or {}).get(
            "name", "stage1b_b_4060")
        self.tasks = load_tasks(cfg)
        self.bundles = {c: RunnerBundle(_judge_cfg_for(cfg, cc["judge_backend"]),
                                        config_path)
                        for c, cc in CONDITIONS.items() if cc["judge_backend"]}
        # B0 无 judge：用 B_C 的配置但 feedback none（judge 不会被调用）
        self.bundles["B0"] = RunnerBundle(_judge_cfg_for(cfg, "qwen3guard_v2"),
                                          config_path)
        self.checkpoint_path = "outputs/checkpoints/{}.json".format(self.experiment_id)
        self.report: Dict = {}

    def run(self, resume: bool = False) -> Dict:
        if not self.tasks:
            raise RuntimeError("no tasks (check experiment.tasks_file)")
        budget = int((self.cfg.get("protocol", {}) or {}).get(
            "target_query_budget", 5))

        trajectories = {}
        for cond, ccfg in CONDITIONS.items():
            protocol = ExperimentProtocol(
                experiment_id=self.experiment_id, condition_id=cond,
                target_query_budget=budget, feedback_level=ccfg["feedback_level"],
                allow_target_response_history=True, memory_enabled=False,
                scheduler_type="uniform", training_enabled=False,
                initial_seed_policy="fixed_direct")
            bundle = self.bundles[cond]
            batch = BatchRunner(
                coordinator_factory=lambda pr: bundle.make_coordinator(pr),
                red_agent=bundle.red_agent, target=bundle.target,
                judge=bundle.judge, memory=bundle.memory,
                reward_factory=lambda b: bundle.make_reward_fn(b),
                feedback_builder=bundle.feedback_builder,
                model_manager=bundle.model_manager,
                provenance=bundle.provenance)
            trajectories[cond] = batch.run(
                self.tasks, {cond: protocol},
                checkpoint_path=self.checkpoint_path.replace(
                    ".json", "_{}.json".format(cond)),
                resume=resume)[cond]
            summarize_all(trajectories[cond])
            logger.info("[%s] done: %d trajectories", cond, len(trajectories[cond]))

        # 初始 prompt 一致性（四条件同一 task 的 round0 prompt）
        validation_lines = ProtocolValidator.check_initial_prompts(trajectories)

        # 离线评估（StrongREJECT，goal 基准——J≠E 原则：E 不参与任何在线环节）
        from evaluation.offline_evaluator import OfflineEvaluator
        offline = OfflineEvaluator(self.bundles["B_C"].evaluator)
        eval_summary = {}
        for cond, trajs in trajectories.items():
            offline.disagreements = []
            eval_summary[cond] = offline.evaluate_all(
                trajs, "{}_{}".format(self.experiment_id, cond))

        metrics = {c: condition_summary(t, budget)
                   for c, t in trajectories.items()}
        comparisons = {}
        for a, b in (("B_C", "B_M"), ("B_G", "B_M"), ("B0", "B_M")):
            paired = paired_bootstrap_delta_asr(
                trajectories[a], trajectories[b], budget)
            from evaluation.metrics import ctts
            by_a = {t.task.task_id: t for t in trajectories[a]}
            by_b = {t.task.task_id: t for t in trajectories[b]}
            ids = sorted(set(by_a) & set(by_b))
            hit = lambda tr: any(
                s.external_evaluation and s.external_evaluation.success
                for s in tr.steps[:budget])
            mcn = mcnemar_test([hit(by_a[i]) for i in ids],
                               [hit(by_b[i]) for i in ids])
            wil = wilcoxon_signed_rank(
                [ctts(by_a[i], budget) for i in ids],
                [ctts(by_b[i], budget) for i in ids])
            comparisons["{}_vs_{}".format(a, b)] = {
                "delta_asr": paired["delta_asr"], "ci": [paired["ci_low"], paired["ci_high"]],
                "mcnemar_p": mcn["p_value"], "wilcoxon_p": wil["p_value"]}

        hyp = self._hypotheses(metrics)
        self.report = {
            "experiment_id": self.experiment_id,
            "stage": "1B-B multi-signal judge",
            "num_tasks": len(self.tasks),
            "protocol_validation": validation_lines,
            "metrics": metrics,
            "comparisons": comparisons,
            "hypotheses_H6_H9": hyp,
            "offline_evaluation": {c: v["disagreement"]
                                   for c, v in eval_summary.items()},
        }
        os.makedirs("outputs/reports", exist_ok=True)
        path = os.path.join("outputs/reports", "{}.json".format(self.experiment_id))
        json.dump(self.report, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        self._print(validation_lines, metrics, comparisons, hyp)
        return self.report

    @staticmethod
    def _hypotheses(m: Dict) -> Dict:
        def _get(cond, key):
            return (m[cond].get(key) if m[cond].get(key) is not None
                    else (m[cond].get("feedback_action_distribution", {}) or {}).get(key))
        h = {}
        for name, stmt, val, ok in [
            ("H6_UR", "UR(B_M) < UR(B_C)",
             (m["B_M"].get("uncertain_rate"), m["B_C"].get("uncertain_rate")),
             (m["B_M"].get("uncertain_rate") or 1) < (m["B_C"].get("uncertain_rate") or 0)),
            ("H7_AFC", "AFC(B_M) > AFC(B_C)",
             (m["B_M"].get("actionable_feedback_coverage"),
              m["B_C"].get("actionable_feedback_coverage")),
             (m["B_M"].get("actionable_feedback_coverage") or 0) >
             (m["B_C"].get("actionable_feedback_coverage") or 1)),
            ("H8_HSR", "HSR(B_M) < HSR(B_C)",
             (m["B_M"].get("harmful_switch_rate"), m["B_C"].get("harmful_switch_rate")),
             (m["B_M"].get("harmful_switch_rate") or 1) <
             (m["B_C"].get("harmful_switch_rate") or 0)),
            ("H9_ASR", "ASR@5(B_M) > ASR@5(B_C)",
             (m["B_M"]["asr_at_k"].get("5"), m["B_C"]["asr_at_k"].get("5")),
             (m["B_M"]["asr_at_k"].get("5", 0)) > (m["B_C"]["asr_at_k"].get("5", 0))),
        ]:
            h[name] = {"stmt": stmt, "values": val, "supported": bool(ok)}
        return h

    def _print(self, validation_lines, metrics, comparisons, hyp):
        print("\n" + "=" * 84)
        print("Stage 1B-B: Task-Aware Multi-Signal Judge ({} tasks, B=5)".format(
            len(self.tasks)))
        print("=" * 84)
        for l in validation_lines:
            print(" ", l)
        header = "{:<5} {:>7} {:>7} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
            "cond", "ASR@5", "AUC-B", "CTTS", "SSR", "HSR", "AFC", "UR")
        print("\n" + header)
        print("-" * len(header))
        for c, mv in metrics.items():
            def _f(x):
                return "{:.3f}".format(x) if x is not None else "-"
            print("{:<5} {:>7.1%} {:>8} {:>8} {:>8} {:>8} {:>8} {:>8}".format(
                c, mv["asr_at_k"].get("5", 0), _f(mv["auc_b"]), _f(mv["mean_ctts"]),
                _f(mv["strategy_switch_rate"]), _f(mv["harmful_switch_rate"]),
                _f(mv.get("actionable_feedback_coverage")),
                _f(mv.get("uncertain_rate"))))
        for name, cmp_ in comparisons.items():
            print("{}: dASR={:+.3f} CI{} mcnemar_p={:.3f}".format(
                name, cmp_["delta_asr"] or 0, tuple(cmp_["ci"]), cmp_["mcnemar_p"]))
        for k, v in hyp.items():
            print("  {:<8} {:<24} {} -> {}".format(
                k, v["stmt"], v["values"],
                "SUPPORTED" if v["supported"] else "NOT"))


def main(config_path: str = "configs/hardware/rtx4060_8g_1bb.yaml",
         resume: bool = False) -> Dict:
    from utils.io import load_yaml
    from utils.logging import setup_logging
    setup_logging()
    cfg = load_yaml(config_path)
    return Stage1BBExperiment(cfg, config_path).run(resume=resume)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "configs/hardware/rtx4060_8g_1bb.yaml")
