# -*- coding: utf-8 -*-
"""ProtocolValidator 测试（设计文档 §33/§34）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.protocol import ExperimentProtocol
from core.protocol_validator import ProtocolValidator, ProtocolViolation
from experiments.conditions import ALLOWED_PAIR_DIFFERENCES, STAGE1_CONDITIONS

BACKENDS = {
    "red": {"backend": "template", "template_version": "red-v1"},
    "target": {"backend": "scripted", "model": "scripted-demo-1"},
    "judge": {"backend": "rule_based", "version": "rule-v0.2"},
    "evaluator": {"backend": "demo", "version": "demo-evaluator-v1"},
}


def _proto(cond_id, **overrides):
    cfg = dict(
        experiment_id="e1",
        condition_id=cond_id,
        target_query_budget=5,
        feedback_level="none",
    )
    cfg.update(overrides)
    return ExperimentProtocol(**cfg)


class TestProtocol(unittest.TestCase):
    def test_conditions_share_budget(self):
        budgets = {c: cfg["target_query_budget"]
                   for c, cfg in STAGE1_CONDITIONS.items()}
        self.assertEqual(budgets["C1"], budgets["C2"], budgets["C3"])
        self.assertEqual(budgets["C0"], 1)

    def test_validator_passes_on_feedback_only(self):
        p1 = _proto("C1", feedback_level="none")
        p3 = _proto("C3", feedback_level="structured")
        lines = ProtocolValidator.compare_protocols(
            p1, p3, backends=BACKENDS,
            allowed_differences=ALLOWED_PAIR_DIFFERENCES[frozenset(("C1", "C3"))])
        self.assertTrue(any("[DIFF] feedback_level" in l for l in lines))
        self.assertTrue(lines[-1] == "Protocol validation: PASS")

    def test_validator_blocks_budget_difference(self):
        p1 = _proto("C1", target_query_budget=5)
        p2 = _proto("C3", target_query_budget=3, feedback_level="structured")
        with self.assertRaises(ProtocolViolation):
            ProtocolValidator.compare_protocols(
                p1, p2, backends=BACKENDS, allowed_differences=["feedback_level"])

    def test_validator_blocks_scheduler_difference(self):
        p1 = _proto("C1")
        p2 = _proto("C3", feedback_level="structured", scheduler_type="risk")
        with self.assertRaises(ProtocolViolation):
            ProtocolValidator.compare_protocols(
                p1, p2, backends=BACKENDS, allowed_differences=["feedback_level"])

    def test_initial_prompt_check_raises_on_mismatch(self):
        from core.schemas import (
            AttackAction, AttackStep, AttackTrajectory, JudgeOutput,
            TargetResponse,
        )

        def _traj(cond, prompt):
            task_task = type("T", (), {})  # placeholder
            from core.schemas import SafetyTask
            task = SafetyTask(task_id="T1", goal="g", harm_category="H01")
            step = AttackStep(
                round_id=0,
                action=AttackAction(prompt=prompt, strategy="direct"),
                response=TargetResponse(text="r", model_name="m"),
                judge_output=JudgeOutput(
                    unsafe_score=0.0, harm_scores={}, jailbreak_score=0.0,
                    refusal_score=0.9, severity_score=0.0, confidence=0.9,
                    outcome="REFUSAL"),
            )
            traj = AttackTrajectory(
                trajectory_id="x", experiment_id="e", condition_id=cond,
                task=task, target_id="t")
            traj.append(step)
            return traj

        ok = {"C1": [_traj("C1", "p0")], "C3": [_traj("C3", "p0")]}
        ProtocolValidator.check_initial_prompts(ok)
        bad = {"C1": [_traj("C1", "p0")], "C3": [_traj("C3", "different")]}
        with self.assertRaises(ProtocolViolation):
            ProtocolValidator.check_initial_prompts(bad)


if __name__ == "__main__":
    unittest.main()
