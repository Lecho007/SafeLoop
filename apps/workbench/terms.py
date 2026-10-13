# -*- coding: utf-8 -*-
"""Workbench 术语层（纯函数，无 streamlit 依赖 —— 供 GUI 与单测共用）。

本体已上移到 safeloop/skills/terms.py（产品层，roadmap P2 统一协议的一部分）；
本文件保留为兼容 shim，GUI/旧测试的 `from terms import ...` 不变。
"""
from safeloop.skills.terms import *  # noqa: F401,F403
from safeloop.skills.terms import (  # noqa: F401  显式再导出（pyflakes 友好）
    CATEGORY_ZH, STRATEGY_ZH, asr_at_budget, compare_verdict, risk_grade,
    scenario_label, stars, task_no, task_title)
