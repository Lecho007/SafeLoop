# -*- coding: utf-8 -*-
"""跨类别轮转抽样单测：小子集不再扎堆单一危害类别（旧逻辑取文件头部）。"""
import os
import sys
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safeloop.agents.main_agent import _stratified_sample


def _t(cat, name):
    return NS(harm_category=cat, name=name)


class TestStratifiedSample(unittest.TestCase):
    def setUp(self):
        self.pool = [_t("A", "a0"), _t("A", "a1"), _t("A", "a2"),
                     _t("B", "b0"), _t("C", "c0"), _t("C", "c1")]

    def test_round_robin_covers_all_categories(self):
        out = _stratified_sample(self.pool, 3)
        self.assertEqual([t.name for t in out], ["a0", "b0", "c0"])

    def test_wraps_to_next_round_when_categories_exhausted(self):
        out = _stratified_sample(self.pool, 4)
        self.assertEqual([t.name for t in out], ["a0", "b0", "c0", "a1"])

    def test_n_ge_len_returns_all_in_file_order(self):
        out = _stratified_sample(self.pool, 6)
        self.assertEqual([t.name for t in out],
                         ["a0", "a1", "a2", "b0", "c0", "c1"])

    def test_deterministic(self):
        self.assertEqual(_stratified_sample(self.pool, 4),
                         _stratified_sample(self.pool, 4))

    def test_within_category_order_preserved(self):
        out = _stratified_sample(self.pool, 5)
        a_names = [t.name for t in out if t.harm_category == "A"]
        self.assertEqual(a_names, ["a0", "a1"])

    def test_single_category_pool(self):
        pool = [_t("A", "a0"), _t("A", "a1")]
        self.assertEqual([t.name for t in _stratified_sample(pool, 1)], ["a0"])


if __name__ == "__main__":
    unittest.main()
