# -*- coding: utf-8 -*-
"""决策树节点模型单测（trajectory/events 归一化 + 事件点亮规则）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "apps", "workbench"))

from tree_model import (ACTION_ZH, SIGNAL_OF_ADVANCEMENT, events_to_tree,
                        node_css_state, trajectory_to_nodes)


def _step(round_id, strategy, adv, action, success=False):
    from core.schemas import (AttackAction, AttackStep, Feedback,
                              JudgeOutput, TargetResponse)
    fb = None
    if action:
        fb = Feedback(attack_success=False, outcome="", unsafe_score=0,
                      jailbreak_score=None, refusal_score=0,
                      feedback_level="structured", adaptation_action=action)
    jo = JudgeOutput(unsafe_score=None, harm_scores={}, jailbreak_score=None,
                     refusal_score=None, severity_score=None, confidence=None,
                     outcome="", metadata={"advancement": adv})
    jo.metadata["advancement"] = adv
    step = AttackStep(round_id=round_id,
                      action=AttackAction(prompt="p", strategy=strategy,
                                          metadata={}),
                      response=TargetResponse(text="r", model_name="m"),
                      judge_output=jo, feedback=fb)
    if success:
        from core.schemas import EvaluationResult
        step.external_evaluation = EvaluationResult(
            success=True, jailbreak_score=1, unsafe_score=1, outcome="",
            severity_score=0, confidence=1, evaluator_id="t")
    return step


class _Traj:
    def __init__(self, steps):
        self.steps = steps


class TestTrajectoryNodes(unittest.TestCase):
    def test_node_model(self):
        nodes = trajectory_to_nodes(_Traj([
            _step(0, "direct", "NONE", "REFINE"),
            _step(1, "roleplay", "PARTIAL", "KEEP"),
        ]))
        self.assertEqual(nodes[0]["round"], 1)                 # +1 人话轮次
        self.assertEqual(nodes[0]["strategy"], "direct")
        self.assertEqual(nodes[0]["signal"], "safe")           # NONE → safe
        self.assertEqual(nodes[1]["signal"], "warn")           # PARTIAL → warn
        self.assertEqual(nodes[1]["action"], "KEEP")

    def test_strong_maps_risk(self):
        nodes = trajectory_to_nodes(
            _Traj([_step(0, "direct", "STRONG", None, success=True)]))
        self.assertEqual(nodes[0]["signal"], "risk")
        self.assertTrue(nodes[0]["success"])


class TestEventTree(unittest.TestCase):
    EVENTS = [
        {"type": "session_started", "task_id": "JBB-0030",
         "harm_category": "JBB:Economic harm"},
        {"type": "round_started", "round": 1},
        {"type": "red_message", "round": 1},
        {"type": "judge_message", "round": 1, "selected_judge": "goal",
         "signal": "NO_GOAL_ADVANCEMENT", "outcome": "REFUSAL"},
        {"type": "control_message", "round": 1, "action": "REFINE"},
        {"type": "round_started", "round": 2},
        {"type": "judge_message", "round": 2, "signal": "GOAL_ADVANCEMENT"},
        {"type": "control_message", "round": 2, "decision": "KEEP"},
        {"type": "session_complete", "rounds": 2, "success": True},
    ]

    def test_events_to_tree_full_flow(self):
        tree = events_to_tree(self.EVENTS)
        self.assertEqual(tree["root"]["task_id"], "JBB-0030")
        self.assertEqual(tree["root"]["domain"], "goal")       # 经济损害 → goal 域
        self.assertTrue(tree["root"]["done"])
        self.assertEqual(tree["root"]["verdict"], "风险确认")
        self.assertEqual(len(tree["rounds"]), 2)
        self.assertEqual(tree["rounds"][0]["signal"], "safe")  # 拒绝 → safe
        self.assertEqual(tree["rounds"][0]["action"], "REFINE")
        self.assertEqual(tree["rounds"][1]["signal"], "risk")
        self.assertEqual(tree["rounds"][1]["action"], "KEEP")

    def test_content_domain_routing(self):
        tree = events_to_tree([
            {"type": "session_started", "task_id": "T",
             "harm_category": "JBB:Malware/Hacking"}])
        self.assertEqual(tree["root"]["domain"], "content")

    def test_partial_signal(self):
        tree = events_to_tree([
            {"type": "session_started", "task_id": "T",
             "harm_category": "JBB:Privacy"},
            {"type": "round_started", "round": 1},
            {"type": "judge_message", "round": 1,
             "signal": "PARTIAL_ADVANCEMENT"}])
        self.assertEqual(tree["rounds"][0]["signal"], "warn")

    def test_action_zh_complete(self):
        for a in ("KEEP", "REFINE", "SWITCH", "REALIGN", "UNCERTAIN"):
            self.assertIn(a, ACTION_ZH)


if __name__ == "__main__":
    unittest.main()
