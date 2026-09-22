# -*- coding: utf-8 -*-
"""Stage 1B-CP 单测：hysteresis 状态机全分支。"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.cp_coordinator import HysteresisCoordinator
from core.protocol import ExperimentProtocol
from core.schemas import (
    AttackAction, AttackStep, Feedback, JudgeOutput, SafetyTask, TargetResponse,
)
from scheduler.uniform_scheduler import UniformScheduler


def _coord():
    from core.control_layer import ControlPolicy
    return HysteresisCoordinator(
        UniformScheduler(["h"], ["direct", "roleplay"], rng=random.Random(0)),
        ControlPolicy(seed=42, enforced=True), "")


def _task():
    return SafetyTask(task_id="T", goal="g", harm_category="h",
                      metadata={"target_id": "t"})


def _proto():
    return ExperimentProtocol(experiment_id="e", condition_id="c",
                              target_query_budget=5, feedback_level="structured")


def _step(strategy, adv, pol="ALIGNED", action="SWITCH", parse="EXACT"):
    fb = Feedback(attack_success=False, outcome="", unsafe_score=0,
                  jailbreak_score=None, refusal_score=0,
                  feedback_level="structured", adaptation_action=action)
    return AttackStep(
        round_id=0,
        action=AttackAction(prompt="p{}".format(random.random()), strategy=strategy,
                            metadata={}),
        response=TargetResponse(text="r", model_name="m"),
        judge_output=JudgeOutput(
            unsafe_score=None, harm_scores={}, jailbreak_score=None,
            refusal_score=0, severity_score=None, confidence=None, outcome="",
            metadata={"advancement": adv, "polarity": pol,
                      "parse_status": parse}),
        feedback=fb)


class TestHysteresis(unittest.TestCase):
    def test_first_none_refines_second_switches(self):
        c = _coord()
        state = c.initialize(_task(), _proto())
        s1 = _step("direct", "NONE")
        state = c.transition(state, s1)
        self.assertEqual(s1.feedback.adaptation_action, "REFINE")  # n=1 → REFINE
        self.assertEqual(state.metadata["no_progress"], 1)
        s2 = _step("direct", "NONE")
        state = c.transition(state, s2)
        self.assertEqual(s2.feedback.adaptation_action, "SWITCH")  # n=2 → SWITCH
        self.assertEqual(state.metadata["no_progress"], 0)         # SWITCH 重置
        # 换族被强制执行
        self.assertNotEqual(state.current_strategy, "direct")

    def test_progress_resets_counter(self):
        c = _coord()
        state = c.initialize(_task(), _proto())
        state = c.transition(state, _step("direct", "NONE"))
        state = c.transition(state, _step("direct", "PARTIAL", action="REFINE"))
        self.assertEqual(state.metadata["no_progress"], 0)
        # 重置后再 NONE 仍是首次 → REFINE
        s = _step("direct", "NONE")
        state = c.transition(state, s)
        self.assertEqual(s.feedback.adaptation_action, "REFINE")

    def test_strong_keep_no_override(self):
        c = _coord()
        state = c.initialize(_task(), _proto())
        s = _step("direct", "STRONG", action="KEEP")
        state = c.transition(state, s)
        self.assertEqual(s.feedback.adaptation_action, "KEEP")

    def test_drifted_realign_priority_resets(self):
        c = _coord()
        state = c.initialize(_task(), _proto())
        state = c.transition(state, _step("direct", "NONE"))
        s = _step("direct", "NONE", pol="DRIFTED", action="REALIGN")
        state = c.transition(state, s)
        self.assertEqual(s.feedback.adaptation_action, "REALIGN")  # 优先级最高
        self.assertEqual(state.metadata["no_progress"], 0)

    def test_parser_failure_neither_counts_nor_overrides(self):
        c = _coord()
        state = c.initialize(_task(), _proto())
        state = c.transition(state, _step("direct", "NONE"))
        n_before = state.metadata["no_progress"]
        s = _step("direct", None, action="UNCERTAIN", parse="FAILED")
        state = c.transition(state, s)
        self.assertEqual(state.metadata["no_progress"], n_before)  # 不计数
        self.assertEqual(s.feedback.adaptation_action, "UNCERTAIN")


if __name__ == "__main__":
    unittest.main()
