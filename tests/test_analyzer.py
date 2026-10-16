# -*- coding: utf-8 -*-
"""AI 报告分析技能单测（零 GPU）：

- summarize_for_prompt：最小摘要字段/截断/多轮暴露案例；
- build_messages：prompt 模板渲染（不加载模型）；
- 缓存读写与 extract_turning_cases 的轨迹形态兼容（对象/字典两形态）。
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safeloop.skills.analyzer import (AnalyzerSkill, extract_turning_cases,
                                      summarize_for_prompt)


class _T:  # 最小轨迹对象形态(task 字段嵌套,与 AttackTrajectory 一致)
    def __init__(self, tid, cat, oks):
        self.task = type("Task", (), {"task_id": tid, "harm_category": cat})()
        self.steps = [type("S", (), {"external_evaluation":
                                     type("E", (), {"success": ok})()})()
                      for ok in oks]


def _tdict(tid, cat, oks):
    return {"task_id": tid, "category": cat,
            "steps": [{"external_evaluation": {"success": ok}} for ok in oks]}


class AnalyzerPureTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._cwd = os.getcwd()
        os.chdir(self._tmp)

    def tearDown(self):
        os.chdir(self._cwd)
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_summarize_minimal_fields(self):
        report = {"overview": {"risk_tasks": 38, "total_tasks": 100,
                               "mode": "compare", "target": "phi"},
                  "metrics": {"user_layer": {"asr_at_budget": 0.38,
                                             "auc_b": 0.31, "mean_ctts": 4.4}},
                  "risk_distribution": {"Malware/Hacking": 9},
                  "representative_cases": [{"task_id": "JBB-1", "category": "x",
                                            "why_representative": "多轮暴露"}]}
        d = summarize_for_prompt(report, [{"task_id": "JBB-9", "category": "隐私",
                                          "first_round": 3}])
        self.assertEqual(d["risk_tasks"], 38)
        self.assertEqual(d["risk_rate"], 0.38)
        self.assertIn("multi_round_revealed_cases", d)
        self.assertEqual(d["multi_round_revealed_cases"][0]["first_round"], 3)
        # 不泄露的字段：代表案例不带 prompt 全文
        self.assertNotIn("prompt", json.dumps(d))

    def test_build_messages_renders_template(self):
        # 模板文件在仓库内,chdir 到 tmp 后用绝对路径回仓库
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sk = AnalyzerSkill(prompt_path=os.path.join(repo, DEFAULT := "prompts/analyzer/analysis_v1.yaml"))
        msgs = sk.build_first_messages({"overview": {"risk_tasks": 1, "total_tasks": 2}})
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("只负责解释", msgs[0]["content"])
        self.assertIn('"risk_tasks": 1', msgs[1]["content"])
        self.assertNotIn("{report_json}", msgs[1]["content"])

    def test_clip_history_bounds(self):
        msgs = [{"role": "system", "content": "sys"}]
        msgs += [{"role": "user", "content": "u" * 800},
                 {"role": "assistant", "content": "a" * 800}] * 10
        clipped = AnalyzerSkill._clip_history(msgs)
        self.assertEqual(clipped[0]["role"], "system")
        self.assertLess(len(clipped), len(msgs))

    def test_turning_cases_both_shapes(self):
        trajs = [_T("A", "恶意", [False, False, True]),
                 _tdict("B", "隐私", [True, True]),          # 首轮即触发,不算
                 _T("C", "欺诈", [False, False, False])]      # 全未触发,不算
        out = extract_turning_cases(trajs)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["task_id"], "A")
        self.assertEqual(out[0]["first_round"], 3)

    def test_cache_roundtrip(self):
        sk = AnalyzerSkill()
        self.assertIsNone(AnalyzerSkill.load_cache("run_x"))
        sk._save_cache("run_x", {"text": "hi", "version": sk.version})
        cached = AnalyzerSkill.load_cache("run_x")
        self.assertEqual(cached["text"], "hi")
        self.assertTrue(os.path.exists(AnalyzerSkill.cache_path("run_x")))


if __name__ == "__main__":
    unittest.main()
