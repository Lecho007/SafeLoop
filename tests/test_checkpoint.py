# -*- coding: utf-8 -*-
"""断点续跑测试：roundtrip / 崩溃模拟恢复 / 幂等重跑。"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.batch_runner import BatchRunner
from engine.checkpoint import load_checkpoint, save_checkpoint
from core.schemas import SafetyTask
from engine.factory import RunnerBundle
from experiments.conditions import STAGE1A_CONDITIONS
from utils.io import load_yaml

CFG_PATH = "configs/stage1.yaml"


def _tasks():
    return [SafetyTask(task_id="T0001", goal="占位目标一", harm_category="H01",
                       metadata={"target_id": "scripted-demo-1"}),
            SafetyTask(task_id="T0002", goal="占位目标二", harm_category="H02",
                       metadata={"target_id": "scripted-demo-1"})]


def _run(ckpt, resume=False):
    cfg = load_yaml(CFG_PATH)
    bundle = RunnerBundle(cfg, CFG_PATH)
    protocols = {c: bundle.make_protocol(c, ccfg, "ckpt-test")
                 for c, ccfg in STAGE1A_CONDITIONS.items()}
    batch = BatchRunner(
        coordinator_factory=lambda proto: bundle.make_coordinator(proto),
        red_agent=bundle.red_agent, target=bundle.target, judge=bundle.judge,
        memory=bundle.memory, reward_factory=lambda b: bundle.make_reward_fn(b),
        feedback_builder=bundle.feedback_builder,
        provenance=bundle.provenance)
    return batch.run(_tasks(), protocols, checkpoint_path=ckpt, resume=resume)


def _prompts(trajs_by_cond):
    return {c: {t.task.task_id: [s.action.prompt for s in t.steps]
                for t in ts} for c, ts in trajs_by_cond.items()}


class TestCheckpointResume(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ckpt = os.path.join(self.tmp, "ckpt.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_full_run_writes_checkpoint(self):
        result = _run(self.ckpt)
        payloads = load_checkpoint(self.ckpt)
        self.assertIsNotNone(payloads)
        self.assertEqual(len(payloads), 4)  # 2 tasks × 2 conds
        for p in payloads:
            self.assertEqual(len(p["steps"]), 3)
            self.assertTrue(p["done"])

    def test_idempotent_resume(self):
        full = _run(self.ckpt)
        resumed = _run(self.ckpt, resume=True)  # 全部 done → 不再产生新轮次
        self.assertEqual(_prompts(full), _prompts(resumed))
        for c, ts in resumed.items():
            for t in ts:
                self.assertEqual(t.target_queries, 3)

    def test_crash_resume_reproduces_trajectory(self):
        full = _run(self.ckpt)
        # 崩溃模拟：截断检查点——每个 slot 只保留 round 0/1 的步（丢弃 round 2）
        payloads = load_checkpoint(self.ckpt)
        for p in payloads:
            p["steps"] = [s for s in p["steps"] if s["round_id"] < 2]
            p["done"] = False
            p["state"]["round_id"] = 2
            p["state"]["target_queries_used"] = 2
            last = p["steps"][-1]
            p["state"]["last_feedback"] = last.get("feedback")
            p["state"]["current_strategy"] = last["action"]["strategy"]
        save_checkpoint(self.ckpt, payloads)
        resumed = _run(self.ckpt, resume=True)
        # 恢复后完整轨迹与一次跑完的结果逐字一致（scripted 确定性后端）
        self.assertEqual(_prompts(full), _prompts(resumed))
        for c, ts in resumed.items():
            for t in ts:
                self.assertEqual(t.target_queries, 3)
                self.assertEqual(t.stop_reason, "budget_exhausted")

    def test_corrupt_checkpoint_cold_starts(self):
        with open(self.ckpt, "w", encoding="utf-8") as f:
            f.write("{not json")
        result = _run(self.ckpt, resume=True)  # 应冷启动而非崩溃
        self.assertEqual(sum(len(v) for v in result.values()), 4)


if __name__ == "__main__":
    unittest.main()
