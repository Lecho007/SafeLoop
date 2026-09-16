# -*- coding: utf-8 -*-
"""V0.3 新指标单测：CTTS / FRR / ESSR（设计 §26/§27）。"""
import os
import sys
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
from evaluation.metrics import (
    ctts,
    effective_strategy_switch_rate,
    feedback_response_rate,
    mean_ctts,
)


def _step(round_id, strategy, prompt, feedback=None, ext_success=None):
    return AttackStep(
        round_id=round_id,
        action=AttackAction(prompt=prompt, strategy=strategy,
                            metadata={"prompt_id": "p{}".format(round_id)}),
        response=TargetResponse(text="r", model_name="m"),
        judge_output=JudgeOutput(
            unsafe_score=0.0, harm_scores={}, jailbreak_score=0.0,
            refusal_score=0.9, severity_score=0.0, confidence=0.9,
            outcome="REFUSAL"),
        feedback=feedback,
        external_evaluation=EvaluationResult(
            success=ext_success, jailbreak_score=0.0, unsafe_score=0.0,
            outcome="", severity_score=0.0, confidence=1.0,
            evaluator_id="t") if ext_success is not None else None,
    )


def _traj(steps):
    t = AttackTrajectory(
        trajectory_id="t", experiment_id="e", condition_id="C3",
        task=SafetyTask(task_id="T", goal="g", harm_category="H"),
        target_id="tgt")
    for s in steps:
        t.append(s)
    return t


def _fb(level, failure_type=None, attack_success=False):
    return Feedback(
        attack_success=attack_success, outcome="REFUSAL", unsafe_score=0.05,
        jailbreak_score=0.05, refusal_score=0.9, failure_type=failure_type,
        feedback_level=level)


class TestV03Metrics(unittest.TestCase):
    def test_ctts_success_and_failure(self):
        success = _traj([
            _step(0, "direct", "a"),
            _step(1, "roleplay", "b", ext_success=True),
        ])
        self.assertEqual(ctts(success, 5), 2)
        failure = _traj([_step(0, "direct", "a")])
        self.assertEqual(ctts(failure, 5), 6)  # B+1 截尾
        self.assertEqual(mean_ctts([success, failure], 5), 4.0)

    def test_frr(self):
        # 两轮：round0 有 actionable structured 反馈；round1 换策略 → FRR=1
        adapted = _traj([
            _step(0, "direct", "a", feedback=_fb("structured", "strategy ineffective")),
            _step(1, "roleplay", "b"),
        ])
        adapted.steps[1].action.metadata["feedback_used"] = True
        self.assertEqual(feedback_response_rate([adapted]), 1.0)
        # 忽略反馈（同策略同 prompt）→ FRR=0
        ignored = _traj([
            _step(0, "direct", "a", feedback=_fb("structured", "strategy ineffective")),
            _step(1, "direct", "a"),
        ])
        self.assertEqual(feedback_response_rate([ignored]), 0.0)
        # 无反馈条件 → None
        none_fb = _traj([_step(0, "direct", "a"), _step(1, "direct", "b")])
        self.assertIsNone(feedback_response_rate([none_fb]))

    def test_essr(self):
        # 一次切换 fail→success，一次切换 fail→fail → ESSR=0.5
        traj = _traj([
            _step(0, "direct", "a", ext_success=False),
            _step(1, "roleplay", "b", ext_success=True),
            _step(2, "reframing", "c", ext_success=False),
        ])
        self.assertEqual(effective_strategy_switch_rate([traj]), 0.5)


if __name__ == "__main__":
    unittest.main()
