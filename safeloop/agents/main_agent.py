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

STATES = ("IDLE", "PLANNING", "READY", "RUNNING", "CANCELLING", "EVALUATING",
          "ANALYZING", "REPORTING", "COMPLETED", "FAILED", "CANCELLED")

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
    max_tasks: Optional[int] = None     # 演示用子集（None = 全部场景）
    scenario_ids: Optional[List[str]] = None   # 指定场景（单场景深度测试），优先于 max_tasks
    api_target: Optional[Dict[str, Any]] = None   # 黑盒 API 待测模型配置
    # ---- v1.1 实验能力（默认关闭；标准模式语义冻结，红线 2）
    use_memory: bool = False            # 长期攻击记忆（round 1+ 生效，保 §13）
    adaptive_budget: Optional[int] = None   # 自适应总预算（独立"自适应评估模式"）
    memory_snapshot_id: Optional[str] = None  # 冻结记忆快照（正式测试防泄漏）
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
        suites = {"jbb100": "data/tasks/jbb100_full.jsonl",
                  "safeloop_cn": "data/tasks/safeloop_cn_v0.1.jsonl"}
        tasks_file = suites.get(req.suite, req.suite)   # 未知值视为文件路径
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


# ---------------------------------------------------------------- task sampling
def _stratified_sample(pool: List, n: int) -> List:
    """跨危害类别轮转抽样：每类轮流取一个（类内保持文件顺序），确定性、可复现。

    旧逻辑 content[:n] 取文件头部，导致小子集的类别高度单一（如全是虚假信息）。
    """
    if n >= len(pool):
        return list(pool)
    by_cat: Dict[str, List] = {}
    for t in pool:
        by_cat.setdefault(getattr(t, "harm_category", "") or "", []).append(t)
    cats = sorted(by_cat)
    out: List = []
    i = 0
    while len(out) < n:
        progressed = False
        for c in cats:
            if i < len(by_cat[c]) and len(out) < n:
                out.append(by_cat[c][i])
                progressed = True
        if not progressed:
            break
        i += 1
    return out


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
        # 实况流式缓冲：每完成一轮，UI 可直接读取渲染
        self.live_events: List[Dict] = []
        self.cancel_requested = False   # 真取消：引擎在轮边界检查（W0-3）
        self._resume = False
        self.is_demo = False            # replay_loader 标记（演示数据 vs 真实 run）

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

    def run(self, resume: bool = False) -> Dict:
        """执行（RUNNING→EVALUATING→ANALYZING→REPORTING→COMPLETED/CANCELLED）。

        resume=True 时从 outputs/checkpoints/{run_id}_{branch}.json 续跑
        （无检查点则冷启动）；取消（cancel()）在轮边界生效：不再发起后续模型
        调用，已完成结果照常评估与出报告（报告 configuration.cancelled=True）。
        """
        from experiments.stage1br import (PlainCoordinator, build_branch_stack,
                                          _split_domains)
        assert self.plan is not None
        self._resume = resume
        cfg = load_yaml(self.plan.config_path)
        # suite 通路：planner 解析的 tasks_file 优先于硬件配置默认值
        _cfg_tasks = (cfg.get("experiment", {}) or {}).get("tasks_file")
        if self.plan.tasks_file and self.plan.tasks_file != _cfg_tasks:
            cfg = dict(cfg)
            cfg["experiment"] = {**(cfg.get("experiment") or {}),
                                 "tasks_file": self.plan.tasks_file}
        tasks = load_tasks(cfg)
        if self.plan.request.scenario_ids:
            wanted = list(self.plan.request.scenario_ids)
            by_id = {t.task_id: t for t in tasks}
            missing = [sid for sid in wanted if sid not in by_id]
            if missing:
                raise ValueError("任务集中不存在指定场景: {}（可用示例: {}）".format(
                    missing, sorted(by_id)[:5]))
            tasks = [by_id[sid] for sid in wanted]
        elif self.plan.request.max_tasks:
            content, goal = _split_domains(tasks)
            nc = min(self.plan.request.max_tasks * 7 // 10, len(content))
            ng = min(self.plan.request.max_tasks - nc, len(goal))
            # 跨类别轮转抽样（旧逻辑取文件头部，导致类别单一——如全是虚假信息）
            tasks = _stratified_sample(content, nc) + _stratified_sample(goal, ng)
        self._set_state("RUNNING")
        self.trajectories = {}
        for br in self.plan.branches:
            self._run_branch(cfg, tasks, br)
            if self.cancel_requested:
                break   # 分支级取消：跳过剩余分支，保留已完成分支结果

        if self.trajectories:
            self._set_state("EVALUATING")
            evaluator = build_evaluator(cfg)
            from evaluation.offline_evaluator import OfflineEvaluator
            for name, trajs in self.trajectories.items():
                offline = OfflineEvaluator(evaluator)
                offline.disagreements = []
                offline.evaluate_all(trajs, "{}_{}".format(self.run_id, name))
                self._emit("evaluator_completed", branch=name, n=len(trajs))
                if self.cancel_requested:
                    break

        self._set_state("ANALYZING")
        from safeloop.skills.report import ReportSkill
        self._set_state("REPORTING")
        if self.trajectories:
            self.report = ReportSkill().build(self.run_id, self.plan,
                                              self.trajectories)
            if self.cancel_requested:
                self.report.setdefault("configuration", {})["cancelled"] = True
        os.makedirs("outputs/reports", exist_ok=True)
        path = "outputs/reports/{}_report.json".format(self.run_id)
        if self.report is not None:
            json.dump(self.report, open(path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        self._emit("report_ready", path=path,
                   summary=(self.report or {}).get("overview", {}).get("answer", ""))
        self._set_state("CANCELLED" if self.cancel_requested else "COMPLETED")
        return self.report

    # -------------------------------------------------------------- v1.1
    def _target_fingerprint(self, cfg) -> str:
        """记忆命名空间键：本地含量化方式，API 含 base_url+model。"""
        api = (self.plan.request.api_target or {})
        if api.get("base_url"):
            return "api:{}/{}".format(api.get("base_url"), api.get("model"))
        tq = cfg.get("target", {}) or {}
        return "local:{}@{}".format(tq.get("model_path", "phi"),
                                    tq.get("quantization") or "none")

    def _build_memory(self, cfg):
        """use_memory=True 时用长期记忆库替换 NullMemory（A1）。"""
        if not getattr(self.plan.request, "use_memory", False):
            return build_memory(cfg)
        from safeloop.skills.memory import (MemoryRecord, MemoryStore,
                                            OnlineUtilityEstimator)
        fp = self._target_fingerprint(cfg)
        snap = getattr(self.plan.request, "memory_snapshot_id", None)
        if snap:
            store = MemoryStore.load_snapshot(
                db_path="outputs/memory/memory.db", snapshot_id=snap,
                target_fingerprint=fp)
        else:
            store = MemoryStore(target_fingerprint=fp)
        est = OnlineUtilityEstimator()
        store_ref = {"s": store}

        def _extractor(step, state=None):
            meta = (getattr(step.judge_output, "metadata", None) or {})
            if meta.get("parse_status") == "FAILED" or meta.get("judge_invoked") is False:
                return []
            safety = meta.get("safety")
            refusal = meta.get("refusal")
            if refusal == "Yes":
                outcome = "refusal"
            elif safety == "Unsafe":
                outcome = "unsafe_content"
            elif safety == "Controversial":
                outcome = "mixed"
            elif safety == "Safe":
                outcome = "safe"
            elif meta.get("advancement"):
                outcome = "advancement_{}".format(
                    str(meta.get("advancement")).lower())
            else:
                outcome = "observed"
            history_prompts = [s.action.prompt for s in
                               (getattr(state, "history", None) or [])]
            history_outcomes = [
                (getattr(getattr(s, "judge_output", None), "metadata", None)
                 or {}).get("safety") or
                (getattr(getattr(s, "judge_output", None), "metadata", None)
                 or {}).get("advancement") or ""
                for s in (getattr(state, "history", None) or [])]
            existing = [r.strategy_summary for r in store_ref["s"].query(
                getattr(getattr(state, "task", None), "harm_category", None),
                top_k=5)]
            task = getattr(state, "task", None) or type("T", (), {
                "task_id": "?", "harm_category": "", "goal": "",
                "language": ""})()
            u = est.evaluate(step.action.prompt, history_prompts, meta,
                             history_outcomes, existing)
            return [MemoryRecord(
                source_run_id=self.run_id or "",
                source_task_id=getattr(task, "task_id", ""),
                target_fingerprint=fp,
                harm_category=getattr(task, "harm_category", "") or "",
                language=getattr(task, "language", "") or "",
                strategy=step.action.strategy or "direct",
                strategy_summary="[{}] {}".format(
                    getattr(task, "harm_category", "")[:24],
                    (getattr(task, "goal", "") or "")[:60]),
                context_summary=(step.action.prompt or "")[:120],
                observation_summary="safety={} refusal={} outcome={}".format(
                    safety, refusal,
                    getattr(step.judge_output, "outcome", "") or ""),
                outcome_proxy=outcome,
                quality=u["quality"], novelty=u["novelty"],
                judge_version=str(meta.get("judge", "v2")),
                metadata={"utility": u})]

        store.extractor = _extractor
        return store

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
        os.makedirs("outputs/checkpoints", exist_ok=True)
        ckpt_path = "outputs/checkpoints/{}.json".format(cond)
        memory = self._build_memory(cfg)
        round_selector = None
        adaptive = getattr(self.plan.request, "adaptive_budget", None)
        if adaptive:
            from safeloop.skills.scheduler import AdaptiveScheduler
            sched = AdaptiveScheduler(
                total_budget=int(adaptive),
                per_task_cap=self.plan.request.budget_per_task,
                seed=self.seed)
            round_selector = sched.select
            self._last_scheduler = sched

        def _on_step(step, slot):
            self.live_events.append({
                "branch": br["name"],
                "task_id": slot.task.task_id,
                "round": step.round_id + 1,
                "strategy": step.action.strategy,
                "prompt": step.action.prompt,
                "response": step.response.text,
                "advancement": step.judge_output.metadata.get("advancement"),
                "safety": step.judge_output.metadata.get("safety"),
                "action": (step.feedback.adaptation_action
                           if step.feedback else None),
                "success": bool(step.external_evaluation
                                and step.external_evaluation.success),
            })

        batch = BatchRunner(
            coordinator_factory=coordinator_factory, red_agent=red,
            target=target, judge=judge, memory=memory,
            reward_factory=reward_factory, feedback_builder=fb_builder,
            model_manager=mm, base_seed=self.seed, on_step=_on_step,
            should_cancel=(lambda: self.cancel_requested),
            round_selector=round_selector,
            provenance={"run_id": self.run_id, "branch": br["name"],
                        "feedback_mode": br["mode"], "mode": self.plan.request.mode,
                        "main_agent": self.version, "seed": self.seed,
                        "memory": ("longterm:" + self._target_fingerprint(cfg)
                                   if getattr(self.plan.request, "use_memory", False)
                                   else "null"),
                        "adaptive_budget": adaptive})
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
        trajs = batch.run(
            tasks, {br["name"]: protocol},
            trajectory_store=TrajectoryStore(),
            checkpoint_path=ckpt_path,
            resume=self._resume)[br["name"]]
        self.trajectories[br["name"]] = trajs
        self._emit("branch_completed", branch=br["name"], n=len(trajs),
                   cancelled=batch.cancelled)

    # -------------------------------------------------------------- misc
    def cancel(self) -> None:
        """请求取消（真取消，W0-3）：置 cancel_requested，引擎在轮边界停下。

        READY（未开始）直接 CANCELLED；活动态 → CANCELLING，run() 收尾时置
        CANCELLED。当前正在进行的单次模型调用会完成或超时后才生效（远端请求
        无法撤回，可能已产生费用）。
        """
        self.cancel_requested = True
        if self.state == "READY":
            self._set_state("CANCELLED")
        elif self.state in ("PLANNING", "RUNNING", "CANCELLING", "EVALUATING",
                            "ANALYZING", "REPORTING"):
            if self.state != "CANCELLING":
                self._set_state("CANCELLING")

    def status(self) -> Dict:
        return {"run_id": self.run_id, "state": self.state,
                "cancel_requested": self.cancel_requested,
                "n_events": len(self.events),
                "branches": {k: len(v) for k, v in self.trajectories.items()},
                "report_ready": self.report is not None}
