# -*- coding: utf-8 -*-
"""Safety Judge 统一接口 V0.2（设计文档 §7 / §20）。

Judge 参与 online loop，输出 JudgeOutput（含四级 outcome）。
攻击成功与否最终由闭环外的 Independent Evaluator 决定，不由 Judge 决定。
"""
from abc import ABC, abstractmethod

from core.schemas import AttackAction, JudgeOutput, SafetyTask, TargetResponse


class BaseJudge(ABC):
    name: str = "base_judge"
    version: str = "v0"

    @abstractmethod
    def evaluate(
        self,
        task: SafetyTask,
        action: AttackAction,
        response: TargetResponse,
    ) -> JudgeOutput:
        raise NotImplementedError
