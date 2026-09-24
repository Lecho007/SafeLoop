# -*- coding: utf-8 -*-
"""RNG 独立流（Stage 1B-R 协议级基础设施）。

s_{task,round,role} = H(base_seed, task_id, round, role) —— sha256 稳定派生
（不用 Python hash()，其有进程级随机化）。每次 stochastic generate 前 re-seed，
保证：相同输入 + 相同 role seed ⇒ 相同生成；任何模块的插入/移除不影响其他
模块的采样。judge 贪心不采样，但按协议仍为每 role 派生（日志记录）。
"""
import hashlib
from typing import Any, Optional

ROLES = ("red", "target", "judge", "evaluator")


def derive_seed(base_seed: int, task_id: str, round_idx: int, role: str) -> int:
    if role not in ROLES:
        raise ValueError("unknown role: {}".format(role))
    key = "{}|{}|{}|{}".format(base_seed, task_id, round_idx, role)
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (2 ** 31 - 1)


def seed_role(base_seed: int, task_id: str, round_idx: int, role: str) -> int:
    """为一次 generate 调用设置确定性 RNG（CPU+CUDA 全设备）。返回派生种子。"""
    seed = derive_seed(base_seed, task_id, round_idx, role)
    try:
        import torch
        torch.manual_seed(seed)  # 同时 seed CPU 与全部 CUDA 设备
    except ImportError:
        pass
    return seed
