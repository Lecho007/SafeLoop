# -*- coding: utf-8 -*-
"""ControlFixCoordinator（Stage 1B-CF）：transition 中执行 ControlPolicy。

无实例级 per-episode 状态（BatchRunner 每条件共享一个 coordinator）——
上一轮决策存 state.metadata["last_control"]，本轮 action 产生后回填校验。
意图-执行分离日志（§25）写入 step.action.metadata["control_log"]。
"""
from core.coordinator_impl import HeuristicCoordinator
from core.control_layer import ControlPolicy
from core.protocol import ExperimentProtocol
from core.schemas import AttackState, AttackStep, SafetyTask


class ControlFixCoordinator(HeuristicCoordinator):
    name = "cf_coordinator"

    def __init__(self, scheduler, control_policy: ControlPolicy,
                 episode_key: str = "") -> None:
        super().__init__(scheduler)
        self.control_policy = control_policy

    def initialize(self, task: SafetyTask, protocol: ExperimentProtocol) -> AttackState:
        state = super().initialize(task, protocol)
        state.metadata["control"] = {
            "forced_strategy_family": state.current_strategy,
            "generation_mode": "normal", "feedback_action": None}
        state.metadata["last_control"] = None
        return state

    def transition(self, state: AttackState, step: AttackStep) -> AttackState:
        # 回填：本轮 action 是否满足上一轮控制决策
        last = state.metadata.get("last_control")
        if last is not None:
            executed = step.action.strategy
            forced = last.get("forced_strategy_family")
            last["executed_strategy_family"] = executed
            last["constraint_satisfied"] = (None if forced is None
                                            else executed == forced)
            step.action.metadata.setdefault("control_log", {}).update(last)

        state = super().transition(state, step)
        decision = self.control_policy.apply(
            step.feedback, step.action.strategy,
            episode_key="{}|{}".format(state.task.task_id, step.round_id))
        state.metadata["control"] = decision
        state.metadata["last_control"] = decision
        if self.control_policy.enforced and decision.get("forced_strategy_family"):
            state.current_strategy = decision["forced_strategy_family"]
        return state
