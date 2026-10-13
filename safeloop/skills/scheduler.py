# -*- coding: utf-8 -*-
"""风险调度器（roadmap A3）：总预算约束下的两阶段任务选择。

设计（简化实现，见 roadmap 修正记录）：
  阶段 A（round 0）—— 基础覆盖：全部任务各 1 轮（受总预算截断）；
  阶段 B（round ≥1）—— 自适应追加：类别覆盖缺口优先（相对轮转），
  可选在线观察信号（裁判 Unsafe 计数）做同优先级内排序，种子随机破平。

红线 3：调度不以"发现风险"为唯一目标——覆盖约束优先于任何信号；
在线信号只在自适应评估模式（显式开启 adaptive_budget）下参与，且只是
过程观察，与独立评估结论无关（红线 1）。

作为 BatchRunner 的 round_selector 挂钩：每轮边界从 active slots 中
选出本轮允许推进的子集；未被选中的 slot 本轮不发起任何模型调用。
"""
import random
from collections import Counter
from typing import List

ONLINE_HINT_KEYS = ("Unsafe", "STRONG")


class AdaptiveScheduler:
    def __init__(self, total_budget: int, per_task_cap: int, seed: int = 42,
                 use_online_signal: bool = True) -> None:
        self.total = int(total_budget)
        self.cap = max(1, int(per_task_cap))
        self.rng = random.Random(seed)
        self.use_online_signal = use_online_signal
        self.granted: Counter = Counter()      # task_id → 已授予轮数
        self.cat_of: dict = {}                 # task_id → harm_category
        self.spent = 0
        self.decisions: List[dict] = []        # 决策留痕（可追溯）

    # ------------------------------------------------------------------ 信号
    @staticmethod
    def _online_hint(slot) -> float:
        """在线观察信号：轨迹内裁判 Unsafe/STRONG 出现次数（仅排序用）。"""
        n = 0
        for s in getattr(slot.state, "history", ()) or ():
            meta = getattr(getattr(s, "judge_output", None), "metadata", None) or {}
            if meta.get("safety") in ONLINE_HINT_KEYS or \
                    meta.get("advancement") in ONLINE_HINT_KEYS:
                n += 1
        return float(n)

    # ------------------------------------------------------------------ 主入口
    def select(self, round_idx: int, slots: List) -> List:
        if self.spent >= self.total or not slots:
            return []
        for slot in slots:
            tid = slot.task.task_id
            self.cat_of.setdefault(tid, slot.task.harm_category)
        if round_idx == 0:
            eligible = [s for s in slots
                        if self.granted[s.task.task_id] < self.cap]
            chosen = eligible[:max(0, self.total - self.spent)]
        else:
            chosen = self._phase_b(round_idx, slots)
        for s in chosen:
            self.granted[s.task.task_id] += 1
            self.spent += 1
        self.decisions.append({
            "round": round_idx,
            "granted": [s.task.task_id for s in chosen],
            "skipped": [s.task.task_id for s in slots if s not in chosen],
            "spent": self.spent, "remaining": max(0, self.total - self.spent)})
        return chosen

    # ------------------------------------------------------------------ 阶段 B
    def _phase_b(self, round_idx: int, slots: List) -> List:
        cat_totals: Counter = Counter(self.cat_of.values())
        cat_granted: Counter = Counter()
        for tid, n in self.granted.items():
            cat_granted[self.cat_of[tid]] += n

        def _priority(slot):
            tid = slot.task.task_id
            cat = self.cat_of[tid]
            # 覆盖缺口：该类别平均每任务已授予轮数越少越优先
            deficit = 1.0 - (cat_granted[cat] / max(1, cat_totals[cat])) / self.cap
            hint = self._online_hint(slot) if self.use_online_signal else 0.0
            return (-round(deficit, 4), -hint, self.rng.random())

        candidates = [s for s in slots
                      if self.granted[s.task.task_id] < self.cap]
        candidates.sort(key=_priority)
        return candidates[:max(0, self.total - self.spent)]

    # ------------------------------------------------------------------ 汇总
    def summary(self) -> dict:
        under = sum(1 for n in self.granted.values() if n < self.cap)
        return {"total_budget": self.total, "queries_granted": self.spent,
                "per_task_cap": self.cap, "tasks_touched": len(self.granted),
                "under_tested_tasks": under,
                "n_round_decisions": len(self.decisions)}
