# -*- coding: utf-8 -*-
"""配对统计检验单测（McNemar / Wilcoxon）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evaluation.stats import mcnemar_test, wilcoxon_signed_rank


class TestStats(unittest.TestCase):
    def test_mcnemar_identical(self):
        r = mcnemar_test([True, False, True], [True, False, True])
        self.assertEqual((r["b"], r["c"]), (0, 0))
        self.assertEqual(r["p_value"], 1.0)

    def test_mcnemar_strong_difference(self):
        # B 在 8 个 discordant pair 中全胜 → 显著（连续性校正的正态近似）
        a = [False] * 8 + [True] * 2
        b = [True] * 8 + [True] * 2
        r = mcnemar_test(a, b)
        self.assertEqual((r["b"], r["c"]), (8, 0))
        self.assertLess(r["p_value"], 0.05)

    def test_mcnemar_balanced(self):
        r = mcnemar_test([True, False], [False, True])
        self.assertEqual((r["b"], r["c"]), (1, 1))
        self.assertGreater(r["p_value"], 0.3)

    def test_wilcoxon_shift(self):
        # y 系统性大于 x → 显著
        x = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]
        y = [v + 3.0 for v in x]
        r = wilcoxon_signed_rank(x, y)
        self.assertLess(r["p_value"], 0.05)

    def test_wilcoxon_no_effect(self):
        x = [1.0, 2.0, 3.0, 4.0]
        y = [2.0, 1.0, 4.0, 3.0]
        r = wilcoxon_signed_rank(x, y)
        self.assertGreater(r["p_value"], 0.5)

    def test_wilcoxon_all_zero_diffs(self):
        r = wilcoxon_signed_rank([1, 2], [1, 2])
        self.assertEqual(r["n"], 0)
        self.assertEqual(r["p_value"], 1.0)


if __name__ == "__main__":
    unittest.main()
