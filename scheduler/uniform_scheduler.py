# -*- coding: utf-8 -*-
"""均匀调度器：V0.1 的默认 Scheduler（Stage 3 将替换为 RiskScheduler）。"""
import random
from typing import List, Optional

from scheduler.base_scheduler import BaseScheduler


class UniformScheduler(BaseScheduler):
    """在配置的风险类别 / 攻击策略空间上均匀采样。"""

    name = "uniform"

    def __init__(
        self,
        risk_categories: List[str],
        attack_strategies: List[str],
        rng: Optional[random.Random] = None,
    ) -> None:
        self.risk_categories = list(risk_categories)
        self.attack_strategies = list(attack_strategies)
        self.rng = rng or random.Random()

    def sample_category(self) -> str:
        return self.rng.choice(self.risk_categories)

    def sample_strategy(self, exclude: Optional[str] = None) -> str:
        pool = [s for s in self.attack_strategies if s != exclude]
        if not pool:
            pool = self.attack_strategies
        return self.rng.choice(pool)
