# -*- coding: utf-8 -*-
"""SafeLoop Main Agent（v1.0 设计 §五/§二十九）。

职责：Question Understanding / Planning / Orchestration / Supervision / Answer。
实现原则（§二十八）：Main Agent 不直接碰底层模型——规划为确定性解析器 +
计划模板（演示鲁棒），最终答案叙述由 Report Skill 的模板引擎生成（可选 LLM
润色钩子）。状态机：IDLE→PLANNING→READY→RUNNING→EVALUATING→ANALYZING→
REPORTING→COMPLETED（异常 FAILED/CANCELLED）。

三种模式（§十三）：
  standard = Red 自主多轮 + Judge 全程观察（SHADOW，不进 red 上下文）
  guided   = Judge→Feedback→Controller→Red（ACTIVE，Experimental）
  compare  = 同时跑 standard 与 guided 并给出对比结论
"""
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from engine.batch_runner import (FEEDBACK_MODE_ACTIVE, FEEDBACK_MODE_SHADOW,
                                 BatchRunner)
from engine.checkpoint import load_checkpoint, rebuild_from_payload
from engine.factory import (build_evaluator, build_memory, build_scheduler,
                            load_tasks)
from memory.trajectory_store import TrajectoryStore
from utils.io import load_yaml

logger = logging.getLogger("safeloop.main_agent")

STATES = ("IDLE", "PLANNING", "READY", "RUNNING", "EVALUATING", "ANALYZING",
          "REPORTING", "COMPLETED", "FAILED", "CANCELLED")

MODES = ("standard", "guided", "compare")


@dataclass
class EvaluationRequest:
    """用户评估请求（自然语言解析产物）。"""
    question: str
    target_model: str = "phi-3.5-mini"
    scope: List[str] = field(default_factory=lambda: ["content_safety", "goal_advancement"])
    suite: str = "jbb100"
    budget_per_task: int = 5
    mode: str = "standard"
    max_tasks: Optional[int] = None     # 演示用子集
    api_target: Optional[Dict[str, Any]] = None   # 黑盒 API 待测模型配置
    output: List[str] = field(default_factory=lambda: [
        "summary", "metrics", "representative_cases", "full_report"])

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class EvaluationPlan:
    """计划（§三）：任务集/预算/域分布/模式/judge 配置。"""
    plan_id: str
    request: EvaluationRequest
    tasks_file: str
    n_tasks: int
    domains: Dict[str, int]
    branches: List[Dict[str, str]]     # [{name, domain, mode}]
    config_path: str

    def to_dict(self) -> Dict[str, Any]:
        return {"plan_id": self.plan_id, "request": self.request.to_dict(),
                "tasks_file": self.tasks_file, "n_tasks": self.n_tasks,
                "domains": self.domains, "branches": self.branches,
                "config_path": self.config_path}


# ---------------------------------------------------------------- task parser
class TaskParserSkill:
    """问题→EvaluationRequest（确定性关键词解析，LLM 可后置增强）。"""
    name = "task_parser"

    TARGETS = {"phi": "phi-3.5-mini", "phi-3.5": "phi-3.5-mini",
               "mistral": "mistral-7b", "qwen": "qwen", "本地": "local"}
    MODE_WORDS = {"比较": "compare", "对比": "compare", "compare": "compare",
                  "引导": "guided", "guided": "guided", "反馈": "guided"}

    def parse(self, question: str, **overrides) -> EvaluationRequest:
        q = question.lower()
        req = EvaluationRequest(question=question)
        for k, v in self.TARGETS.items():
            if k in q:
                req.target_model = v
                break
        for k, v in self.MODE_WORDS.items():
            if k in q:
                req.mode = v
                break
        for word in ("内容", "content"):
            if word in q and "内容安全" not in req.scope:
                pass  # scope 默认双域
        if "快速" in q or "quick" in q:
            req.max_tasks = 5
        for k, v in overrides.items():
            setattr(req, k, v)
        if req.mode not in MODES:
            req.mode = "standard"
        return req


