# -*- coding: utf-8 -*-
"""Attack Memory 统一接口（设计文档 §11）。

Memory 分三层：Episode Memory（完整轨迹）/ Semantic Memory（embedding 检索）/
Statistical Memory（目标风险画像）。V0.1 中 Memory=False（NullMemory），
但接口先固定，Stage 2 再接入真实实现。
"""
from abc import ABC, abstractmethod
from typing import List, Tuple

from core.schemas import AttackStep, AttackState, MemoryItem


class BaseMemory(ABC):
    """攻击记忆抽象基类。"""

    name: str = "base_memory"

    @abstractmethod
    def retrieve(self, state: AttackState) -> Tuple[List[MemoryItem], List[MemoryItem]]:
        """返回 (成功案例, 失败案例)，注入 state 供红方参考。"""
        raise NotImplementedError

    @abstractmethod
    def update(self, step: AttackStep) -> None:
        """每轮结束后写入记忆。"""
        raise NotImplementedError
