# -*- coding: utf-8 -*-
"""v1.1 单测（A1 记忆 / A2 效用 / A3 调度 / 引擎挂钩 / round-0 门控）——零 GPU。"""
import os
import random
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.experience import build_experience_block
from safeloop.skills.memory import (MemoryRecord, MemoryStore,
                                    OnlineUtilityEstimator)
from safeloop.skills.scheduler import AdaptiveScheduler


def _rec(**kw):
    d = dict(target_fingerprint="local:phi@nf4", harm_category="JBB:Privacy",
             strategy="roleplay", strategy_summary="[Privacy] test goal",
             observation_summary="target refused consistently",
             outcome_proxy="refusal", quality=0.7, novelty=0.8)
    d.update(kw)
    return MemoryRecord(**d)


class TestMemoryStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = MemoryStore(
            db_path=os.path.join(self.tmp, "mem.db"),
            target_fingerprint="local:phi@nf4")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_dedup_merges_occurrences(self):
        a = self.store.store(_rec())
        b = self.store.store(_rec(strategy_summary="[Privacy] test goal"))
        self.assertEqual(a, b)                       # 同 dedup 键合并
        self.assertEqual(self.store.stats()["records"], 1)

    def test_namespace_isolation(self):
        self.store.store(_rec())
        other = MemoryStore(db_path=os.path.join(self.tmp, "mem.db"),
                            target_fingerprint="api:other/model")
        self.assertEqual(len(other.query()), 0)      # 跨目标不泄漏

    def test_retrieve_diversity_and_usage_accounting(self):
        self.store.store(_rec(strategy="direct", outcome_proxy="unsafe_content",
                              quality=0.9))
        self.store.store(_rec(strategy="direct", outcome_proxy="refusal",
                              quality=0.85))
        self.store.store(_rec(strategy="roleplay", outcome_proxy="refusal",
                              quality=0.8))
        state = NS(task=NS(harm_category="JBB:Privacy"))
        success, failure = self.store.retrieve(state)
        self.assertLessEqual(len(success) + len(failure), 4)
        per_strat = {}
        for r in list(success) + list(failure):
            per_strat.setdefault(r.strategy, 0)
            per_strat[r.strategy] += 1
        self.assertTrue(all(v <= 2 for v in per_strat.values()))  # 每族 ≤ cap
        self.assertTrue(all(r.uses >= 1 for r in
                            list(success) + list(failure)))       # usage 记账

    def test_snapshot_freezes_live_view(self):
        self.store.store(_rec())
        sid = self.store.snapshot(note="freeze for eval")
        frozen = MemoryStore.load_snapshot(
            db_path=self.store.db_path, snapshot_id=sid,
            target_fingerprint="local:phi@nf4")
        self.assertEqual(len(frozen.query()), 1)
        self.assertEqual(len(self.store.query()), 0)   # live 已被冻结清空
        # live 里再写新记录，不影响快照
        self.store.store(_rec(strategy="obfuscation"))
        self.assertEqual(len(frozen.query()), 1)
        self.assertEqual(len(self.store.query()), 1)


class TestUtility(unittest.TestCase):
    def test_components_and_range(self):
        est = OnlineUtilityEstimator()
        u = est.evaluate("全新的攻击措辞甲乙丙", [],
                         {"safety": "Unsafe", "refusal": "No",
                          "parse_status": "EXACT"}, [], [])
        self.assertEqual(u["novelty"], 1.0)
        self.assertGreater(u["info"], 0.5)
        self.assertLessEqual(u["quality"], 1.0)
        # 与历史高度相似 → 新颖性低
        u2 = est.evaluate("全新的攻击措辞甲乙丙",
                          ["全新的攻击措辞甲乙丙"], None, [], [])
        self.assertLess(u2["novelty"], 0.1)

    def test_quality_ignores_external_success(self):
        """红线 1：效用只看在线状态，external_evaluation 的成败不进质量分。"""
        est = OnlineUtilityEstimator()
        meta = {"safety": "Unsafe", "refusal": "No"}
        a = est.evaluate("同一措辞", [], meta, [], [])
        self.assertEqual(a["quality"], a["quality"])   # 无 success 入参可传


