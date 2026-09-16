# -*- coding: utf-8 -*-
"""Scheduler 统一接口（设计文档 §12）。

Coordinator 依赖 Scheduler 决定 (risk_category, attack_strategy)。
V0.1 使用 UniformScheduler；Stage 3 替换为 RiskScheduler
（S_k = alpha*(1-C_k) + beta*U_k + gamma*(1-ASR_k) 的风险边界自适应调度）。
"""
from abc import ABC, abstractmethod
from typing import Optional, Tuple


class BaseScheduler(ABC):
    """调度器抽象基类。"""

    name: str = "base_scheduler"

    @abstractmethod
    def sample_category(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def sample_strategy(self, exclude: Optional[str] = None) -> str:
        """采样攻击策略；exclude 用于剔除上一轮已失败且反馈建议更换的策略。"""
        raise NotImplementedError
