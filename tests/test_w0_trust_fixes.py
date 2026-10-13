# -*- coding: utf-8 -*-
"""W0 信任修复单测：asr_at_budget 统一口径 / 真取消 / 断点续跑 / 真实 run 回放。

全部零 GPU：取消与续跑用 template/scripted 后端走同一 round-batched 管道。
"""
import json
import os
import random
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "apps", "workbench"))

from evaluation.metrics import asr_at_budget
from safeloop.skills.replay_loader import load_prerun_as_agent, load_run_branches


class TestAsrAtBudget(unittest.TestCase):
    def test_explicit_field_wins(self):
        self.assertEqual(
            asr_at_budget({"asr_at_budget": 0.4, "asr_at_k": {"3": 0.9}}), 0.4)

    def test_curve_by_budget_then_max_key(self):
        m = {"asr_at_k": {"1": 0.5, "3": 1.0}}
        self.assertEqual(asr_at_budget(m, 3), 1.0)
        self.assertEqual(asr_at_budget(m), 1.0)
        self.assertEqual(asr_at_budget(m, 5), 1.0)  # 无 5 键 → 最大键兜底

    def test_legacy_float_and_garbage(self):
        self.assertEqual(asr_at_budget({"asr_at_k": 0.25}), 0.25)
        self.assertIsNone(asr_at_budget({"asr_at_k": {}}))
        self.assertIsNone(asr_at_budget({}))
        self.assertIsNone(asr_at_budget(None))
        self.assertIsNone(asr_at_budget({"asr_at_k": {"x": 1}}))


class TestReportAsrField(unittest.TestCase):
    def test_report_contains_asr_at_budget(self):
        from core.schemas import (AttackAction, AttackStep, AttackTrajectory,
                                  AttackTrajectory as _AT, EvaluationResult,
                                  JudgeOutput, SafetyTask, TargetResponse)
        from safeloop.skills.report import ReportSkill
        from types import SimpleNamespace as NS

        def step(round_id, ok):
            return AttackStep(
                round_id=round_id,
                action=AttackAction(prompt="p{}".format(round_id),
                                    strategy="direct"),
                response=TargetResponse(text="r", model_name="t"),
                judge_output=JudgeOutput(
                    unsafe_score=0.0, harm_scores={}, jailbreak_score=None,
                    refusal_score=0.0, severity_score=None, confidence=None,
                    outcome="", rationale=""),
                reward=0.0,
                external_evaluation=(
                    EvaluationResult(success=ok, jailbreak_score=0.0,
                                     unsafe_score=0.0, outcome="", severity_score=0.0,
                                     confidence=0.0, evaluator_id="stub")
                    if ok is not None else None))

        def traj(tid, oks):
            task = SafetyTask(task_id=tid, goal="g", harm_category="JBB:Privacy")
            t = AttackTrajectory(trajectory_id="tr-{}".format(tid),
                                 experiment_id="run-t", condition_id="STD",
                                 task=task, target_id="phi")
            for i, ok in enumerate(oks):
                t.append(step(i, ok))
            return t

        plan = NS(request=NS(mode="standard", budget_per_task=3,
                             target_model="phi-3.5-mini", suite="jbb100"),
                  branches=[])
        rep = ReportSkill().build("run-t", plan, {"STD": [
            traj("T1", [False, True, False]), traj("T2", [False, False, False])]})
        ul = rep["metrics"]["user_layer"]
        self.assertEqual(ul["asr_at_budget"], 0.5)
        self.assertEqual(ul["asr_at_k"]["3"], 0.5)
        # 旧报告（无显式字段）经统一口径也能读对
        self.assertEqual(asr_at_budget(ul, 3), 0.5)
        self.assertEqual(asr_at_budget({"asr_at_k": ul["asr_at_k"]}, 3), 0.5)


def _scripted_stack(cancel_after_rounds=None, checkpoint_path=None):
    """零 GPU BatchRunner：template 红 + scripted 被测 + 规则裁判。"""
    from agents.red_agent import TemplateRedAgent
    from agents.safety_judge import RuleBasedJudge
    from core.coordinator_impl import HeuristicCoordinator
    from core.protocol import ExperimentProtocol
    from core.reward import RewardConfig, RewardFunction
    from engine.batch_runner import BatchRunner
    from feedback.feedback_builder_v2 import FeedbackBuilderV2
    from memory.null_memory import NullMemory
    from scheduler.uniform_scheduler import UniformScheduler
    from targets.scripted_target import ScriptedTarget

    cancel_flag = {"on": False}

    def _should_cancel():
        return cancel_flag["on"]

    proto = ExperimentProtocol(
        experiment_id="t", condition_id="C1", target_query_budget=3,
        feedback_level="none",
        metadata={"feedback_mode": "NONE"})
    batch = BatchRunner(
        coordinator_factory=lambda p: HeuristicCoordinator(UniformScheduler(
            ["h"], ["direct", "roleplay"], rng=random.Random(0))),
        red_agent=TemplateRedAgent(rng=random.Random(0),
                                   template_path="prompts/red/v1.yaml"),
        target=ScriptedTarget(), judge=RuleBasedJudge(), memory=NullMemory(),
        reward_factory=lambda b: RewardFunction(RewardConfig(), b),
        feedback_builder=FeedbackBuilderV2(), should_cancel=_should_cancel)
    return batch, proto, cancel_flag


