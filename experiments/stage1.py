# -*- coding: utf-8 -*-
"""Stage 1 实验执行器（设计文档 §39/§51）。

流程：
  1. 装配组件（所有条件共享同一套后端与种子）；
  2. ProtocolValidator 运行前校验：C1/C2/C3 之间只允许 feedback_level 不同；
  3. 逐条件跑满 target_query_budget（不提前停），落盘轨迹；
  4. 代码级 invariant：所有条件同一 task 的第 0 轮 prompt 完全一致；
  5. OfflineEvaluator 离线批评估（evaluator 绝不进入在线环）；
  6. 指标：ASR@k / AUC-B / QTS(mean,median) / SSR / LRR + 配对 bootstrap ΔASR；
  7. 输出报告与终端摘要（含效率曲线）。

主假设 H1：ASR_{C3}@B > ASR_{C1}@B（相同查询预算下，判别反馈提升探索能力）。
"""
import json
import logging
import os
from typing import Dict, List

from core.protocol_validator import ProtocolValidator
from core.schemas import AttackTrajectory, SafetyTask
from engine.factory import RunnerBundle, load_tasks
from evaluation.metrics import (
    asr_at_k,
    auc_b,
    condition_summary,
    paired_bootstrap_delta_asr,
)
from experiments.conditions import (
    ALLOWED_PAIR_DIFFERENCES,
    MAIN_COMPARISON,
    STAGE1_DEMO_CONDITIONS,
)

logger = logging.getLogger("safeloop.stage1")


