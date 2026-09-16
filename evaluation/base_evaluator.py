# -*- coding: utf-8 -*-
"""Independent Evaluator 统一接口（设计文档 §10/§38）。

硬约束：Evaluator 绝不进入在线闭环——不出现在 state / feedback / reward /
coordinator / memory 中；只在实验结束后离线批处理。
JudgeOutput != EvaluationResult，两者是不同的数据结构。
"""
from abc import ABC, abstractmethod

from core.schemas import (
    AttackAction,
    EvaluationResult,
    SafetyTask,
    TargetResponse,
)


class BaseEvaluator(ABC):
    name: str = "base_evaluator"

    @abstractmethod
    def evaluate(
        self,
        task: SafetyTask,
        action: AttackAction,
        response: TargetResponse,
    ) -> EvaluationResult:
        raise NotImplementedError
