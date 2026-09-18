# -*- coding: utf-8 -*-
"""TaskAwareJudgeRouterV1（Stage 1B-R §7/§9）。

确定性路由，无学习变量：
    content_observable → J_c（Qwen3Guard，输入 attack prompt + response）
    goal_compliance     → J_g（Qwen3-1.7B goal judge，输入 original goal + response）

硬原则（§9）：One Task → One Primary Judge——未被选中的 judge 不会被调用、
不进入在线 state；shadow 评估只能事后 Replay。两路模型同时驻留仅是资源
优化（judge 相位独占 GPU，~5.2G），不影响语义。
"""
from typing import Optional

from agents.base_judge import BaseJudge
from core.schemas import AttackAction, JudgeOutput, SafetyTask, TargetResponse

ROUTER_VERSION = "task-aware-router-v1"


class TaskAwareJudgeRouter(BaseJudge):
    name = "routed"
    version = ROUTER_VERSION

    def __init__(self, content_judge: BaseJudge, goal_judge: BaseJudge,
                 model_manager=None, mapping_version: str = "jbb_observability_v1") -> None:
        self.content_judge = content_judge
        self.goal_judge = goal_judge
        self.manager = model_manager
        self.mapping_version = mapping_version
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            if self.manager is not None:
                self.manager.acquire("judge", lambda: None)
            return

        def _load_both():
            self.content_judge._ensure_loaded()
            self.goal_judge._ensure_loaded()

        def _unload_both():
            self.content_judge._unload()
            self.goal_judge._unload()
            self._loaded = False

        if self.manager is not None:
            self.manager.acquire("judge", _load_both)
            self.manager.register_unloader(_unload_both)
        else:
            _load_both()
        self._loaded = True

    # ------------------------------------------------------------------ api
    def route(self, task: SafetyTask) -> str:
        """确定性路由：只读冻结的 feedback_observability 元数据。"""
        obs = (task.metadata or {}).get("feedback_observability", "")
        if obs == "goal_compliance":
            return "goal"
        if obs == "content_observable":
            return "content"
        raise ValueError(
            "task {} 缺少冻结的 feedback_observability（mapping_version={}）".format(
                task.task_id, self.mapping_version))

    def evaluate(self, task: SafetyTask, action: AttackAction,
                 response: TargetResponse) -> JudgeOutput:
        self._ensure_loaded()
        if self.manager is not None:
            self.manager.bump("judge")
        which = self.route(task)
        judge = self.goal_judge if which == "goal" else self.content_judge
        out = judge.evaluate(task, action, response)
        # Router provenance（§22）：selected_judge / router_version 附到每步
        out.metadata["router_version"] = ROUTER_VERSION
        out.metadata["selected_judge"] = which
        out.metadata["mapping_version"] = self.mapping_version
        return out
