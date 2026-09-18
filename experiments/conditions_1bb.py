# -*- coding: utf-8 -*-
"""Stage 1B-B 实验条件（V0.3-B 1B-B §8）：goal-compliance 子集上的 Judge 信号消融。

四条件，B=5，Red/Target/seed/初始 prompt 全部一致，唯一变量 = 在线反馈的 Judge 信号源：
  B0   无 Judge 反馈（= C1 语义，并行对照）
  B-C  Content Judge only（Qwen3Guard V2）
  B-G  Goal Compliance Judge only（goal+response 判 progress/polarity）
  B-M  Multi-Signal Judge（任务感知融合）
"""

STAGE1BB_CONDITIONS = {
    "B0": {"target_query_budget": 5, "feedback_level": "none",
           "judge_backend": None, "role": "no judge feedback (parallel control)"},
    "B_C": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "qwen3guard_v2", "role": "content signal only"},
    "B_G": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "goal_compliance", "role": "goal signal only"},
    "B_M": {"target_query_budget": 5, "feedback_level": "structured",
            "judge_backend": "multi_signal", "role": "task-aware multi-signal"},
}

# 白名单：四条件间允许不同的协议字段
ALLOWED_PAIR_DIFFERENCES_1BB = {
    frozenset(("B0", p)): ["feedback_level"] for p in ("B_C", "B_G", "B_M")
}
# 注：B_C/B_G/B_M 之间 feedback_level 相同但 judge_backend 不同——judge backend
# 是被操纵变量本身，在 1B-B 语义下属于"唯一变量"的合法组成部分，由
# stage1bb 执行器按条件覆写 backend 并记录于 provenance。

# 主比较（假设 H6–H9）
MAIN_COMPARISONS_1BB = [
    ("B_C", "B_M"),   # H6/H7/H8：multi 是否扩大观测覆盖/可行动反馈/行为质量
    ("B_G", "B_M"),
    ("B0", "B_M"),
]
