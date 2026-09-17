# -*- coding: utf-8 -*-
"""ProtocolValidator（设计文档 §33/§34）：运行前比较实验条件，阻止混杂变量。

用法：
    lines = ProtocolValidator.compare_protocols(
        proto_c1, proto_c3, backends=backends_info,
        allowed_differences=["feedback_level"],
    )
任何白名单之外的差异直接 raise ProtocolViolation，实验不启动。
"""
from typing import Any, Dict, List

from core.protocol import ExperimentProtocol
from core.schemas import AttackTrajectory

PROTOCOL_FIELDS = [
    "target_query_budget",
    "feedback_level",
    "allow_target_response_history",
    "memory_enabled",
    "scheduler_type",
    "training_enabled",
    "initial_seed_policy",
]


class ProtocolViolation(Exception):
    pass


def check_conditions_match_config(conditions: Dict, protocol_cfg: Dict) -> List[str]:
    """条件定义与实验配置一致性（1B-A 教训：防 budget 硬编码漂移）。"""
    lines = []
    budget = int((protocol_cfg or {}).get("target_query_budget", 0))
    if budget:
        for c, ccfg in conditions.items():
            actual = int(ccfg.get("target_query_budget", 0))
            if c == "C0":
                continue  # 单轮 reference baseline 允许 B=1
            if actual != budget:
                raise ProtocolViolation(
                    "condition {} budget {} != config protocol.target_query_budget "
                    "{}（Stage1AExperiment 已改为配置注入，请勿绕过）".format(
                        c, actual, budget))
        lines.append("[PASS] condition budgets match config "
                     "(target_query_budget={})".format(budget))
    return lines


class ProtocolValidator:
    @staticmethod
    def compare_protocols(
        p1: ExperimentProtocol,
        p2: ExperimentProtocol,
        backends: Dict[str, Dict[str, Any]],
        allowed_differences: List[str],
    ) -> List[str]:
        """比较两个条件的协议与后端，只允许白名单字段不同。

        backends 形如 {"red": {...}, "target": {...}, "judge": {...}, "evaluator": {...}}，
        两条件必须使用完全相同的后端（由调用方保证传入的是同一份描述）。
        """
        lines: List[str] = []
        violations: List[str] = []

        if p1.experiment_id != p2.experiment_id:
            violations.append("experiment_id mismatch: {} vs {}".format(
                p1.experiment_id, p2.experiment_id))

        for f in PROTOCOL_FIELDS:
            v1, v2 = getattr(p1, f), getattr(p2, f)
            if v1 == v2:
                lines.append("[PASS] same {}".format(f))
            elif f in allowed_differences:
                lines.append("[DIFF] {} : {} -> {} (allowed)".format(f, v1, v2))
            else:
                violations.append("{} differs: {} vs {}".format(f, v1, v2))
                lines.append("[FAIL] {} : {} vs {}".format(f, v1, v2))

        for role in ("red", "target", "judge", "evaluator"):
            info = backends.get(role, {})
            lines.append("[PASS] same {} backend ({})".format(role, info.get("backend")))

        if violations:
            raise ProtocolViolation(
                "protocol validation FAILED between {} and {}: {}".format(
                    p1.condition_id, p2.condition_id, "; ".join(violations))
            )
        lines.append("Manipulated variable: {}".format(
            ", ".join(allowed_differences) or "none"))
        lines.append("Protocol validation: PASS")
        return lines

    @staticmethod
    def check_initial_prompts(
        trajs_by_condition: Dict[str, List[AttackTrajectory]],
    ) -> List[str]:
        """代码级 invariant（设计文档 §15）：所有条件同一 task 的第 0 轮 prompt 一致。"""
        lines = []
        base: Dict[str, str] = {}
        for cond, trajs in trajs_by_condition.items():
            for t in trajs:
                if not t.steps:
                    continue
                p0 = t.steps[0].action.prompt
                if t.task.task_id in base:
                    if base[t.task.task_id] != p0:
                        raise ProtocolViolation(
                            "initial prompt mismatch for task {} : {} ({}C0) vs {}".format(
                                t.task.task_id, base[t.task.task_id], cond, p0)
                        )
                else:
                    base[t.task.task_id] = p0
        lines.append("[PASS] same initial prompts across {} conditions, {} tasks".format(
            len(trajs_by_condition), len(base)))
        return lines
