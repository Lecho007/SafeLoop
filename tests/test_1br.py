# -*- coding: utf-8 -*-
"""1B-R 组件单测：Router 确定性路由/未选 judge 不被调用、hierarchical bootstrap、
stage1bb 装配防回归。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.task_aware_router import ROUTER_VERSION, TaskAwareJudgeRouter
from core.schemas import (
    AttackAction,
    JudgeOutput,
    SafetyTask,
    TargetResponse,
)
from utils.io import load_yaml


class _FakeJudge:
    def __init__(self, name):
        self.name = name
        self.calls = 0

    def _ensure_loaded(self):
        pass

    def _unload(self):
        pass

    def evaluate(self, task, action, response):
        self.calls += 1
        return JudgeOutput(
            unsafe_score=0.0, harm_scores={}, jailbreak_score=None,
            refusal_score=0.0, severity_score=None, confidence=None,
            outcome="X", metadata={"judge": self.name})


def _task(obs):
    return SafetyTask(task_id="T", goal="g", harm_category="JBB:Expert advice",
                      metadata={"feedback_observability": obs,
                                "mapping_version": "jbb_observability_v1"})


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.content = _FakeJudge("content")
        self.goal = _FakeJudge("goal")
        self.router = TaskAwareJudgeRouter(self.content, self.goal)

    def test_deterministic_routing(self):
        self.assertEqual(self.router.route(_task("content_observable")), "content")
        self.assertEqual(self.router.route(_task("goal_compliance")), "goal")

    def test_unselected_judge_never_called(self):
        out = self.router.evaluate(
            _task("goal_compliance"), AttackAction(prompt="p", strategy="s"),
            TargetResponse(text="r", model_name="m"))
        self.assertEqual(self.goal.calls, 1)
        self.assertEqual(self.content.calls, 0)   # One Task → One Primary Judge
        self.assertEqual(out.metadata["selected_judge"], "goal")
        self.assertEqual(out.metadata["router_version"], ROUTER_VERSION)

    def test_missing_observability_raises(self):
        with self.assertRaises(ValueError):
            self.router.route(SafetyTask(task_id="T2", goal="g", harm_category="x"))


class TestHierarchicalBootstrap(unittest.TestCase):
    def test_known_effect(self):
        from core.schemas import (
            AttackStep, AttackTrajectory, EvaluationResult,
        )

        def _traj(tid, success):
            t = AttackTrajectory(
                trajectory_id=tid, experiment_id="e", condition_id="c",
                task=SafetyTask(task_id=tid, goal="g", harm_category="h"),
                target_id="x")
            s = AttackStep(
                round_id=0, action=AttackAction(prompt="p", strategy="s"),
                response=TargetResponse(text="r", model_name="m"),
                judge_output=JudgeOutput(
                    unsafe_score=0, harm_scores={}, jailbreak_score=None,
                    refusal_score=0, severity_score=None, confidence=None,
                    outcome="X"),
                external_evaluation=EvaluationResult(
                    success=success, jailbreak_score=0, unsafe_score=0, outcome="",
                    severity_score=0, confidence=1, evaluator_id="t"))
            t.append(s)
            return t

        pairs = {"42": [(_traj("T1", False), _traj("T1", True)),
                        (_traj("T2", False), _traj("T2", True))],
                 "123": [(_traj("T1", False), _traj("T1", True))]}
        from evaluation.stats import hierarchical_paired_bootstrap
        r = hierarchical_paired_bootstrap(
            pairs, lambda t: 1.0 if t.steps[0].external_evaluation.success else 0.0)
        self.assertAlmostEqual(r["delta"], 1.0, places=6)
        self.assertEqual(r["n_tasks"], 2)
        self.assertEqual(r["n_seeds"], 2)


class Test1BRConfig(unittest.TestCase):
    def test_config_and_assembly(self):
        cfg = load_yaml("configs/hardware/rtx4060_8g_1br.yaml")
        self.assertEqual(cfg["experiment"]["tasks_file"],
                         "data/tasks/jbb100_full.jsonl")
        self.assertEqual(cfg["protocol"]["target_query_budget"], 5)
        self.assertEqual(cfg["router"]["mapping_version"], "jbb_observability_v1")
        self.assertEqual(cfg["goal_judge"]["model_path"],
                         "weights/red/Qwen3-1.7B")
        self.assertEqual(cfg["judge"]["model_path"],
                         "weights/judge/Qwen3Guard-Gen-0.6B")
        # stage1br 装配：C_R 走 routed，两路模型路径正确
        from experiments.stage1br import CONDITIONS, Stage1BRExperiment
        bundle = Stage1BRExperiment(cfg, "configs/hardware/rtx4060_8g_1br.yaml"
                                    )._condition_bundle(CONDITIONS["C_R"])
        self.assertEqual(bundle.judge.name, "routed")
        self.assertEqual(bundle.judge.content_judge.model_path,
                         "weights/judge/Qwen3Guard-Gen-0.6B")
        self.assertEqual(bundle.judge.goal_judge.model_path,
                         "weights/red/Qwen3-1.7B")
        # stage1bb 防回归：goal_compliance 条件必须用 goal_judge 路径
        from experiments.stage1bb import _judge_cfg_for
        g = _judge_cfg_for(cfg, "goal_compliance")["judge"]
        self.assertEqual(g["model_path"], cfg["goal_judge"]["model_path"])


if __name__ == "__main__":
    unittest.main()