def _two_tasks():
    from core.schemas import SafetyTask
    return [SafetyTask(task_id="T{}".format(i), goal="goal {}".format(i),
                       harm_category="JBB:Privacy") for i in (1, 2)]


class TestGracefulCancel(unittest.TestCase):
    def test_cancel_stops_at_round_boundary(self):
        batch, proto, flag = _scripted_stack()
        seen = {"rounds": 0}

        def _on_step(step, slot):
            seen["rounds"] = step.round_id + 1
            if seen["rounds"] >= 1:      # 第一轮完成后请求取消
                flag["on"] = True

        batch.on_step = _on_step
        trajs = batch.run(_two_tasks(), {"C1": proto})["C1"]
        self.assertTrue(batch.cancelled)
        self.assertEqual(len(trajs), 2)
        for t in trajs:
            self.assertEqual(len(t.steps), 1)          # 不再发起第 2/3 轮调用
            self.assertEqual(t.stop_reason, "cancelled")

    def test_no_cancel_runs_full_budget(self):
        batch, proto, _ = _scripted_stack()
        trajs = batch.run(_two_tasks(), {"C1": proto})["C1"]
        self.assertFalse(batch.cancelled)
        for t in trajs:
            self.assertEqual(len(t.steps), 3)
            self.assertNotEqual(t.stop_reason, "cancelled")


class TestResume(unittest.TestCase):
    def test_resume_extends_budget(self):
        from core.protocol import ExperimentProtocol
        tmp = tempfile.mkdtemp()
        try:
            ckpt = os.path.join(tmp, "ck.json")
            batch, _, _ = _scripted_stack()
            p2 = ExperimentProtocol(experiment_id="t", condition_id="C1",
                                    target_query_budget=2, feedback_level="none",
                                    metadata={"feedback_mode": "NONE"})
            trajs = batch.run(_two_tasks(), {"C1": p2},
                              checkpoint_path=ckpt)["C1"]
            self.assertTrue(all(len(t.steps) == 2 for t in trajs))
            # 续跑：预算扩到 3，从检查点继续（只补第 3 轮）
            batch2, _, _ = _scripted_stack()
            p3 = ExperimentProtocol(experiment_id="t", condition_id="C1",
                                    target_query_budget=3, feedback_level="none",
                                    metadata={"feedback_mode": "NONE"})
            trajs2 = batch2.run(_two_tasks(), {"C1": p3},
                                checkpoint_path=ckpt, resume=True)["C1"]
            self.assertTrue(all(len(t.steps) == 3 for t in trajs2))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestReplayLoaderRealRun(unittest.TestCase):
    def _mk_traj(self):
        from core.schemas import (AttackTrajectory, SafetyTask)
        task = SafetyTask(task_id="T1", goal="g", harm_category="JBB:Privacy")
        return AttackTrajectory(trajectory_id="tr-1", experiment_id="run-x",
                                condition_id="STD", task=task, target_id="phi")

    def test_real_run_id_loads_and_marks_not_demo(self):
        from memory.trajectory_store import TrajectoryStore
        tmp = tempfile.mkdtemp()
        try:
            store = TrajectoryStore(output_dir=os.path.join(tmp, "evaluations"))
            store.save(self._mk_traj(), "run-x_STD")
            agent = load_prerun_as_agent("run-x", outputs_dir=tmp)
            self.assertFalse(agent.is_demo)
            self.assertEqual(len(agent.trajectories["STD"]), 1)
            self.assertEqual(agent.state, "COMPLETED")
            self.assertIsNotNone(agent.report)
            self.assertEqual(
                load_run_branches("run-x", outputs_dir=tmp).keys(), {"STD"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_id_falls_back_to_demo_labeled(self):
        # 无对应文件 → 演示数据路径（真实仓库 1B-R 产物），必须标记 is_demo
        agent = load_prerun_as_agent("stage1b_r_4060")
        self.assertTrue(agent.is_demo)
        self.assertTrue(agent.trajectories["STD"])


if __name__ == "__main__":
    unittest.main()
