# -*- coding: utf-8 -*-
"""OfflineEvaluator：实验结束后批量评估所有 step（设计文档 §19/§21/§45）。

采用 final-only 模式：攻击过程完全不调用 Evaluator，绝不发生 evaluator 泄漏。
同时产出 Judge 与 Evaluator 的 disagreement 集合（Type A 高估 / Type B 漏检），
该集合正是 Stage 4 Hard Examples 的重要来源，现在就落盘。
"""
import json
import os
from typing import Dict, List

from core.schemas import AttackTrajectory
from evaluation.base_evaluator import BaseEvaluator


class OfflineEvaluator:
    name = "offline"

    def __init__(
        self,
        evaluator: BaseEvaluator,
        output_dir: str = "outputs/evaluations",
        disagreement_dir: str = "outputs/disagreement",
    ) -> None:
        self.evaluator = evaluator
        self.output_dir = output_dir
        self.disagreement_dir = disagreement_dir
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(disagreement_dir, exist_ok=True)
        self.disagreements: List[Dict] = []

    # ------------------------------------------------------------------
    def evaluate_trajectory(self, traj: AttackTrajectory) -> None:
        """填充每个 step 的 external_evaluation，并确定最终 success。"""
        first_success_result = None
        for step in traj.steps:
            result = self.evaluator.evaluate(
                task=traj.task,
                action=step.action,
                response=step.response,
            )
            step.external_evaluation = result
            if result.success and first_success_result is None:
                first_success_result = result
            self._record_disagreement(traj, step)
        traj.success = first_success_result is not None
        traj.final_evaluation = (
            first_success_result
            if first_success_result is not None
            else (traj.steps[-1].external_evaluation if traj.steps else None)
        )

    def evaluate_all(self, trajs: List[AttackTrajectory], name: str) -> Dict:
        self.disagreements = []  # 每次批评估独立统计，避免跨条件累积
        for t in trajs:
            self.evaluate_trajectory(t)
        eval_path = os.path.join(self.output_dir, "{}.jsonl".format(name))
        with open(eval_path, "w", encoding="utf-8") as f:
            for t in trajs:
                f.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
        dis_path = self._dump_disagreement(name)
        type_a = sum(1 for d in self.disagreements if d["type"] == "A")
        type_b = sum(1 for d in self.disagreements if d["type"] == "B")
        return {
            "evaluated_trajectories": len(trajs),
            "evaluated_steps": sum(len(t.steps) for t in trajs),
            "evaluator": self.evaluator.version
            if hasattr(self.evaluator, "version") else self.evaluator.name,
            "disagreement": {"type_A_judge_overestimate": type_a,
                             "type_B_judge_missed": type_b,
                             "total": len(self.disagreements)},
            "evaluations_path": eval_path,
            "disagreement_path": dis_path,
        }

    # ------------------------------------------------------------------
    def _record_disagreement(self, traj: AttackTrajectory, step) -> None:
        ext = step.external_evaluation
        if ext is None:
            return
        judge_success = step.online_success
        if judge_success == ext.success:
            return
        self.disagreements.append({
            "type": "A" if judge_success else "B",  # A: Judge 高估；B: Judge 漏检
            "experiment_id": traj.experiment_id,
            "condition_id": traj.condition_id,
            "trajectory_id": traj.trajectory_id,
            "task_id": traj.task.task_id,
            "harm_category": traj.task.harm_category,
            "round_id": step.round_id,
            "strategy": step.action.strategy,
            "judge_outcome": step.judge_output.outcome,
            "evaluator_outcome": ext.outcome,
            "judge_success": judge_success,
            "evaluator_success": ext.success,
            "prompt": step.action.prompt,
            "response": step.response.text,
        })

    def _dump_disagreement(self, name: str) -> str:
        path = os.path.join(self.disagreement_dir, "{}.jsonl".format(name))
        with open(path, "w", encoding="utf-8") as f:
            for d in self.disagreements:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        return path
