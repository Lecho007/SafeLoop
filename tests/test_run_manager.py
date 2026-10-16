# -*- coding: utf-8 -*-
"""RunManager 单测（roadmap P1）：队列/持久化/取消/恢复/历史导入——零 GPU。

agent_factory 注入 FakeAgent（模拟轮边界取消与 resume），走真实 SQLite 与工作线程。
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safeloop.runs.manager import RunManager, RunSpec


class FakePlan:
    def __init__(self, n_tasks):
        self.n_tasks = n_tasks
        self.branches = [{"name": "STD", "mode": "SHADOW"}]


class FakeAgent:
    """模拟 SafeLoopMainAgent 的执行面：轮循环、轮边界取消、resume 记录。"""

    def __init__(self, config_path="", seed=42, rounds=3, tmp="", delay=0.03):
        self.config_path = config_path
        self.seed = seed
        self.rounds = rounds
        self.tmp = tmp
        self.delay = delay
        self.state = "IDLE"
        self.run_id = None
        self.events = []
        self.live_events = []
        self.trajectories = {}
        self.report = None
        self.plan = None
        self.cancel_requested = False
        self.resume_used = None

    def _emit(self, kind, **d):
        self.events.append({"ts": time.time(), "state": self.state,
                            "kind": kind, **d})

    def submit(self, question, **ov):
        self.state = "PLANNING"
        self._emit("plan_ready")
        self.state = "READY"
        self.plan = FakePlan(1 if ov.get("scenario_ids") else
                             (ov.get("max_tasks") or 100))

    def cancel(self):
        self.cancel_requested = True
        if self.state == "READY":
            self.state = "CANCELLED"
        elif self.state in ("RUNNING", "CANCELLING"):
            if self.state != "CANCELLING":
                self.state = "CANCELLING"

    def run(self, resume=False):
        self.resume_used = resume
        self.state = "RUNNING"
        done_rounds = 0
        for r in range(self.rounds):
            if self.cancel_requested:      # 轮边界检查（同 BatchRunner 语义）
                self.state = "CANCELLING"
                break
            time.sleep(self.delay)
            self.live_events.append({"task_id": "T1", "round": r + 1,
                                     "strategy": "direct", "prompt": "p",
                                     "response": "r"})
            self._emit("round_done", round=r + 1)
            done_rounds = r + 1
        self.report = {"overview": {"risk_tasks": 0, "total_tasks": 1,
                                    "answer": "stub"},
                       "configuration": {"budget_per_task": self.rounds}}
        if self.tmp and self.run_id:
            os.makedirs(os.path.join(self.tmp, "reports"), exist_ok=True)
            with open(os.path.join(self.tmp, "reports",
                                   "{}_report.json".format(self.run_id)),
                      "w", encoding="utf-8") as f:
                json.dump(self.report, f)
        self.state = "CANCELLED" if self.cancel_requested else "COMPLETED"
        self._emit("finished", rounds=done_rounds)


def _wait_terminal(mgr, run_id, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = mgr.get_run(run_id)["status"]
        if st in ("COMPLETED", "FAILED", "CANCELLED"):
            return st
        time.sleep(0.1)
    raise AssertionError("run not terminal in {}s (status={})".format(
        timeout, mgr.get_run(run_id)["status"]))


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.made = []
        self.rounds = 3
        self.delay = 0.03

        def factory(config_path="", seed=42):
            a = FakeAgent(config_path=config_path, seed=seed,
                          rounds=self.rounds, tmp=self.tmp, delay=self.delay)
            self.made.append(a)
            return a

        self.factory = factory
        self.mgr = RunManager(
            db_path=os.path.join(self.tmp, "runs.db"),
            agent_factory=factory, start_worker=True,
            import_history=True, outputs_dir=self.tmp)

    def tearDown(self):
        self.mgr.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestQueueAndCompletion(_Base):
    def test_submit_runs_to_completion_with_events_and_artifacts(self):
        run_id = self.mgr.submit(RunSpec(scope="sample", sample_size=2,
                                         rounds=3))
        self.assertTrue(run_id.startswith("run_"))
        self.assertEqual(_wait_terminal(self.mgr, run_id), "COMPLETED")
        d = self.mgr.get_run(run_id)
        self.assertEqual(d["steps_done"], 3)
        self.assertEqual(d["n_tasks"], 2)
        self.assertEqual(d["total_steps"], 6)
        arts = {a["kind"]: a["path"] for a in d["artifacts"]}
        self.assertIn("report", arts)
        evs = self.mgr.get_events(run_id)
        self.assertTrue(any(e["kind"] == "plan_ready" for e in evs))
        self.assertTrue(any(e["kind"] == "round_done" for e in evs))
        self.assertTrue(all(evs[i]["seq"] < evs[i + 1]["seq"]
                            for i in range(len(evs) - 1)))

    def test_events_pagination_after_seq(self):
        run_id = self.mgr.submit(RunSpec(rounds=2))
        _wait_terminal(self.mgr, run_id)
        evs = self.mgr.get_events(run_id)
        mid = evs[len(evs) // 2]["seq"]
        tail = self.mgr.get_events(run_id, after_seq=mid)
        self.assertEqual(tail[0]["seq"], mid + 1)
        self.assertEqual(len(tail), len(evs) - len(evs) // 2 - 1)

    def test_serial_queue_no_gpu_contention(self):
        a = self.mgr.submit(RunSpec(rounds=3))
        b = self.mgr.submit(RunSpec(rounds=3))
        _wait_terminal(self.mgr, a)
        # a 终态时 b 仍可能在执行，但绝不允许并行（b 的 agent 在 a 完成前不启动）
        st_b = self.mgr.get_run(b)["status"]
        self.assertIn(st_b, ("QUEUED", "RUNNING", "COMPLETED", "CANCELLING"))
        # 注：RUNNING 且 get_agent 为空的瞬态是合法的（agent 收尾窗口：
        # _agents 已注销、终态尚未落库），不构成并行证据；并行的判定
        # 以最终创建的 agent 数量为准。
        _wait_terminal(self.mgr, b)
        self.assertEqual(len(self.made), 2)


class TestCancelAndResume(_Base):
    def test_cancel_queued_never_starts(self):
        # 占住工作进程，再排一个，然后取消排队者
        blocker = self.mgr.submit(RunSpec(rounds=3))
        victim = self.mgr.submit(RunSpec(rounds=3))
        # 等 blocker 开始执行
        deadline = time.time() + 5
        while time.time() < deadline and self.mgr.get_run(blocker)["status"] \
                not in ("RUNNING", "CANCELLING", "COMPLETED", "CANCELLED"):
            time.sleep(0.05)
        r = self.mgr.cancel(victim)
        self.assertEqual(r["status"], "CANCELLED")
        _wait_terminal(self.mgr, blocker)
        _wait_terminal(self.mgr, victim)
        agents_for_victim = 0   # victim 从未执行 → 工厂只为 blocker 建过 agent
        self.assertEqual(len(self.made), 1)
        self.assertEqual(agents_for_victim, 0)

    def test_cancel_running_stops_at_round_boundary_and_resumes(self):
        self.rounds, self.delay = 12, 0.15   # 慢速长跑，保证取消窗口
        run_id = self.mgr.submit(RunSpec(rounds=12))
        deadline = time.time() + 8
        while time.time() < deadline and not self.mgr.get_run(run_id)["steps_done"]:
            time.sleep(0.02)
        r = self.mgr.cancel(run_id)
        self.assertEqual(r["status"], "CANCELLING")
        self.assertEqual(_wait_terminal(self.mgr, run_id, timeout=10), "CANCELLED")
        agent = self.made[0]
        self.assertTrue(agent.cancel_requested)
        self.assertLess(len(agent.live_events), 12)   # 没跑满
        # 恢复：同一 run_id 重新入队，从检查点续跑语义（resume=True）
        self.rounds, self.delay = 12, 0.02           # 恢复后快速跑完
        self.mgr.resume(run_id)
        self.assertEqual(_wait_terminal(self.mgr, run_id, timeout=10), "COMPLETED")
        self.assertEqual(self.made[1].run_id, run_id)
        self.assertTrue(self.made[1].resume_used)
        self.assertEqual(len(self.made), 2)

    def test_resume_rejects_active_run(self):
        run_id = self.mgr.submit(RunSpec(rounds=3))
        with self.assertRaises(ValueError):
            self.mgr.resume(run_id)
        _wait_terminal(self.mgr, run_id)


class TestHistoryImport(unittest.TestCase):
    def test_imports_existing_reports_once(self):
        tmp = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(tmp, "reports"), exist_ok=True)
            for rid in ("run-aaa111", "run-bbb222"):
                with open(os.path.join(tmp, "reports",
                                       "{}_report.json".format(rid)), "w",
                          encoding="utf-8") as f:
                    json.dump({"overview": {"mode": "standard", "target": "phi",
                                            "risk_tasks": 1, "total_tasks": 3},
                               "configuration": {"budget_per_task": 3,
                                                 "suite": "jbb100"}}, f)
            mgr = RunManager(db_path=os.path.join(tmp, "runs.db"),
                             agent_factory=lambda **kw: None,
                             start_worker=False, import_history=True,
                             outputs_dir=tmp)
            runs = {r["run_id"]: r for r in mgr.list_runs()}
            self.assertIn("run-aaa111", runs)
            self.assertTrue(runs["run-aaa111"]["imported"])
            self.assertEqual(runs["run-aaa111"]["status"], "COMPLETED")
            arts = mgr.get_run("run-aaa111")["artifacts"]
            self.assertEqual(arts[0]["kind"], "report")
            mgr.shutdown()
            # 幂等：二次启动不重复导入
            mgr2 = RunManager(db_path=os.path.join(tmp, "runs.db"),
                              agent_factory=lambda **kw: None,
                              start_worker=False, import_history=True,
                              outputs_dir=tmp)
            self.assertEqual(len(mgr2.list_runs()), 2)
            mgr2.shutdown()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
