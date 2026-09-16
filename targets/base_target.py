# -*- coding: utf-8 -*-
"""Target LLM 统一接口（设计文档 §9）。

以后 OpenAI / DeepSeek / Qwen / 本地 HF / vLLM 全部只是 Adapter。
"""
from abc import ABC, abstractmethod

from core.schemas import TargetResponse


class BaseTarget(ABC):
    """目标模型抽象基类。"""

    name: str = "base_target"

    @abstractmethod
    def generate(self, prompt: str) -> TargetResponse:
        """y_t = T(p_t)。"""
        raise NotImplementedError
