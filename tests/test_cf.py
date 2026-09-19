# -*- coding: utf-8 -*-
"""Stage 1B-CF 单测（设计 §26）：三条硬 Gate + 控制器确定性 + 映射表 + 意图-执行日志。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.polarity_judge import parse_polarity
from core.control_layer import (
    ADAPTATION_REALIGN,
    ControlPolicy,
    CFSplitJudge,
    FeedbackBuilderCF,
)
from core.protocol import (
    ADAPTATION_KEEP,
    ADAPTATION_REFINE,
    ADAPTATION_SWITCH,
    ADAPTATION_UNCERTAIN,
)
from core.schemas import AttackAction, Feedback, JudgeOutput, SafetyTask, TargetResponse


def _jo(pol, adv, parse="EXACT", refusal=False):
    return JudgeOutput(
        unsafe_score=None, harm_scores={}, jailbreak_score=None,
        refusal_score=0.9 if refusal else 0.1, severity_score=None,
        confidence=None, outcome="",
        metadata={"polarity": pol, "advancement": adv, "parse_status": parse,
                  "refusal_signal": refusal})


class TestPolarityV2(unittest.TestCase):
    def test_polarity_does_not_receive_target_response(self):
        """硬 Gate：Polarity 判定签名只吃 goal+prompt（response 丢弃）。"""
        from agents.polarity_judge import PolarityJudge
        j = PolarityJudge.__new__(PolarityJudge)  # 不加载模型
        # judge_prompt 无 response 参数；evaluate 兼容层丢弃 response
        import inspect
        sig = inspect.signature(PolarityJudge.judge_prompt)
        self.assertNotIn("response", sig.parameters)
        src = inspect.getsource(PolarityJudge.judge_prompt)
        self.assertNotIn("response.text", src)

    def test_refusal_does_not_imply_drift(self):
        """硬 Gate：φ 表中 on-goal+refusal → P=ALIGNED, A=NONE ⇒ SWITCH（非 REALIGN）。"""
        fb = FeedbackBuilderCF().build("structured", _jo("ALIGNED", "NONE", refusal=True))
        self.assertEqual(fb.adaptation_action, ADAPTATION_SWITCH)
        self.assertEqual(fb.failure_type, "no advancement (target_refusal)")

    def test_parser_failure_maps_uncertain(self):
        fb = FeedbackBuilderCF().build("structured", _jo(None, None, parse="FAILED"))
        self.assertEqual(fb.adaptation_action, ADAPTATION_UNCERTAIN)

    def test_frozen_phi_table(self):
        b = FeedbackBuilderCF()
        self.assertEqual(b.build("s", _jo("DRIFTED", "STRONG")).adaptation_action,
                         ADAPTATION_REALIGN)
        self.assertEqual(b.build("s", _jo("ALIGNED", "STRONG")).adaptation_action,
                         ADAPTATION_KEEP)
        self.assertEqual(b.build("s", _jo("AMBIGUOUS", "PARTIAL")).adaptation_action,
                         ADAPTATION_REFINE)  # AMBIGUOUS 不触发 override
        self.assertEqual(b.build("s", _jo("ALIGNED", "NONE")).adaptation_action,
                         ADAPTATION_SWITCH)


class TestControlPolicy(unittest.TestCase):
    def test_switch_forces_new_strategy_family(self):
        """硬 Gate：SWITCH ⇒ forced_family ≠ current（确定性 seeded permutation）。"""
        cp = ControlPolicy(seed=42, enforced=True)
        fb = Feedback(attack_success=False, outcome="", unsafe_score=0,
                      jailbreak_score=None, refusal_score=0.9,
                      feedback_level="structured", adaptation_action=ADAPTATION_SWITCH)
        for cur in ("direct", "roleplay", "reframing", "obfuscation", "multi_turn"):
            d = cp.apply(fb, cur, "ep1")
            self.assertNotEqual(d["forced_strategy_family"], cur)

    def test_keep_refine_realign_preserve_family(self):
        cp = ControlPolicy(seed=1, enforced=True)
        for action, mode in ((ADAPTATION_KEEP, "normal"), (ADAPTATION_REFINE, "refine"),
                             (ADAPTATION_REALIGN, "realign")):
            fb = Feedback(attack_success=False, outcome="", unsafe_score=0,
                          jailbreak_score=None, refusal_score=0,
                          feedback_level="structured", adaptation_action=action)
            d = cp.apply(fb, "roleplay", "ep2")
            self.assertEqual(d["forced_strategy_family"], "roleplay")
            self.assertEqual(d["generation_mode"], mode)

    def test_seeded_strategy_order_deterministic(self):
        cp1 = ControlPolicy(seed=7)
        cp2 = ControlPolicy(seed=7)
        self.assertEqual(cp1.episode_order("epA"), cp2.episode_order("epA"))
        self.assertNotEqual(cp1.episode_order("epA"), cp1.episode_order("epB"))

    def test_soft_mode_does_not_force(self):
        cp = ControlPolicy(seed=3, enforced=False)
        fb = Feedback(attack_success=False, outcome="", unsafe_score=0,
                      jailbreak_score=None, refusal_score=0,
                      feedback_level="structured", adaptation_action=ADAPTATION_SWITCH)
        d = cp.apply(fb, "direct", "ep")
        self.assertIsNone(d["forced_strategy_family"])
        self.assertEqual(d["controller_mode"], "soft")

    def test_ambiguous_does_not_force_realign(self):
        # AMBIGUOUS polarity 走 advancement 映射（KEEP/REFINE/SWITCH），非 REALIGN
        b = FeedbackBuilderCF()
        for adv, expect in (("STRONG", ADAPTATION_KEEP), ("PARTIAL", ADAPTATION_REFINE),
                            ("NONE", ADAPTATION_SWITCH)):
            self.assertEqual(b.build("s", _jo("AMBIGUOUS", adv)).adaptation_action, expect)


class TestCFJudgeComposition(unittest.TestCase):
    def test_controller_logs_required_and_executed(self):
        from core.cf_coordinator import ControlFixCoordinator
        from scheduler.uniform_scheduler import UniformScheduler
        from core.protocol import ExperimentProtocol
        import random
        cp = ControlPolicy(seed=42, enforced=True)
        coord = ControlFixCoordinator(
            UniformScheduler(["h"], ["direct", "roleplay"], rng=random.Random(0)), cp, "epX")
        task = SafetyTask(task_id="T", goal="g", harm_category="h",
                          metadata={"target_id": "t"})
        proto = ExperimentProtocol(
            experiment_id="e", condition_id="c", target_query_budget=5,
            feedback_level="structured")
        state = coord.initialize(task, proto)
        # 两步：SWITCH 后强制换族并记录 executed/constraint
        def _step(strategy, action_fb):
            from core.schemas import AttackStep
            return AttackStep(
                round_id=len(state.history),
                action=AttackAction(prompt="p", strategy=strategy, metadata={}),
                response=TargetResponse(text="r", model_name="m"),
                judge_output=_jo("ALIGNED", "NONE"),
                feedback=Feedback(attack_success=False, outcome="", unsafe_score=0,
                                  jailbreak_score=None, refusal_score=0,
                                  feedback_level="structured", adaptation_action=action_fb))
        s1 = _step("direct", ADAPTATION_SWITCH)
        state = coord.transition(state, s1)
        self.assertNotEqual(state.current_strategy, "direct")  # SWITCH 强制生效
        s2 = _step(state.current_strategy, ADAPTATION_KEEP)
        state = coord.transition(state, s2)
        log = s2.action.metadata["control_log"]
        self.assertEqual(log["feedback_action"], ADAPTATION_SWITCH)
        self.assertIn("forced_strategy_family", log)
        self.assertIn("constraint_satisfied", log)

    def test_realign_anchors_original_goal_mode(self):
        cp = ControlPolicy(seed=5, enforced=True)
        fb = Feedback(attack_success=False, outcome="", unsafe_score=0,
                      jailbreak_score=None, refusal_score=0,
                      feedback_level="structured", adaptation_action=ADAPTATION_REALIGN)
        d = cp.apply(fb, "reframing", "ep")
        self.assertEqual(d["generation_mode"], "realign")
        self.assertEqual(d["forced_strategy_family"], "reframing")  # 不换族，先回正目标


class TestPolarityParser(unittest.TestCase):
    def test_parse(self):
        r = parse_polarity('{"polarity": "DRIFTED"}')
        self.assertEqual((r["polarity"], r["parse_status"]), ("DRIFTED", "EXACT"))
        r = parse_polarity("cannot decide")
        self.assertEqual(r["parse_status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