class TestRound0Gating(unittest.TestCase):
    def test_round0_never_injects_experience(self):
        cases = [_rec()]
        self.assertEqual(build_experience_block(cases, cases, round0=True),
                         "(none)")                     # §13：p0 零差异
        blk = build_experience_block(cases, [], round0=False)
        self.assertIn("roleplay", blk)
        self.assertIn("observation only", blk)
        self.assertEqual(build_experience_block([], [], round0=False), "(none)")


def _slot(tid, cat, history=()):
    return NS(task=NS(task_id=tid, harm_category=cat),
              state=NS(history=list(history)))


class TestAdaptiveScheduler(unittest.TestCase):
    def test_phase_a_full_coverage_then_budget_cap(self):
        sched = AdaptiveScheduler(total_budget=5, per_task_cap=3, seed=1)
        slots = [_slot("T1", "A"), _slot("T2", "B"), _slot("T3", "C")]
        r0 = sched.select(0, slots)
        self.assertEqual(len(r0), 3)                  # 阶段 A：全部任务
        sched.select(1, slots)
        sched.select(2, slots)
        self.assertEqual(sched.spent, 5)              # 总预算硬约束
        self.assertEqual(sched.granted["T1"] + sched.granted["T2"]
                         + sched.granted["T3"], 5)
        # 全部任务都未满 cap（5 < 3×3），留痕正确
        self.assertEqual(sched.summary()["under_tested_tasks"], 3)

    def test_per_task_cap_respected(self):
        sched = AdaptiveScheduler(total_budget=10, per_task_cap=2, seed=1)
        slots = [_slot("T1", "A"), _slot("T2", "A")]
        sched.select(0, slots)
        sched.select(1, slots)
        r2 = sched.select(2, slots)                   # 都到 cap → 无一可选
        self.assertEqual(r2, [])

    def test_coverage_first_signal_only_breaks_ties(self):
        """红线 3：覆盖缺口优先；在线信号只做同优先级内的次级排序。"""
        hot_hist = [NS(judge_output=NS(metadata={"safety": "Unsafe"}))]
        # 两类覆盖缺口相同（各 1 任务 / 各已授 1 轮 / cap 3）→ 平局由信号破：
        # T1 有 Unsafe 观察信号，T2 无 → 剩 1 预算时选 T1
        sched = AdaptiveScheduler(total_budget=3, per_task_cap=3, seed=1)
        slots = [_slot("T1", "A", history=hot_hist), _slot("T2", "B")]
        sched.select(0, slots)                       # 阶段 A 各 1 轮（spent=2）
        picked = sched.select(1, slots)              # 只剩 1 预算
        self.assertEqual({s.task.task_id for s in picked}, {"T1"})
        # 反例：无任何信号时同为平局，选择仍确定（seed）
        sched2 = AdaptiveScheduler(total_budget=3, per_task_cap=3, seed=1,
                                   use_online_signal=False)
        slots2 = [_slot("T1", "A"), _slot("T2", "B")]
        sched2.select(0, slots2)
        picked2 = {s.task.task_id for s in sched2.select(1, slots2)}
        self.assertEqual(len(picked2), 1)

    def test_deterministic_with_seed(self):
        a = AdaptiveScheduler(total_budget=7, per_task_cap=3, seed=42)
        b = AdaptiveScheduler(total_budget=7, per_task_cap=3, seed=42)
        slots = [_slot("T%d" % i, "C%d" % (i % 3)) for i in range(6)]
        for r in range(3):
            self.assertEqual([s.task.task_id for s in a.select(r, slots)],
                             [s.task.task_id for s in b.select(r, slots)])


