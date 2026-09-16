# -*- coding: utf-8 -*-
"""Coordinator 统一接口 V0.2（设计文档 §12 / §20）。

协调器不写 prompt，只管理：初始状态、每轮决策（预算/策略/停止）、状态转移。
Stage 1 停止策略由设计文档 §23 冻结：跑满 target_query_budget，不因在线成功提前停。
"""
from abc import ABC, abstractmethod

from core.protocol import ExperimentProtocol
from core.schemas import (
    AttackState,
    AttackStep,
    SafetyTask,
)


class CoordinatorAction:
    """a_t^C = (h_t, z_t, b_t, stop_t)。"""

    def __init__(self, harm_category: str, attack_strategy: str,
                 budget: int = 1, stop: bool = False) -> None:
        self.harm_category = harm_category
        self.attack_strategy = attack_strategy
        self.budget = budget
        self.stop = stop


class BaseCoordinator(ABC):
    name: str = "base_coordinator"

    @abstractmethod
    def initialize(self, task: SafetyTask, protocol: ExperimentProtocol) -> AttackState:
        """构造 s_0（含查询预算与初始策略种子）。"""
        raise NotImplementedError

    @abstractmethod
    def decide(self, state: AttackState) -> CoordinatorAction:
        raise NotImplementedError

    @abstractmethod
    def transition(self, state: AttackState, step: AttackStep) -> AttackState:
        """状态转移；预算耗尽时设置 stop_reason='budget_exhausted'。"""
        raise NotImplementedError
