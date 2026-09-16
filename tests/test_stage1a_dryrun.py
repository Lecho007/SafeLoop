# -*- coding: utf-8 -*-
"""Stage 1A dry-run 管道测试（scripted 后端走真实 batch 管道，设计 §41-8）。"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.factory import RunnerBundle
from experiments.stage1a import Stage1AExperiment, _dry_run_config
from utils.io import load_yaml

CFG_PATH = "configs/stage1a.yaml"


class TestStage1ADryRun(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = _dry_run_config(load_yaml(CFG_PATH))
        # demo manifest 已生成；B=3、C1/C3
        cls.report = Stage1AExperiment(cls.cfg, CFG_PATH).run()

    # -------------------------------------------------- pipeline correctness
    def test_queries_exact(self):
        """20 tasks × 2 conds × B=3 = 120 Target queries，各条件恰 3 轮。"""
        for cond, cost in self.report["cost"].items():
            self.assertEqual(cost["q_t_target_queries"], 20 * 3)
            self.assertEqual(cost["q_g_red_calls"], 20 * 3)
            self.assertEqual(cost["q_j_judge_calls"], 20 * 3)
            self.assertEqual(cost["q_e_evaluator_calls"], 20 * 3)

    def test_initial_prompt_invariant(self):
        lines = self.report["protocol_validation"]
        self.assertTrue(any("same initial prompts" in l for l in lines))

    def test_report_fields_complete(self):
        for key in ("protocol_validation", "provenance", "backends",
                    "offline_evaluation", "cost", "metrics", "paired",
                    "stats", "target_gate", "acceptance"):
            self.assertIn(key, self.report)
        self.assertIn("model_paths", self.report["provenance"])
        self.assertIn("mcnemar_asr", self.report["stats"])
        self.assertIn("wilcoxon_ctts", self.report["stats"])

    def test_trajectories_persisted_with_cost(self):
        from memory.trajectory_store import TrajectoryStore
        for cond in ("C1", "C3"):
            path = "outputs/trajectories/{}_{}.jsonl".format(
                self.report["experiment_id"], cond)
            self.assertTrue(os.path.exists(path), path)
            trajs = TrajectoryStore.load(path)
            self.assertEqual(len(trajs), 20)
            for t in trajs:
                self.assertEqual(t.target_queries, 3)
                self.assertTrue(t.cost and "q_t_target_queries" in t.cost)
                self.assertTrue(all(
                    s.external_evaluation is not None for s in t.steps))
        # JSON 可恢复完整 experiment
        rec = json.loads(open(
            "outputs/trajectories/{}_C3.jsonl".format(
                self.report["experiment_id"]), encoding="utf-8").readline())
        self.assertEqual(rec["condition_id"], "C3")
        self.assertIn("model_paths", rec["provenance"])
        self.assertIn("cost", rec)


if __name__ == "__main__":
    unittest.main()
