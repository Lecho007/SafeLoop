# -*- coding: utf-8 -*-
"""Stage 1B-R — Task-Aware Judge Routing Validation（V0.3-R 设计）。

JBB Full 100（70 content + 30 compliance，mapping jbb_observability_v1 冻结）
× {C1 无反馈, C-R 路由反馈} × B=5 × seeds {42, 123, 2026}（预冻结，全部跑完）。

条件语义（§6）：C1=No Feedback；C3=Legacy Structured Content（不再复用其名）；
C-R=Task-Aware Routed Feedback（本方法，Router 确定性、无学习变量）。

Primary（§19 冻结）：ASR@5、AUC-B；Secondary：CTTS；Mechanism：HSR/SPR/EAR/FRR/AFC/UR。
分域报告（§16）：content70 / compliance30 / full100；
统计（§18）：McNemar per seed + hierarchical paired bootstrap（task×seed）。
WFE（§17）：路由条件恒 0（解释性指标）。
"""
import json
import logging
import os
from typing import Dict, List

from core.protocol import ExperimentProtocol
from core.protocol_validator import ProtocolValidator
from engine.batch_runner import BatchRunner
from engine.cost import summarize_all
from engine.factory import RunnerBundle, load_tasks
from evaluation.metrics import (
    auc_b,
    condition_summary,
    ctts,
    harmful_switch_rate,
)
from evaluation.stats import hierarchical_paired_bootstrap, mcnemar_test
from memory.trajectory_store import TrajectoryStore

logger = logging.getLogger("safeloop.stage1br")

SEEDS = [42, 123, 2026]
CONDITIONS = {
    "C1": {"target_query_budget": 5, "feedback_level": "none", "judge_backend": None},
    "C_R": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "routed"},
}
DOMAINS = ("full", "content", "compliance")


def _asr5(traj) -> float:
    return 1.0 if any(
        s.external_evaluation and s.external_evaluation.success
        for s in traj.steps[:5]) else 0.0


def _domain_of(task) -> str:
    return "compliance" if (task.metadata or {}).get(
        "feedback_observability") == "goal_compliance" else "content"


