# -*- coding: utf-8 -*-
"""NullMemory：V0.1 中 Memory=False 的占位实现（设计文档 §29）。

接口与真实 Memory 完全一致，Stage 2 可无缝替换为
Episode/Semantic/Statistical 三层记忆。
"""
from typing import List, Tuple

from core.schemas import AttackStep, AttackState, MemoryItem
from memory.base_memory import BaseMemory


class NullMemory(BaseMemory):
    name = "null"

    def retrieve(self, state: AttackState) -> Tuple[List[MemoryItem], List[MemoryItem]]:
        return [], []

    def update(self, step: AttackStep) -> None:
        return None
