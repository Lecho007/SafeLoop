# -*- coding: utf-8 -*-
"""Stage 1B-R 协议单测（16 项，scripted 后端零 GPU）。"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.goal_advancement_judge_v3 import GoalAdvancementJudgeV3
from agents.polarity_judge import PolarityJudge
from core.protocol import ExperimentProtocol
from engine.batch_runner import FEEDBACK_MODE_ACTIVE, FEEDBACK_MODE_NONE
from experiments.stage1br import (BRANCHES, SEED, _split_domains, build_branch_stack)
from utils.io import load_yaml
from utils.rng import derive_seed, seed_role

CFG = "configs/hardware/rtx4060_8g_1bb.yaml"


def _task(tid, domain):
    from core.schemas import SafetyTask
    return SafetyTask(task_id=tid, goal="g-{}".format(tid),
                      harm_category="JBB:x",
                      metadata={"feedback_observability": domain,
                                "mapping_version": "jbb_observability_v1"})


class TestRoutingManifest(unittest.TestCase):
    def test_routing_manifest_is_frozen(self):
        import json
        tasks = [json.loads(l) for l in open(
            "data/tasks/jbb100_full.jsonl", encoding="utf-8")]
        self.assertEqual(len(tasks), 100)
        from collections import Counter
        c = Counter(t["metadata"]["feedback_observability"] for t in tasks)
        self.assertEqual(c["content_observable"], 70)
        self.assertEqual(c["goal_compliance"], 30)
        self.assertTrue(all(t["metadata"]["mapping_version"] == "jbb_observability_v1"
                            for t in tasks))

    def test_domain_split(self):
        c, g = _split_domains([_task("a", "content_observable"),
                               _task("b", "goal_compliance")])
        self.assertEqual([t.task_id for t in c], ["a"])
        self.assertEqual([t.task_id for t in g], ["b"])

    def test_branch_matrix_frozen(self):
        self.assertEqual(BRANCHES["A"]["mode"], FEEDBACK_MODE_NONE)
        self.assertEqual(BRANCHES["B"]["mode"], FEEDBACK_MODE_ACTIVE)
        self.assertEqual(BRANCHES["C"]["mode"], FEEDBACK_MODE_NONE)
        self.assertEqual(BRANCHES["D"]["mode"], FEEDBACK_MODE_ACTIVE)
        self.assertEqual(sum(b["queries"] for b in BRANCHES.values()), 1000)


class TestRNGStreams(unittest.TestCase):
    def test_derive_seed_stable_and_role_scoped(self):
        s1 = derive_seed(42, "JBB-0001", 0, "red")
        s2 = derive_seed(42, "JBB-0001", 0, "red")
        self.assertEqual(s1, s2)                      # 跨调用稳定
        self.assertNotEqual(s1, derive_seed(42, "JBB-0001", 0, "target"))
        self.assertNotEqual(s1, derive_seed(42, "JBB-0001", 1, "red"))
        self.assertNotEqual(s1, derive_seed(42, "JBB-0002", 0, "red"))

    def test_shadow_does_not_change_red_rng(self):
        """judge 角色派生/消耗不影响 red 流（结构性：按 (task,round,role) 独立）。"""
        before = derive_seed(7, "T", 2, "red")
        seed_role(7, "T", 2, "judge")            # 模拟 shadow judge 调用
        _ = derive_seed(7, "T", 2, "target")
        after = derive_seed(7, "T", 2, "red")
        self.assertEqual(before, after)


class TestStackAssembly(unittest.TestCase):
    def test_content_stack_uses_real_v1_and_guard(self):
        """装配静态检查：content 支指向 HfRedAgent+real_v1+Qwen3Guard+BuilderV2（不实例化模型）。"""
        import inspect
        from experiments import stage1br
        src = inspect.getsource(stage1br.build_branch_stack)
        self.assertIn("HfRedAgent", src)
        self.assertIn("real_v1.yaml", src)
        self.assertIn("Qwen3GuardJudgeV2", src)
        self.assertIn("FeedbackBuilderV2", src)
        # goal 支
        self.assertIn("CFRedAgent", src)
        self.assertIn("enforced=False", src)
        self.assertIn("FeedbackBuilderCF", src)

    def test_goal_stack_uses_cf10(self):
        cfg = load_yaml(CFG)
        mm, red, target, judge, fb, tpl = build_branch_stack(cfg, "D")
        self.assertEqual(tpl, "cf_v1")
        self.assertEqual(red.name, "cf_red")
        self.assertFalse(red.enforced)              # CF-10 soft
        self.assertEqual(judge.name, "cf_split")

    def test_router_does_not_receive_target_response_or_evaluator(self):
        """Router 只读任务元数据（域），不接触 response/evaluator 输出。"""
        # 路由在任务装配层完成（_split_domains），签名不接 response
        import inspect
        self.assertNotIn("response", inspect.signature(_split_domains).parameters)

    def test_evaluator_runs_only_after_episode(self):
        """Evaluator 不在 BatchRunner 因果路径（结构检查）。"""
        import engine.batch_runner as br
        src = inspect.getsource(br.BatchRunner.run) if (inspect := __import__("inspect")) else ""
        self.assertNotIn("evaluator", src.lower())


class TestFeedbackModeInvariants(unittest.TestCase):
    def _run(self, mode, tasks):
        """scripted 双分支小跑：NONE 跳过 judge。"""
        from agents.red_agent import TemplateRedAgent
        from agents.safety_judge import RuleBasedJudge
        from core.coordinator_impl import HeuristicCoordinator
        from engine.batch_runner import BatchRunner
        from feedback.feedback_builder_v2 import FeedbackBuilderV2
        from memory.null_memory import NullMemory
        from scheduler.uniform_scheduler import UniformScheduler
        from targets.scripted_target import ScriptedTarget
        from core.reward import RewardConfig, RewardFunction
        cond = "TEST_{}".format(mode)
        proto = ExperimentProtocol(
            experiment_id="t", condition_id=cond, target_query_budget=2,
            feedback_level=("none" if mode == FEEDBACK_MODE_NONE else "structured"),
            metadata={"feedback_mode": mode})
        judge_calls = []

        class CountingJudge(RuleBasedJudge):
            def evaluate(self, task, action, response):
                judge_calls.append(1)
                return super().evaluate(task, action, response)

        batch = BatchRunner(
            coordinator_factory=lambda p: HeuristicCoordinator(UniformScheduler(
                ["h"], ["direct", "roleplay"], rng=random.Random(0))),
            red_agent=TemplateRedAgent(rng=random.Random(0),
                                       template_path="prompts/red/v1.yaml"),
            target=ScriptedTarget(), judge=CountingJudge(), memory=NullMemory(),
            reward_factory=lambda b: RewardFunction(RewardConfig(), b),
            feedback_builder=FeedbackBuilderV2())
        trajs = batch.run(tasks, {cond: proto})[cond]
        return trajs, judge_calls

    def test_none_mode_skips_judge_entirely(self):
        t1 = _task("T1", "content_observable")
        trajs, calls = self._run(FEEDBACK_MODE_NONE, [t1])
        self.assertEqual(calls, [])                    # judge 零调用
        for s in trajs[0].steps:
            self.assertFalse(s.judge_output.metadata.get("judge_invoked", True))
            self.assertIsNone(s.feedback)

    def test_active_mode_invokes_judge(self):
        t1 = _task("T1", "content_observable")
        trajs, calls = self._run(FEEDBACK_MODE_ACTIVE, [t1])
        self.assertEqual(len(calls), 2)                # 每轮一次
        self.assertTrue(all(s.feedback is not None for s in trajs[0].steps))

    def test_none_trajectory_matches_no_judge_reference(self):
        """NONE 模式轨迹与"无 judge 概念"的参考实现一致性：反馈恒 None。"""
        t1 = _task("T1", "content_observable")
        trajs, _ = self._run(FEEDBACK_MODE_NONE, [t1])
        for s in trajs[0].steps:
            self.assertIsNone(s.feedback)
            self.assertEqual(s.reward, 0.0)

    def test_same_initial_prompt_across_modes(self):
        """同域 NONE vs ACTIVE round-0 prompt 一致（模板同源 + round0 无反馈）。"""
        t1 = _task("T1", "content_observable")
        tr_n, _ = self._run(FEEDBACK_MODE_NONE, [t1])
        tr_a, _ = self._run(FEEDBACK_MODE_ACTIVE, [t1])
        self.assertEqual(tr_n[0].steps[0].action.prompt,
                         tr_a[0].steps[0].action.prompt)

    def test_shadow_feedback_not_in_red_context(self):
        """SHADOW：judge 输出仅落盘，feedback=None（在线形态协议测试）。"""
        from engine.batch_runner import FEEDBACK_MODE_SHADOW
        t1 = _task("T1", "content_observable")
        trajs, calls = self._run(FEEDBACK_MODE_SHADOW, [t1])
        self.assertGreater(len(calls), 0)              # judge 被调用（旁路观测）
        for s in trajs[0].steps:
            self.assertIsNone(s.feedback)              # 但反馈不进 red


if __name__ == "__main__":
    unittest.main()
