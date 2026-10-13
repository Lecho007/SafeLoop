# -*- coding: utf-8 -*-
"""API server 端点单测（零 GPU）：

- v1.1 高级选项透传：EvalRequest.use_memory/adaptive_budget → RunSpec
  （此前 EvalRequest 未声明这两个字段，pydantic 静默丢弃，Web 高级选项完全无效）；
- GET /evaluations/{id}/export：报告 HTML 生成/落盘/登记，无报告 404；
- GET /evaluations/{id}/transcript：artifacts 优先、默认路径回退（legacy 文件），缺失 404；
- POST /evaluations/{id}/reviewed：人工复核标记（roadmap P3），未知 run 404；
- GET /evaluations/{id}/live?tail=N：tail 参数生效。

无 httpx，不走 TestClient，直接调用路由函数（均无 Request 依赖）。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import HTTPException  # noqa: E402


class ApiServerEndpointsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._cwd = os.getcwd()
        os.chdir(self._tmp)
        os.makedirs(os.path.join(self._tmp, "outputs", "reports"), exist_ok=True)
        from apps.api import server
        from safeloop.runs.manager import RunManager
        # 干净 manager：tmp 库、不起 worker、不导历史（模块级单例留给 import 期，不干扰）
        server.mgr = RunManager(
            db_path=os.path.join(self._tmp, "outputs", "runs", "t.db"),
            start_worker=False, import_history=False,
            outputs_dir=os.path.join(self._tmp, "outputs"))
        self.server = server

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    # ---------------------------------------------------------------- passthrough
    def test_v11_fields_passthrough(self):
        from apps.api.server import EvalRequest, _to_spec
        spec = _to_spec(EvalRequest(use_memory=True, adaptive_budget=300, rounds=5))
        self.assertTrue(spec.use_memory)
        self.assertEqual(spec.adaptive_budget, 300)
        base = _to_spec(EvalRequest())
        self.assertFalse(base.use_memory)
        self.assertIsNone(base.adaptive_budget)
        # 旧兼容字段不受影响
        old = _to_spec(EvalRequest(budget_per_task=7, max_tasks=9))
        self.assertEqual(old.rounds, 7)
        self.assertEqual(old.sample_size, 9)

    # ---------------------------------------------------------------- export
    def _write_report(self, run_id):
        rep = {"overview": {"risk_tasks": 1, "total_tasks": 3, "mode": "standard",
                            "target": "phi"},
               "metrics": {"user_layer": {"asr_at_budget": 0.34}},
               "configuration": {"budget_per_task": 3}}
        p = os.path.join(self._tmp, "outputs", "reports",
                         "{}_report.json".format(run_id))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False)
        return p

    def test_export_generates_printable_html(self):
        s = self.server
        run_id = "run_t_export"
        with self.assertRaises(HTTPException) as cm:
            s.export_report_html(run_id)
        self.assertEqual(cm.exception.status_code, 404)

        self._write_report(run_id)
        tp = os.path.join(self._tmp, "outputs", "reports",
                          "{}_transcript.md".format(run_id))
        with open(tp, "w", encoding="utf-8") as f:
            f.write("# 对话存档\nR1 TESTER …\n")
        resp = s.export_report_html(run_id)
        out = os.path.join(self._tmp, "outputs", "reports",
                           "{}_export.html".format(run_id))
        self.assertTrue(os.path.exists(out))
        with open(out, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("大模型安全检测报告", body)
        self.assertIn("对话存档", body)          # transcript 全文已嵌入
        self.assertEqual(resp.media_type, "text/html")
        # 幂等：再导一次不报错
        s.export_report_html(run_id)

    # ---------------------------------------------------------------- transcript
    def test_transcript_fallback_and_404(self):
        s = self.server
        run_id = "run_t_transcript"              # 不在 runs 表（legacy 场景）
        with self.assertRaises(HTTPException) as cm:
            s.download_transcript(run_id)
        self.assertEqual(cm.exception.status_code, 404)
        tp = os.path.join(self._tmp, "outputs", "reports",
                          "{}_transcript.md".format(run_id))
        with open(tp, "w", encoding="utf-8") as f:
            f.write("# 存档\n")
        resp = s.download_transcript(run_id)     # 默认路径回退命中
        self.assertEqual(resp.media_type, "text/markdown")

    # ---------------------------------------------------------------- reviewed
    def test_reviewed_marking(self):
        s = self.server
        from safeloop.runs.manager import RunSpec
        run_id = s.mgr.submit(RunSpec(question="t"))
        with self.assertRaises(HTTPException) as cm:
            s.set_reviewed("run_不存在", s.ReviewedRequest())
        self.assertEqual(cm.exception.status_code, 404)
        r = s.set_reviewed(run_id, s.ReviewedRequest(reviewed=True))
        self.assertTrue(r["reviewed"])
        arts = [a["kind"] for a in s.mgr.get_run(run_id)["artifacts"]]
        self.assertIn("reviewed", arts)
        s.set_reviewed(run_id, s.ReviewedRequest(reviewed=False))
        arts = [a["kind"] for a in s.mgr.get_run(run_id)["artifacts"]]
        self.assertIn("unreviewed", arts)
        self.assertNotIn("reviewed", arts)

    # ---------------------------------------------------------------- live tail
    def test_live_tail_param(self):
        s = self.server
        from safeloop.runs.manager import RunSpec
        run_id = s.mgr.submit(RunSpec(question="t"))
        d = s.get_live(run_id, tail=200)
        self.assertEqual(d["status"], "QUEUED")
        self.assertEqual(d["events"], [])
        with self.assertRaises(HTTPException):
            s.get_live("run_不存在")


if __name__ == "__main__":
    unittest.main()
