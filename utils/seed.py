# -*- coding: utf-8 -*-
"""随机种子管理：保证实验可复现（one-shot 与 feedback 严格同起点）。"""
import random


def set_seed(seed: int) -> random.Random:
    """设置全局随机种子并返回共享 RNG 实例。"""
    random.seed(seed)
    return random.Random(seed)
