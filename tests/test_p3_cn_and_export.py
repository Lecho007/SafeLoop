# -*- coding: utf-8 -*-
"""P3 单测：suite 通路（planner 映射）+ SafeLoop-CN 数据集结构 + HTML 导出。"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestSuiteWiring(unittest.TestCase):
    def test_planner_maps_known_suites(self):
        from safeloop.agents.main_agent import EvaluationPlanner, EvaluationRequest
        p = EvaluationPlanner("configs/hardware/rtx4060_8g_1br.yaml")
        plan = p.plan(EvaluationRequest(question="q", suite="jbb100"))
        self.assertEqual(plan.tasks_file, "data/tasks/jbb100_full.jsonl")
        plan_cn = p.plan(EvaluationRequest(question="q", suite="safeloop_cn"))
        self.assertEqual(plan_cn.tasks_file,
                         "data/tasks/safeloop_cn_v0.1.jsonl")
        plan_path = p.plan(EvaluationRequest(
            question="q", suite="data/tasks/jbb20.jsonl"))
        self.assertEqual(plan_path.tasks_file, "data/tasks/jbb20.jsonl")


class TestSafeloopCN(unittest.TestCase):
    PATH = "data/tasks/safeloop_cn_v0.1.jsonl"

    def test_dataset_schema_and_coverage(self):
        if not os.path.exists(self.PATH):
            self.skipTest("数据集未生成（先跑 scripts/build_safeloop_cn.py）")
        rows = [json.loads(l) for l in open(self.PATH, encoding="utf-8") if l.strip()]
        self.assertEqual(len(rows), 40)
        cats = set()
        for r in rows:
            self.assertTrue(r["task_id"].startswith("CN-"))
            self.assertTrue(r["goal"].strip())
            self.assertEqual(r["language"], "zh")
            self.assertEqual(r["source"], "jailbench_seed")
            self.assertEqual(r["metadata"]["feedback_observability"],
                             "content_observable")
            self.assertEqual(r["metadata"]["review_status"], "pending_review")
            cats.add(r["harm_category"])
        self.assertGreaterEqual(len(cats), 4)   # 跨类别覆盖

    def test_loadable_by_safety_task(self):
        from core.schemas import SafetyTask
        if not os.path.exists(self.PATH):
            self.skipTest("数据集未生成")
        rows = [json.loads(l) for l in open(self.PATH, encoding="utf-8") if l.strip()]
        t = SafetyTask.from_dict(rows[0])
        self.assertEqual(t.language, "zh")
        self.assertTrue(t.metadata["secondary_domain"])


class TestExportHtml(unittest.TestCase):
    def test_export_renders_report_sections(self):
        from safeloop.skills.export_html import build_export_html
        report = {
            "overview": {"answer": "在本次范围内发现风险。",
                         "risk_tasks": 1, "total_tasks": 3, "mode": "standard",
                         "target": "phi"},
            "metrics": {"user_layer": {"asr_at_budget": 1 / 3, "auc_b": 0.4,
                                       "mean_ctts": 2.0}},
            "configuration": {"budget_per_task": 3},
            "risk_distribution": {"JBB:Privacy": 1},
            "representative_cases": [{"task_id": "JBB-0050",
                                      "category": "Disinformation",
                                      "why_representative": "代表性风险轨迹"}],
            "limitations": ["局限一"],
        }
        out = build_export_html("run-t", report, transcript_md="# 对话\n内容")
        for expect in ("大模型安全检测报告", "run-t", "风险发现比例 1/3",
                       "Privacy", "代表性风险轨迹", "完整对话记录", "参考等级"):
            self.assertIn(expect, out)


if __name__ == "__main__":
    unittest.main()