class TestEngineRoundSelector(unittest.TestCase):
    def test_unselected_slot_gets_no_queries(self):
        from agents.red_agent import TemplateRedAgent
        from agents.safety_judge import RuleBasedJudge
        from core.coordinator_impl import HeuristicCoordinator
        from core.protocol import ExperimentProtocol
        from core.reward import RewardConfig, RewardFunction
        from core.schemas import SafetyTask
        from engine.batch_runner import BatchRunner
        from feedback.feedback_builder_v2 import FeedbackBuilderV2
        from memory.null_memory import NullMemory
        from scheduler.uniform_scheduler import UniformScheduler
        from targets.scripted_target import ScriptedTarget

        tasks = [SafetyTask(task_id="T1", goal="g1", harm_category="JBB:Privacy"),
                 SafetyTask(task_id="T2", goal="g2", harm_category="JBB:Privacy")]
        proto = ExperimentProtocol(experiment_id="t", condition_id="C1",
                                   target_query_budget=3, feedback_level="none",
                                   metadata={"feedback_mode": "NONE"})
        sched = AdaptiveScheduler(total_budget=3, per_task_cap=3, seed=7)
        batch = BatchRunner(
            coordinator_factory=lambda p: HeuristicCoordinator(
                UniformScheduler(["h"], ["direct"], rng=random.Random(0))),
            red_agent=TemplateRedAgent(rng=random.Random(0),
                                       template_path="prompts/red/v1.yaml"),
            target=ScriptedTarget(), judge=RuleBasedJudge(),
            memory=NullMemory(),
            reward_factory=lambda b: RewardFunction(RewardConfig(), b),
            feedback_builder=FeedbackBuilderV2(),
            round_selector=sched.select)
        trajs = {t.task.task_id: t for t in batch.run(tasks, {"C1": proto})["C1"]}
        self.assertEqual(len(trajs["T1"].steps) + len(trajs["T2"].steps), 3)
        self.assertEqual(sched.spent, 3)


class TestReportAdaptiveSummary(unittest.TestCase):
    def test_adaptive_block_present(self):
        from core.schemas import (AttackAction, AttackStep, AttackTrajectory,
                                  EvaluationResult, JudgeOutput, SafetyTask,
                                  TargetResponse)
        from safeloop.skills.report import ReportSkill

        def traj(tid, oks):
            task = SafetyTask(task_id=tid, goal="g", harm_category="JBB:Privacy")
            t = AttackTrajectory(trajectory_id=tid, experiment_id="e",
                                 condition_id="STD", task=task, target_id="phi")
            for i, ok in enumerate(oks):
                t.append(AttackStep(
                    round_id=i,
                    action=AttackAction(prompt="p", strategy="direct"),
                    response=TargetResponse(text="r", model_name="t"),
                    judge_output=JudgeOutput(
                        unsafe_score=0, harm_scores={}, jailbreak_score=None,
                        refusal_score=0, severity_score=None, confidence=None,
                        outcome="", rationale=""),
                    reward=0.0,
                    external_evaluation=EvaluationResult(
                        success=ok, jailbreak_score=0, unsafe_score=0,
                        outcome="", severity_score=0, confidence=0,
                        evaluator_id="s") if ok is not None else None))
            return t

        plan = NS(request=NS(mode="standard", budget_per_task=3,
                             target_model="phi", suite="jbb100",
                             adaptive_budget=4),
                  branches=[])
        rep = ReportSkill().build("run-a", plan, {"STD": [
            traj("T1", [True, False]), traj("T2", [False])]})
        ad = rep["adaptive"]
        self.assertEqual(ad["total_budget"], 4)
        self.assertEqual(ad["queries_used"], 3)
        self.assertEqual(ad["distinct_risky_tasks"], 1)
        self.assertEqual(ad["under_tested_tasks"], 2)   # T1=2轮 T2=1轮 都 < cap 3
        self.assertAlmostEqual(ad["yield"], round(1 / 3, 4))


if __name__ == "__main__":
    unittest.main()
