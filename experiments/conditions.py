# -*- coding: utf-8 -*-
"""Stage 1 实验条件（V0.2 §13 + V0.3 §9–§12）。

C0 单轮基线（B=1）；C1 多轮无反馈（主对照，红方可见响应历史自我调整）；
C2 分数反馈（F1）；C3 结构化反馈（F3，主方法）；C_SR 红方自我反思基线（1C 用）。
主比较 C1 vs C3；更上位的说服力比较是 C3 vs C_SR（设计 §12）。
"""

STAGE1_CONDITIONS = {
    "C0": {"target_query_budget": 1, "feedback_level": "none",
           "role": "single-shot reference baseline"},
    "C1": {"target_query_budget": 5, "feedback_level": "none",
           "role": "multi-round no-feedback control"},
    "C2": {"target_query_budget": 5, "feedback_level": "score",
           "role": "multi-round score feedback (F1)"},
    "C3": {"target_query_budget": 5, "feedback_level": "structured",
           "role": "multi-round structured feedback (F3)"},
    "C_SR": {"target_query_budget": 5, "feedback_level": "self_reflection",
             "role": "red self-reflection baseline (Stage 1C only)"},
}

# V0.2 协议层 demo 用（不含 C_SR）
STAGE1_DEMO_CONDITIONS = {k: v for k, v in STAGE1_CONDITIONS.items() if k != "C_SR"}

# Stage 1A（V0.3 §21）：只跑 C1/C3，B=3
STAGE1A_CONDITIONS = {
    "C1": dict(STAGE1_CONDITIONS["C1"], target_query_budget=3),
    "C3": dict(STAGE1_CONDITIONS["C3"], target_query_budget=3),
}

MAIN_COMPARISON = ("C1", "C3")

# 白名单：条件对之间允许不同的协议字段（设计文档 §34）
ALLOWED_PAIR_DIFFERENCES = {
    frozenset(("C1", "C2")): ["feedback_level"],
    frozenset(("C1", "C3")): ["feedback_level"],
    frozenset(("C2", "C3")): ["feedback_level"],
    frozenset(("C1", "C_SR")): ["feedback_level"],
    frozenset(("C3", "C_SR")): ["feedback_level"],
}
