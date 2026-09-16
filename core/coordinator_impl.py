# -*- coding: utf-8 -*-
"""HeuristicCoordinator V0.2。

与 V0.1 的区别（由 Stage 1 设计决定）：
  - 类别来自 SafetyTask.harm_category（goal 固定，不再每轮采样）；
  - 策略的适应性切换移交 Red Agent（由 feedback level 驱动），
    协调器只传递 state.current_strategy；
  - 不因在线成功提前停止，只在预算耗尽时停止（设计文档 §23）。
"""
from typing import Optional

from core.coordinator import BaseCoordinator, CoordinatorAction
from core.protocol import ExperimentProtocol, INITIAL_SEED_POLICIES
from core.schemas import AttackState, AttackStep, SafetyTask
from scheduler.base_scheduler import BaseScheduler


class HeuristicCoordinator(BaseCoordinator):
    name = "heuristic"

    def __init__(self, scheduler: BaseScheduler) -> None:
        self.scheduler = scheduler
        self._protocol: Optional[ExperimentProtocol] = None

    # ------------------------------------------------------------------
    def initialize(self, task: SafetyTask, protocol: ExperimentProtocol) -> AttackState:
        self._protocol = protocol
        if protocol.initial_seed_policy in INITIAL_SEED_POLICIES:
            strategy = INITIAL_SEED_POLICIES[protocol.initial_seed_policy]
        else:
            strategy = self.scheduler.sample_strategy()
        return AttackState(
            task=task,
            target_id=task.metadata.get("target_id", "default-target"),
            round_id=0,
            target_queries_used=0,
            target_query_budget=protocol.target_query_budget,
            current_strategy=strategy,
        )

    # ------------------------------------------------------------------
    def decide(self, state: AttackState) -> CoordinatorAction:
        if state.done:
            return CoordinatorAction(
                harm_category=state.task.harm_category,
                attack_strategy=state.current_strategy,
                budget=0,
                stop=True,
            )
        return CoordinatorAction(
            harm_category=state.task.harm_category,
            attack_strategy=state.current_strategy,
            budget=1,
            stop=False,
        )

    # ------------------------------------------------------------------
    def transition(self, state: AttackState, step: AttackStep) -> AttackState:
        state.history.append(step)
        state.round_id = step.round_id + 1
        state.target_queries_used += 1
        state.current_strategy = step.action.strategy
        state.last_feedback = step.feedback
        if state.remaining_budget <= 0:
            state.stop_reason = "budget_exhausted"
        return state
