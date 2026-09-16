# -*- coding: utf-8 -*-
"""Schema 测试：roundtrip 与 JSONL 序列化（设计文档 §47）。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.schemas import (
    AttackAction,
    AttackStep,
    AttackTrajectory,
    EvaluationResult,
    Feedback,
    JudgeOutput,
    SafetyTask,
    TargetResponse,
)


def _make_trajectory():
    task = SafetyTask(task_id="T0001", goal="goal", harm_category="H01")
    step = AttackStep(
        round_id=0,
        action=AttackAction(prompt="p", strategy="direct", strategy_family="plain",
                            metadata={"prompt_id": "abc"}),
        response=TargetResponse(text="r", model_name="demo"),
        judge_output=JudgeOutput(
            unsafe_score=0.9, harm_scores={"H01": 0.9}, jailbreak_score=0.9,
            refusal_score=0.1, severity_score=0.8, confidence=0.9,
            outcome="FULL_COMPLIANCE", rationale="ok"),
        feedback=Feedback(attack_success=True, outcome="FULL_COMPLIANCE",
                          unsafe_score=0.9, jailbreak_score=0.9, refusal_score=0.1,
                          failure_type=None, guidance="keep",
                          feedback_level="structured"),
        reward=0.7,
        online_success=True,
        external_evaluation=EvaluationResult(
            success=True, jailbreak_score=0.9, unsafe_score=0.9,
            outcome="FULL_COMPLIANCE", severity_score=0.8, confidence=0.9,
            evaluator_id="demo-evaluator-v1"),
    )
    traj = AttackTrajectory(
        trajectory_id="t1", experiment_id="e1", condition_id="C3",
        task=task, target_id="tgt", initial_prompt="p",
        final_evaluation=step.external_evaluation, target_queries=1,
        success=True, stop_reason="budget_exhausted",
        provenance={"seed": 42},
    )
    traj.append(step)
    return traj


class TestSchemas(unittest.TestCase):
    def test_trajectory_roundtrip(self):
        traj = _make_trajectory()
        restored = AttackTrajectory.from_dict(json.loads(json.dumps(
            traj.to_dict(), ensure_ascii=False)))
        self.assertEqual(restored.task.task_id, "T0001")
        self.assertEqual(restored.condition_id, "C3")
        self.assertEqual(len(restored.steps), 1)
        s = restored.steps[0]
        self.assertEqual(s.action.strategy, "direct")
        self.assertEqual(s.action.prompt_id, "abc")
        self.assertEqual(s.judge_output.outcome, "FULL_COMPLIANCE")
        self.assertTrue(s.feedback.attack_success)
        self.assertTrue(s.external_evaluation.success)
        self.assertEqual(restored.final_evaluation.evaluator_id, "demo-evaluator-v1")

    def test_jsonl_serialization(self):
        traj = _make_trajectory()
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl",
                                         delete=False, encoding="utf-8") as f:
            f.write(json.dumps(traj.to_dict(), ensure_ascii=False) + "\n")
            path = f.name
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.loads(f.readline())
            self.assertEqual(rec["steps"][0]["action"]["strategy"], "direct")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