class Stage1Experiment:
    def __init__(self, cfg: Dict, config_path: str = "configs/stage1.yaml") -> None:
        self.cfg = cfg
        self.experiment_id = (cfg.get("experiment", {}) or {}).get(
            "name", "stage1_feedback_validation")
        self.bundle = RunnerBundle(cfg, config_path)
        self.tasks: List[SafetyTask] = load_tasks(cfg)
        self.trajectories: Dict[str, List[AttackTrajectory]] = {}
        self.report: Dict = {}

    # ------------------------------------------------------------------
    def run(self) -> Dict:
        if not self.tasks:
            raise RuntimeError("no tasks loaded (check experiment.tasks_file)")

        # 1) 运行前协议校验（阻止混杂变量）
        validation_lines = self._validate_protocol()

        # 2) 逐条件执行（先不落盘，待离线评估补全 E 标签后统一持久化）
        for cond_id, cond_cfg in STAGE1_DEMO_CONDITIONS.items():
            protocol = self.bundle.make_protocol(cond_id, cond_cfg, self.experiment_id)
            runner = self.bundle.make_runner(protocol, save_trajectory=False)
            self.trajectories[cond_id] = [
                runner.run_episode(t, protocol) for t in self.tasks
            ]

        # 3) 初始 prompt 一致性（代码级 invariant，§15）
        validation_lines += ProtocolValidator.check_initial_prompts(self.trajectories)

        # 4) 离线批评估（final-only，绝不进入在线环）
        offline = self.bundle.make_offline_evaluator()
        eval_summary = {
            cond: offline.evaluate_all(trajs, "{}_{}".format(self.experiment_id, cond))
            for cond, trajs in self.trajectories.items()
        }

        # 4.5) 持久化已评估的完整轨迹（canonical JSONL，可供 replay）
        from memory.trajectory_store import TrajectoryStore
        store = TrajectoryStore()
        for cond, trajs in self.trajectories.items():
            for t in trajs:
                store.save(t, "{}_{}".format(self.experiment_id, cond))

        # 5) 指标与配对检验
        budget = max(
            c["target_query_budget"] for c in STAGE1_DEMO_CONDITIONS.values())
        metrics = {
            cond: condition_summary(trajs, budget)
            for cond, trajs in self.trajectories.items()
        }
        base_cond, aug_cond = MAIN_COMPARISON
        paired = paired_bootstrap_delta_asr(
            self.trajectories[base_cond], self.trajectories[aug_cond], budget)
        paired = {"baseline": base_cond, "augmented": aug_cond, **paired}

        self.report = {
            "experiment_id": self.experiment_id,
            "num_tasks": len(self.tasks),
            "protocol_validation": validation_lines,
            "provenance": self.bundle.provenance,
            "backends": self.bundle.backends_info,
            "offline_evaluation": eval_summary,
            "metrics": metrics,
            "paired": {"baseline": base_cond, "augmented": aug_cond, **paired},
            "hypotheses": self._hypotheses(metrics, base_cond, aug_cond, budget),
        }
        self._dump_report()
        self._print_summary(validation_lines, metrics, paired, budget)
        return self.report

    # ------------------------------------------------------------------
    def _validate_protocol(self) -> List[str]:
        lines: List[str] = []
        conds = list(STAGE1_DEMO_CONDITIONS)
        protocols = {
            c: self.bundle.make_protocol(c, STAGE1_DEMO_CONDITIONS[c], self.experiment_id)
            for c in conds
        }
        for i in range(len(conds)):
            for j in range(i + 1, len(conds)):
                a, b = conds[i], conds[j]
                allowed = ALLOWED_PAIR_DIFFERENCES.get(frozenset((a, b)))
                if allowed is None:
                    # 非白名单对（如 C0 vs C3，预算不同）只提示，不比较
                    lines.append("[SKIP] {} vs {}: budget differs (reference baseline)".format(a, b))
                    continue
                lines.append("== {} vs {} ==".format(a, b))
                lines += ProtocolValidator.compare_protocols(
                    protocols[a], protocols[b],
                    backends=self.bundle.backends_info,
                    allowed_differences=allowed,
                )
        return lines

    @staticmethod
    def _hypotheses(metrics: Dict, base: str, aug: str, budget: int) -> Dict:
        asr_b = metrics[base]["asr_at_k"].get(str(budget), 0)
        asr_a = metrics[aug]["asr_at_k"].get(str(budget), 0)
        qts_b, qts_a = metrics[base]["mean_qts"], metrics[aug]["mean_qts"]
        if qts_b is None or qts_a is None:
            # 基线（或对照）零成功时 QTS 无定义，只能标记不可评估
            h3_status = "NOT EVALUABLE (no successes in a compared condition)"
            h3_supported = False
        else:
            h3_supported = qts_a < qts_b
            h3_status = "SUPPORTED" if h3_supported else "NOT SUPPORTED"
        return {
            "H1_asr": {
                "statement": "ASR_{}@{} > ASR_{}@{}".format(aug, budget, base, budget),
                "baseline": asr_b, "augmented": asr_a,
                "supported": asr_a > asr_b,
                "status": "SUPPORTED" if asr_a > asr_b else "NOT SUPPORTED",
            },
            "H2_auc": {
                "statement": "AUC_B({}) > AUC_B({})".format(aug, base),
                "baseline": metrics[base]["auc_b"], "augmented": metrics[aug]["auc_b"],
                "supported": metrics[aug]["auc_b"] > metrics[base]["auc_b"],
                "status": "SUPPORTED" if metrics[aug]["auc_b"] > metrics[base]["auc_b"]
                else "NOT SUPPORTED",
            },
            "H3_qts": {
                "statement": "MeanQTS({}) < MeanQTS({})".format(aug, base),
                "baseline": qts_b, "augmented": qts_a,
                "supported": h3_supported,
                "status": h3_status,
            },
        }

    def _dump_report(self) -> None:
        os.makedirs("outputs/reports", exist_ok=True)
        path = os.path.join("outputs/reports", "{}.json".format(self.experiment_id))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, ensure_ascii=False, indent=2)
        logger.info("report saved -> %s", path)

    # ------------------------------------------------------------------
    def _print_summary(self, validation_lines, metrics, paired, budget) -> None:
        print("\n" + "=" * 74)
        print("SafeLoop Stage 1 experiment: {} ({} tasks)".format(
            self.experiment_id, len(self.tasks)))
        print("=" * 74)
        for line in validation_lines:
            print("  " + line)

        header = "{:<5} {:>7} {:>7} {:>7} {:>7} {:>7} {:>8} {:>10} {:>7} {:>7}".format(
            "cond", "ASR@1", "ASR@2", "ASR@3", "ASR@4", "ASR@5",
            "AUC-B", "QTS(mean)", "SSR", "LRR")
        print("\n" + header)
        print("-" * len(header))
        for cond, m in metrics.items():
            asr = m["asr_at_k"]
            print("{:<5} {:>7.1%} {:>7.1%} {:>7.1%} {:>7.1%} {:>7.1%} {:>8.3f} {:>10} {:>7} {:>7}".format(
                cond,
                asr.get("1", 0), asr.get("2", 0), asr.get("3", 0),
                asr.get("4", 0), asr.get("5", 0),
                m["auc_b"],
                "{:.2f}".format(m["mean_qts"]) if m["mean_qts"] is not None else "-",
                "{:.2f}".format(m["strategy_switch_rate"])
                if m["strategy_switch_rate"] is not None else "-",
                "{:.2f}".format(m["lexical_revision_rate"])
                if m["lexical_revision_rate"] is not None else "-",
            ))

        print("\nAttack Efficiency Curve (ASR@k):")
        for cond, m in metrics.items():
            bars = " ".join(
                "{:>5}".format("{:.0%}".format(m["asr_at_k"].get(str(k), 0)))
                for k in range(1, budget + 1))
            print("  {} | {}".format(cond, bars))

        print("\npaired ΔASR ({} − {}): {:+.3f}, 95% CI [{:+.3f}, {:+.3f}], n={}".format(
            paired["augmented"], paired["baseline"],
            paired["delta_asr"] or 0.0, paired["ci_low"] or 0.0,
            paired["ci_high"] or 0.0, paired["n_paired"]))
        for name, h in self.report["hypotheses"].items():
            print("  {:<8} {:<55} -> {}".format(
                name, h["statement"], h["status"]))


def main(config_path: str = "configs/stage1.yaml") -> Dict:
    from utils.io import load_yaml
    from utils.logging import setup_logging

    setup_logging()
    cfg = load_yaml(config_path)
    return Stage1Experiment(cfg, config_path).run()


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "configs/stage1.yaml")
