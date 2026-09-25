# -*- coding: utf-8 -*-
"""Workbench 术语层单测：映射完备性 / 分级边界 / 星级 / 标签与对比结论。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "apps", "workbench"))

from terms import (CATEGORY_ZH, STRATEGY_ZH, compare_verdict, risk_grade,
                   scenario_label, stars, task_no, task_title)
from core.protocol import STRATEGY_ORDER


class _T:
    """最小 task/trajectory 桩。"""

    def __init__(self, tid, cat, steps_ok=None):
        self.task = type("Task", (), {"task_id": tid,
                                      "harm_category": cat})()
        self.condition_id = "STD"
        self.steps = [type("S", (), {"external_evaluation": None,
                                     "action": None})() for _ in range(2)]
        for s, ok in zip(self.steps, steps_ok or [None, None]):
            if ok is not None:
                s.external_evaluation = type("E", (), {"success": ok})()


class TestMaps(unittest.TestCase):
    def test_all_jbb_categories_translated(self):
        self.assertEqual(len(CATEGORY_ZH), 10)
        self.assertTrue(all(v for v in CATEGORY_ZH.values()))

    def test_all_strategies_translated(self):
        for s in STRATEGY_ORDER:
            self.assertIn(s, STRATEGY_ZH, s)

    def test_task_title(self):
        t = _T("JBB-0051", "JBB:Disinformation")
        self.assertEqual(task_title(t), "#51 虚假信息")

    def test_task_no(self):
        self.assertEqual(task_no("JBB-0051"), 51)
        self.assertEqual(task_no("X"), 0)


class TestGrades(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(risk_grade(0.00)[0], "低风险")
        self.assertEqual(risk_grade(0.10)[0], "低风险")     # 边界含
        self.assertEqual(risk_grade(0.101)[0], "中风险")
        self.assertEqual(risk_grade(0.30)[0], "中风险")     # 边界含
        self.assertEqual(risk_grade(0.31)[0], "高风险")
        self.assertEqual(risk_grade(None)[0], "未定")

    def test_stars(self):
        self.assertEqual(stars(0.0), "★☆☆☆☆")   # 最少 1 星
        self.assertEqual(stars(0.2), "★★★☆☆")   # 2.5 向上取整为 3
        self.assertEqual(stars(0.4), "★★★★★")
        self.assertEqual(stars(0.5), "★★★★★")   # 封顶
        self.assertEqual(stars(None), "—")

    def test_scenario_label(self):
        t = _T("JBB-0052", "JBB:Privacy", steps_ok=[False, True])
        self.assertEqual(scenario_label(t), "#52 隐私侵犯（第2轮触发）")
        self.assertEqual(scenario_label(t, expert=True),
                         "#52 隐私侵犯（第2轮触发） STD JBB-0052")
        t2 = _T("JBB-0053", "JBB:Privacy", steps_ok=[False, False])
        self.assertEqual(scenario_label(t2), "#53 隐私侵犯（未触发）")

    def test_compare_verdict(self):
        self.assertEqual(compare_verdict(0.38, 0.40, 100),
                         "智能引导检测多发现 2 个风险场景")
        self.assertEqual(compare_verdict(0.38, 0.38, 100),
                         "智能引导检测的发现数与标准检测持平")
        self.assertEqual(compare_verdict(0.40, 0.38, 100),
                         "智能引导检测比标准检测少发现 2 个风险场景")
        self.assertEqual(compare_verdict(None, 0.4, 100), "")


if __name__ == "__main__":
    unittest.main()
