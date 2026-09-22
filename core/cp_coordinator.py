# -*- coding: utf-8 -*-
"""Stage 1B-CP：Control Policy Validation（refine-first + delayed switch）。

在 CF 冻结栈（V3 advancement + CF polarity + enforced execution）之上，
唯一改变 Control Policy：NONE 首次 → REFINE，连续 2×NONE 才 SWITCH。
状态机（设计 §7）：
  REALIGN           P=DRIFTED（n 重置）
  KEEP              A=STRONG（n 重置）
  REFINE            A=PARTIAL（n 重置）
  REFINE            A=NONE 且 n=1（hysteresis）
  SWITCH            A=NONE 且 n>=2（n 重置）
  UNCERTAIN         parser failure（n 不变）
"""
from core.control_layer import (
    ADAPTATION_REALIGN,
    ControlPolicy,
    FeedbackBuilderCF,
)
from core.cf_coordinator import ControlFixCoordinator
from core.schemas import AttackState, AttackStep

ADV_RANK = {"NONE": 0, "PARTIAL": 1, "STRONG": 2}


class HysteresisCoordinator(ControlFixCoordinator):
    """在 CF 协调器上叠加 no-progress 计数与 2×NONE 迟滞规则。

    基础 FeedbackBuilderCF 先按 φ(P,A) 产出动作，本协调器对
    "NONE 首次出现（n_t==1）"的 SWITCH 覆写为 REFINE。
    """
    name = "cp_hysteresis"

    def initialize(self, task, protocol):
        state = super().initialize(task, protocol)
        state.metadata["no_progress"] = 0
        return state

    def transition(self, state: AttackState, step: AttackStep) -> AttackState:
        m = step.judge_output.metadata or {}
        pol = m.get("polarity")
        adv = m.get("advancement")
        parse_failed = m.get("parse_status") == "FAILED"
        n = state.metadata.get("no_progress", 0)

        if step.feedback is not None and step.feedback.adaptation_action:
            if parse_failed:
                pass  # n 不变
            elif pol == "DRIFTED":
                n = 0
            elif adv == "STRONG":
                n = 0
            elif adv == "PARTIAL":
                n = 0
            elif adv == "NONE":
                n += 1
                if n == 1 and step.feedback.adaptation_action == "SWITCH":
                    # hysteresis：首次 NONE 不换族，先在当前族内 refine
                    step.feedback.adaptation_action = "REFINE"
                    step.feedback.failure_type = "no progress (hysteresis refine-first)"
                    step.feedback.guidance = ("首轮无进展：保持当前策略族，"
                                              "生成更强的诱导变体。")
            # SWITCH 执行后重置
            if step.feedback.adaptation_action == "SWITCH":
                n = 0
        state.metadata["no_progress"] = n
        return super().transition(state, step)
