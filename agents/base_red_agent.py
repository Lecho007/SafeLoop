# -*- coding: utf-8 -*-
"""Red Agent 统一接口 V0.2（设计文档 §8 / §20）。

generate 额外接收 feedback_level：红方按反馈级别决定如何利用 Judge 信息
（none/score/outcome/structured），实现 Feedback Ablation。
"""
from abc import ABC, abstractmethod

from core.schemas import AttackAction, AttackState


class BaseRedAgent(ABC):
    name: str = "base_red_agent"
    template_version: str = "unknown"

    @abstractmethod
    def generate(self, state: AttackState, feedback_level: str = "none") -> AttackAction:
        """p_t = G_theta(s_t)。根据状态（含历史响应与对应级别的反馈）生成攻击 prompt。"""
        raise NotImplementedError