# ---------------------------------------------------------------- planner
class EvaluationPlanner:
    """EvaluationRequest → EvaluationPlan（确定性）。"""
    name = "planner"

    def __init__(self, config_path: str = "configs/hardware/rtx4060_8g_1br.yaml"):
        self.config_path = config_path

    def plan(self, req: EvaluationRequest) -> EvaluationPlan:
        tasks_file = ("data/tasks/jbb100_full.jsonl"
                      if req.suite == "jbb100" else req.suite)
        branches = []
        if req.mode == "standard":
            branches = [{"name": "STD", "domain": "all", "mode": FEEDBACK_MODE_SHADOW}]
        elif req.mode == "guided":
            branches = [{"name": "GUI", "domain": "all", "mode": FEEDBACK_MODE_ACTIVE}]
        else:  # compare
            branches = [{"name": "STD", "domain": "all", "mode": FEEDBACK_MODE_SHADOW},
                        {"name": "GUI", "domain": "all", "mode": FEEDBACK_MODE_ACTIVE}]
        return EvaluationPlan(
            plan_id="plan-{}".format(uuid.uuid4().hex[:8]), request=req,
            tasks_file=tasks_file, n_tasks=req.max_tasks or 100,
            domains={"content": 70, "goal": 30}, branches=branches,
            config_path=self.config_path)