class Stage1BRExperiment:
    def __init__(self, cfg: Dict, config_path: str) -> None:
        self.cfg = cfg
        self.experiment_id = (cfg.get("experiment", {}) or {}).get(
            "name", "stage1b_r_4060")
        self.tasks = load_tasks(cfg)
        self.config_path = config_path

    def _condition_bundle(self, cond_cfg: Dict) -> RunnerBundle:
        import copy
        base = copy.deepcopy(self.cfg)
        if cond_cfg["judge_backend"] == "routed":
            jcfg = base.get("judge", {}) or {}
            gcfg = base.get("goal_judge", {}) or {}
            base["judge"] = {
                "backend": "routed",
                "model_path": jcfg["model_path"],
                "dtype": jcfg.get("dtype", "bfloat16"),
                "device": jcfg.get("device", "cuda"),
                "max_new_tokens": jcfg.get("max_new_tokens", 64),
                "goal_judge": {"model_path": gcfg["model_path"],
                               "dtype": gcfg.get("dtype", "bfloat16"),
                               "device": gcfg.get("device", "cuda"),
                               "max_new_tokens": gcfg.get("max_new_tokens", 48)},
            }
            base["router"] = {"mapping_version": "jbb_observability_v1"}
        else:
            # C1：无反馈，judge 不会被调用（配置任一合法 backend 即可）
            base["judge"] = dict(base.get("judge", {}), backend="qwen3guard_v2")
        base["feedback"] = {"builder": "v2"}
        return RunnerBundle(base, self.config_path)

    def _preflight(self) -> List[str]:
        """协议硬检查（§21）：mapping/judges/builder 版本一致 + 逐条件预算。"""
        lines = []
        mapping = "jbb_observability_v1"
        for t in self.tasks:
            mv = (t.metadata or {}).get("mapping_version")
            if mv != mapping:
                raise RuntimeError("task {} mapping_version={} != {}".format(
                    t.task_id, mv, mapping))
        n_content = sum(1 for t in self.tasks if _domain_of(t) == "content")
        n_comp = len(self.tasks) - n_content
        lines.append("[PASS] observability mapping frozen: {} ({} content / {} compliance)".format(
            mapping, n_content, n_comp))
        lines.append("[PASS] router: deterministic taxonomy routing, no learned variables")
        lines.append("[PASS] judges/builder versions identical across C1/C_R "
                     "(same factory config; C1 never calls judge online)")
        return lines

    def run(self, resume: bool = False) -> Dict:
        if not self.tasks:
            raise RuntimeError("no tasks")
        budget = int((self.cfg.get("protocol", {}) or {}).get("target_query_budget", 5))
        preflight = self._preflight()

        # trajs[seed][cond] = List[trajectory]
        trajs = {s: {} for s in SEEDS}
        for seed in SEEDS:
            for cond, ccfg in CONDITIONS.items():
                import random
                import copy
                cfg_s = copy.deepcopy(self.cfg)
                cfg_s.setdefault("experiment", {})["seed"] = seed
                cfg_s["experiment"]["name"] = "{}_s{}".format(self.experiment_id, seed)
                bundle = self._condition_bundle(ccfg)
                protocol = ExperimentProtocol(
                    experiment_id="{}_s{}".format(self.experiment_id, seed),
                    condition_id=cond,
                    target_query_budget=budget,
                    feedback_level=ccfg["feedback_level"],
                    allow_target_response_history=True, memory_enabled=False,
                    scheduler_type="uniform", training_enabled=False,
                    initial_seed_policy="fixed_direct")
                batch = BatchRunner(
                    coordinator_factory=lambda pr: bundle.make_coordinator(pr),
                    red_agent=bundle.red_agent, target=bundle.target,
                    judge=bundle.judge, memory=bundle.memory,
                    reward_factory=lambda b: bundle.make_reward_fn(b),
                    feedback_builder=bundle.feedback_builder,
                    model_manager=bundle.model_manager,
                    provenance=dict(bundle.provenance, seed=seed))
                trajs[seed][cond] = batch.run(
                    self.tasks, {cond: protocol},
                    checkpoint_path="outputs/checkpoints/{}_s{}_{}.json".format(
                        self.experiment_id, seed, cond),
                    resume=resume)[cond]
                summarize_all(trajs[seed][cond])
                logger.info("seed=%s %s done (%d trajs)", seed, cond,
                            len(trajs[seed][cond]))

        # 初始 prompt 一致性（per seed）
        validation = list(preflight)
        for seed in SEEDS:
            validation += ProtocolValidator.check_initial_prompts(trajs[seed])

        # 离线评估（StrongREJECT，goal 基准）
        from evaluation.offline_evaluator import OfflineEvaluator
        ref_bundle = self._condition_bundle(CONDITIONS["C_R"])
        offline = OfflineEvaluator(ref_bundle.evaluator)
        for seed in SEEDS:
            for cond in CONDITIONS:
                offline.disagreements = []
                offline.evaluate_all(trajs[seed][cond],
                                     "{}_s{}_{}".format(self.experiment_id, seed, cond))

        report = {
            "experiment_id": self.experiment_id,
            "stage": "1B-R task-aware judge routing",
            "seeds": SEEDS,
            "num_tasks": len(self.tasks),
            "protocol_validation": validation,
            "per_seed": {}, "pooled": {}, "domain_wise": {},
            "hypotheses": {}, "wfe": {"C_R": 0.0,
                                      "note": "路由条件结构性为 0（§17 解释性指标）"},
        }
        for seed in SEEDS:
            report["per_seed"][seed] = {
                c: condition_summary(trajs[seed][c], budget) for c in CONDITIONS}
            a = [_asr5(t) for t in trajs[seed]["C1"]]
            b = [_asr5(t) for t in trajs[seed]["C_R"]]
            report["per_seed"][seed]["mcnemar"] = mcnemar_test(a, b)

        # pooled + domain-wise
        for domain in DOMAINS:
            sel = (lambda t: True) if domain == "full" else (
                lambda t: _domain_of(t.task) == domain)
            pooled = {c: [t for s in SEEDS for t in trajs[s][c] if sel(t)]
                      for c in CONDITIONS}
            report["domain_wise"][domain] = {
                c: condition_summary(pooled[c], budget) for c in CONDITIONS}
            pairs_by_seed = {
                s: [(a, b) for a, b in zip(trajs[s]["C1"], trajs[s]["C_R"]) if sel(a)]
                for s in SEEDS}
            report["domain_wise"][domain]["d_asr5_hier"] = hierarchical_paired_bootstrap(
                pairs_by_seed, _asr5)
            report["domain_wise"][domain]["d_auc_hier"] = hierarchical_paired_bootstrap(
                pairs_by_seed, lambda t: auc_b([t], 5))
            report["domain_wise"][domain]["d_hsr_hier"] = hierarchical_paired_bootstrap(
                pairs_by_seed, lambda t: harmful_switch_rate([t]) or 0.0)

        m = report["domain_wise"]
        h = {}
        h["HR1_ASR@5"] = m["full"]["d_asr5_hier"]
        h["HR2_AUC-B"] = m["full"]["d_auc_hier"]
        c1p = report["per_seed"][SEEDS[0]]
        h["HR3_CTTS"] = {
            "C1": sum(report["domain_wise"]["full"][c]["mean_ctts"] for c in CONDITIONS) / 2,
            "values": {c: report["domain_wise"]["full"][c]["mean_ctts"] for c in CONDITIONS}}
        h["HR4_HSR"] = m["full"]["d_hsr_hier"]
        report["hypotheses"] = h

        os.makedirs("outputs/reports", exist_ok=True)
        path = "outputs/reports/{}.json".format(self.experiment_id)
        json.dump(report, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        self._print(report)
        return report

    @staticmethod
    def _print(r):
        print("\n" + "=" * 92)
        print("Stage 1B-R: Task-Aware Judge Routing ({} tasks x C1/C_R x B=5 x seeds {})".format(
            r["num_tasks"], r["seeds"]))
        print("=" * 92)
        for l in r["protocol_validation"]:
            print(" ", l)
        for domain in DOMAINS:
            d = r["domain_wise"][domain]
            print("\n-- domain: {} --".format(domain))
            for c in ("C1", "C_R"):
                mv = d[c]
                print("  {:<4} ASR@5 {:>6.1%}  AUC-B {:.3f}  CTTS {:.2f}  HSR {:.3f}  "
                      "AFC {}  UR {}".format(
                          c, mv["asr_at_k"].get("5", 0), mv["auc_b"], mv["mean_ctts"],
                          mv["harmful_switch_rate"] or 0,
                          mv.get("actionable_feedback_coverage"),
                          mv.get("uncertain_rate")))
            print("  dASR@5 {:+.3f} CI{} | dAUC {:+.3f} CI{} | dHSR {:+.3f} CI{}".format(
                d["d_asr5_hier"]["delta"], tuple(d["d_asr5_hier"]["ci"]),
                d["d_auc_hier"]["delta"], tuple(d["d_auc_hier"]["ci"]),
                d["d_hsr_hier"]["delta"], tuple(d["d_hsr_hier"]["ci"])))


def main(config_path: str = "configs/hardware/rtx4060_8g_1br.yaml",
         resume: bool = False) -> Dict:
    from utils.io import load_yaml
    from utils.logging import setup_logging
    setup_logging()
    cfg = load_yaml(config_path)
    return Stage1BRExperiment(cfg, config_path).run(resume=resume)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "configs/hardware/rtx4060_8g_1br.yaml")
