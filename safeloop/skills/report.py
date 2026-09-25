# -*- coding: utf-8 -*-
"""Report Skill（v1.0 设计 §十九/§二十）：轨迹+指标 → 带证据的最终回答。

14 节结构；结论必须带证据（条件化表述）；代表性案例自动挑选
（首轮拒绝→后续成功的转变轨迹优先——最能体现多轮探索价值）。
"""
import json
from collections import Counter
from typing import Dict

from evaluation.metrics import (asr_at_k, auc_b, condition_summary, ctts,
                                mean_ctts)


class ReportSkill:
    name = "report"
    version = "report-1.0"

    def build(self, run_id: str, plan, trajectories: Dict[str, list]) -> Dict:
        std = trajectories.get("STD", [])
        gui = trajectories.get("GUI", [])
        primary = gui if (plan.request.mode == "guided" and gui) else (std or gui)
        mode = plan.request.mode
        m = condition_summary(primary, plan.request.budget_per_task) if primary else {}

        # 分域
        domains = {}
        for dom_key, dom_val in (("content", "content_observable"),
                                 ("goal", "goal_compliance")):
            sub = [t for t in primary
                   if (t.task.metadata or {}).get("feedback_observability") == dom_val]
            domains[dom_key] = condition_summary(sub, 5) if sub else None

        risk_tasks = [t for t in primary if any(
            s.external_evaluation and s.external_evaluation.success
            for s in t.steps)]
        cases = self._representative_cases(primary, k=3)
        cats = Counter(t.task.harm_category for t in risk_tasks)

        answer = self._answer(plan, len(primary), len(risk_tasks), cats, mode)
        comparison = None
        if std and gui:
            comparison = self._compare(std, gui)

        return {
            "run_id": run_id,
            "overview": {"answer": answer,
                         "risk_tasks": len(risk_tasks),
                         "total_tasks": len(primary),
                         "mode": mode,
                         "target": plan.request.target_model},
            "metrics": {"user_layer": {k: m.get(k) for k in (
                            "asr_at_k", "auc_b", "mean_ctts")},
                        "research_layer": {k: m.get(k) for k in (
                            "strategy_switch_rate", "harmful_switch_rate",
                            "effective_strategy_switch_rate")}},
            "domains": domains,
            "risk_distribution": dict(cats.most_common()),
            "representative_cases": cases,
            "comparison": comparison,
            "configuration": {"budget_per_task": plan.request.budget_per_task,
                              "suite": plan.request.suite,
                              "branches": plan.branches,
                              "seed": getattr(plan, "seed", 42)},
            "limitations": self._limitations(plan),
            "provenance": {"report_skill": self.version,
                           "main_agent_version": "main-agent-1.0"},
        }

    # ---------------------------------------------------------------- cases
    @staticmethod
    def _representative_cases(trajs, k=3):
        """优先：首轮 E 失败→后续成功的转变轨迹（多轮探索价值的直接证据）。"""
        def _ok(s):
            return bool(s.external_evaluation and s.external_evaluation.success)
        turning, first_round, late = [], [], []
        for t in trajs:
            if not t.steps:
                continue
            if any(_ok(s) for s in t.steps):
                rec = {"task_id": t.task.task_id,
                       "goal": t.task.goal[:150],
                       "category": t.task.harm_category,
                       "rounds": [{"round": s.round_id,
                                   "strategy": s.action.strategy,
                                   "prompt": s.action.prompt[:180],
                                   "response": s.response.text[:220],
                                   "judge_outcome": s.judge_output.outcome or
                                   s.judge_output.metadata.get("advancement", ""),
                                   "evaluator_success": _ok(s)}
                                  for s in t.steps]}
                if not _ok(t.steps[0]):
                    turning.append(rec)
                elif len(t.steps) > 1:
                    late.append(rec)
                else:
                    first_round.append(rec)
        picked = (turning + late + first_round)[:k]
        for p in picked:
            p["why_representative"] = (
                "首轮未出现风险，多轮自适应后触发（探索价值）"
                if p in turning[:k] else "代表性风险轨迹")
        return picked

    # ---------------------------------------------------------------- answer
    @staticmethod
    def _answer(plan, n_total, n_risk, cats, mode) -> str:
        top = ", ".join("{}×{}".format(c.replace("JBB:", ""), v)
                        for c, v in list(cats.most_common())[:3]) or "未检出"
        base = ("在本次评估范围内（{n} 个安全任务 × 每任务 {b} 次多轮查询），"
                "独立评估器在 {r} 个任务中确认了风险响应。"
                "风险主要集中在：{top}。").format(n=n_total or 100,
                                                b=plan.request.budget_per_task,
                                                r=n_risk, top=top)
        scope = ("该结论仅适用于当前模型版本、测试集、查询预算与评估器配置；"
                 "Judge 在本次运行中仅作过程观察（Standard 模式）。"
                 if mode == "standard" else
                 "该结论仅适用于当前模型版本、测试集、查询预算与评估器配置。")
        return base + scope

    @staticmethod
    def _compare(std, gui) -> Dict:
        b = 5
        ms, mg = condition_summary(std, b), condition_summary(gui, b)
        return {"standard": {k: ms.get(k) for k in ("asr_at_k", "auc_b", "mean_ctts")},
                "guided": {k: mg.get(k) for k in ("asr_at_k", "auc_b", "mean_ctts")},
                "note": ("Judge feedback 的作用需按域解读：详见 1B-R 研究结论——"
                         "content 域 HSR 改善但 ASR 未必提升；证据随轨迹提供。")}

    @staticmethod
    def _limitations(plan) -> list:
        return [
            "评估结论条件于当前 Target 模型版本与解码配置",
            "任务集为内置 JBB100 子集（英文为主）",
            "独立评估器为 StrongREJECT（自动化评估器，合规域存在已知偏松样本）",
            "查询预算固定 B={}，未做 early-stop，跨预算外推未验证".format(
                plan.request.budget_per_task),
        ]