# ---------------------------------------------------------------- main agent
class SafeLoopMainAgent:
    """总控（§五六件事：理解/规划/构造/调度/监督/回答）。"""
    name = "safeloop_main_agent"
    version = "main-agent-1.0"

    def __init__(self, config_path: str = "configs/hardware/rtx4060_8g_1br.yaml",
                 seed: int = 42):
        self.parser = TaskParserSkill()
        self.planner = EvaluationPlanner(config_path)
        self.seed = seed
        self.state = "IDLE"
        self.run_id: Optional[str] = None
        self.plan: Optional[EvaluationPlan] = None
        self.events: List[Dict] = []
        self.trajectories: Dict[str, list] = {}
        self.report: Optional[Dict] = None

    # -------------------------------------------------------------- events
    def _emit(self, kind: str, **data) -> None:
        ev = {"ts": time.time(), "state": self.state, "kind": kind, **data}
        self.events.append(ev)
        logger.info("EVENT %s %s", kind, json.dumps(
            {k: v for k, v in data.items() if k != "prompt"}, ensure_ascii=False)[:200])

    def _set_state(self, s: str) -> None:
        self.state = s
        self._emit("state_changed", state=s)

    # -------------------------------------------------------------- phases
    def submit(self, question: str, **overrides) -> EvaluationPlan:
        self._set_state("PLANNING")
        req = self.parser.parse(question, **overrides)
        self.run_id = "run-{}".format(uuid.uuid4().hex[:10])
        self.plan = self.planner.plan(req)
        self._emit("plan_ready", plan=self.plan.to_dict())
        self._set_state("READY")
        return self.plan

    def run(self) -> Dict:
        """执行（RUNNING→EVALUATING→ANALYZING→REPORTING→COMPLETED）。"""
        from experiments.stage1br import (PlainCoordinator, build_branch_stack,
                                          _split_domains)
        assert self.plan is not None
        cfg = load_yaml(self.plan.config_path)
        tasks = load_tasks(cfg)
        if self.plan.request.max_tasks:
            content, goal = _split_domains(tasks)
            nc = min(self.plan.request.max_tasks * 7 // 10, len(content))
            ng = min(self.plan.request.max_tasks - nc, len(goal))
            tasks = content[:nc] + goal[:ng]
        self._set_state("RUNNING")
        self.trajectories = {}
        for br in self.plan.branches:
            self._run_branch(cfg, tasks, br)

        self._set_state("EVALUATING")
        evaluator = build_evaluator(cfg)
        from evaluation.offline_evaluator import OfflineEvaluator
        for name, trajs in self.trajectories.items():
            offline = OfflineEvaluator(evaluator)
            offline.disagreements = []
            offline.evaluate_all(trajs, "{}_{}".format(self.run_id, name))
            self._emit("evaluator_completed", branch=name, n=len(trajs))

        self._set_state("ANALYZING")
        from safeloop.skills.report import ReportSkill
        self._set_state("REPORTING")
        self.report = ReportSkill().build(self.run_id, self.plan,
                                            self.trajectories)
        os.makedirs("outputs/reports", exist_ok=True)
        path = "outputs/reports/{}_report.json".format(self.run_id)
        json.dump(self.report, open(path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        self._emit("report_ready", path=path, summary=self.report["overview"]["answer"])
        self._set_state("COMPLETED")
        return self.report

    # -------------------------------------------------------------- branch
    def _run_branch(self, cfg, tasks, br: Dict) -> None:
        from experiments.stage1br import PlainCoordinator, build_branch_stack
        from core.protocol import ExperimentProtocol
        mm, red, target, judge, fb_builder, tpl = build_branch_stack(
            cfg, "B" if br["mode"] == FEEDBACK_MODE_ACTIVE else "A")
        # 黑盒 API Target 覆盖（用户提供的远端模型替换本地 Phi-3.5）
        if (self.plan.request.api_target or {}).get("base_url"):
            from targets.api_target import build_api_target
            target = build_api_target(self.plan.request.api_target)
        # standard 模式：全部任务统一用 no-feedback 红方栈 + shadow 观察
        if br["mode"] == FEEDBACK_MODE_SHADOW:
            from agents.hf_red_agent import HfRedAgent
            from feedback.feedback_builder_v2 import FeedbackBuilderV2
            red = HfRedAgent(
                model_path=cfg["red_agent"]["model_path"], model_manager=mm,
                template_path="prompts/red/real_v1.yaml",
                dtype=cfg["red_agent"].get("dtype", "bfloat16"),
                device=cfg["red_agent"].get("device", "cuda"),
                do_sample=True, temperature=0.7, top_p=0.9,
                max_new_tokens=256, rng=random.Random(self.seed))
            from agents.qwen_guard_judge_v2 import Qwen3GuardJudgeV2
            judge = Qwen3GuardJudgeV2(
                model_path=cfg["judge"]["model_path"], max_new_tokens=64)
            fb_builder = FeedbackBuilderV2()

        def coordinator_factory(proto):
            return PlainCoordinator(build_scheduler(cfg, random.Random(self.seed)))

        def reward_factory(budget):
            from core.reward import RewardConfig, RewardFunction
            return RewardFunction(RewardConfig(**(cfg.get("reward", {}) or {})), budget)

        cond = "{}_{}".format(self.run_id, br["name"])
        batch = BatchRunner(
            coordinator_factory=coordinator_factory, red_agent=red,
            target=target, judge=judge, memory=build_memory(cfg),
            reward_factory=reward_factory, feedback_builder=fb_builder,
            model_manager=mm, base_seed=self.seed,
            provenance={"run_id": self.run_id, "branch": br["name"],
                        "feedback_mode": br["mode"], "mode": self.plan.request.mode,
                        "main_agent": self.version, "seed": self.seed})
        protocol = ExperimentProtocol(
            experiment_id=self.run_id, condition_id=br["name"],
            target_query_budget=self.plan.request.budget_per_task,
            feedback_level=("structured" if br["mode"] == FEEDBACK_MODE_ACTIVE
                            else "none"),
            allow_target_response_history=True, memory_enabled=False,
            scheduler_type="uniform", training_enabled=False,
            initial_seed_policy="fixed_direct",
            metadata={"feedback_mode": br["mode"]})
        self._emit("branch_started", branch=br["name"], n_tasks=len(tasks))
        trajs = batch.run(tasks, {br["name"]: protocol})[br["name"]]
        self.trajectories[br["name"]] = trajs
        self._emit("branch_completed", branch=br["name"], n=len(trajs))

    # -------------------------------------------------------------- misc
    def cancel(self) -> None:
        if self.state in ("RUNNING", "EVALUATING", "ANALYZING", "REPORTING"):
            self._set_state("CANCELLED")

    def status(self) -> Dict:
        return {"run_id": self.run_id, "state": self.state,
                "n_events": len(self.events),
                "branches": {k: len(v) for k, v in self.trajectories.items()},
                "report_ready": self.report is not None}
