# -*- coding: utf-8 -*-
"""组件工厂 V0.2：从 configs/stage1.yaml 装配闭环（设计文档 §32/§49）。

配置拆成 protocol 与 backend 两层：protocol 描述实验协议（条件的公共部分），
backend 描述模型后端。真实化只改 backend 字段，不改源码。
"""
import os
import random
from typing import Any, Dict, List, Optional

from agents.base_judge import BaseJudge
from agents.base_red_agent import BaseRedAgent
from agents.hf_red_agent import HfRedAgent
from agents.red_agent import TemplateRedAgent
from agents.safety_judge import RuleBasedJudge
from agents.qwen_guard_judge import QwenGuardJudge
from agents.qwen_guard_judge_v2 import Qwen3GuardJudgeV2
from agents.goal_compliance_judge import GoalComplianceJudge
from agents.goal_advancement_judge import GoalAdvancementJudge
from agents.goal_advancement_judge_v3 import GoalAdvancementJudgeV3
from agents.multi_signal_judge import MultiSignalJudge
from agents.task_aware_router import TaskAwareJudgeRouter
from core.coordinator import BaseCoordinator
from core.coordinator_impl import HeuristicCoordinator
from core.protocol import ExperimentProtocol
from core.reward import RewardConfig, RewardFunction
from core.schemas import SafetyTask
from engine.episode_runner import EpisodeRunner
from engine.hf_backend import ModelManager, quantization_spec
from engine.provenance import collect_provenance
from evaluation.base_evaluator import BaseEvaluator
from evaluation.demo_evaluator import DemoEvaluator
from evaluation.offline_evaluator import OfflineEvaluator
from evaluation.strongreject_evaluator import StrongRejectEvaluator
from feedback.feedback_builder import FeedbackBuilder
from memory.base_memory import BaseMemory
from memory.null_memory import NullMemory
from memory.trajectory_store import TrajectoryStore
from scheduler.base_scheduler import BaseScheduler
from scheduler.uniform_scheduler import UniformScheduler
from targets.base_target import BaseTarget
from targets.scripted_target import ScriptedTarget
from targets.hf_target import HfTarget

_DEFAULT_STRATEGIES = ["direct", "roleplay", "reframing", "obfuscation", "multi_turn"]


def build_scheduler(cfg: Dict, rng: random.Random) -> BaseScheduler:
    sched_cfg = cfg.get("scheduler", {}) or {}
    if sched_cfg.get("type", "uniform") == "uniform":
        return UniformScheduler(
            risk_categories=sched_cfg.get(
                "risk_categories", ["违法犯罪", "歧视偏见", "暴力恐怖",
                                    "隐私侵犯", "虚假信息", "色情低俗"]),
            attack_strategies=sched_cfg.get("attack_strategies", _DEFAULT_STRATEGIES),
            rng=rng,
        )
    raise ValueError("unknown scheduler type: {}".format(sched_cfg.get("type")))


def build_red_agent(cfg: Dict, rng: random.Random,
                    model_manager: "ModelManager" = None) -> BaseRedAgent:
    acfg = cfg.get("red_agent", {}) or {}
    backend = acfg.get("backend", "template")
    if backend == "template":
        return TemplateRedAgent(
            rng=rng,
            template_path=acfg.get("template_path", "prompts/red/v1.yaml"),
        )
    if backend == "hf":
        return HfRedAgent(
            model_path=acfg["model_path"],
            model_manager=model_manager,
            template_path=acfg.get("template_path", "prompts/red/real_v1.yaml"),
            dtype=acfg.get("dtype", "float16"),
            device=acfg.get("device", "cuda"),
            do_sample=bool(acfg.get("do_sample", True)),
            temperature=float(acfg.get("temperature", 0.7)),
            top_p=float(acfg.get("top_p", 0.9)),
            max_new_tokens=int(acfg.get("max_new_tokens", 256)),
            rng=rng,
        )
    raise ValueError("unknown red_agent backend: {}".format(backend))


def build_judge(cfg: Dict, model_manager: "ModelManager" = None) -> BaseJudge:
    jcfg = cfg.get("judge", {}) or {}
    backend = jcfg.get("backend", "rule_based")
    if backend == "rule_based":
        return RuleBasedJudge(rules_path=jcfg.get("rules_path", "prompts/judge/v1.yaml"))
    if backend == "qwen3guard_v2":
        return Qwen3GuardJudgeV2(
            model_path=jcfg["model_path"],
            model_manager=model_manager,
            dtype=jcfg.get("dtype", "bfloat16"),
            device=jcfg.get("device", "cuda"),
            max_new_tokens=int(jcfg.get("max_new_tokens", 64)),
        )
    if backend == "goal_compliance":
        # 1B-GC2 后：goal 路 = V3（三级推进信号，控制校准）
        return GoalAdvancementJudgeV3(
            model_path=jcfg["model_path"],
            model_manager=model_manager,
            dtype=jcfg.get("dtype", "bfloat16"),
            device=jcfg.get("device", "cuda"),
            max_new_tokens=int(jcfg.get("max_new_tokens", 64)),
        )
    if backend == "goal_compliance_v2":
        return GoalAdvancementJudge(
            model_path=jcfg["model_path"],
            model_manager=model_manager,
            dtype=jcfg.get("dtype", "bfloat16"),
            device=jcfg.get("device", "cuda"),
            max_new_tokens=int(jcfg.get("max_new_tokens", 96)),
        )
    if backend == "goal_compliance_v1":
        return GoalComplianceJudge(
            model_path=jcfg["model_path"],
            model_manager=model_manager,
            dtype=jcfg.get("dtype", "bfloat16"),
            device=jcfg.get("device", "cuda"),
            max_new_tokens=int(jcfg.get("max_new_tokens", 48)),
        )
    if backend == "routed":
        gcfg = jcfg.get("goal_judge", {}) or {}
        goal_path = gcfg.get("model_path") or (cfg.get("goal_judge", {}) or {}).get("model_path")
        content = Qwen3GuardJudgeV2(
            model_path=jcfg["model_path"], model_manager=None,
            dtype=jcfg.get("dtype", "bfloat16"), device=jcfg.get("device", "cuda"),
            max_new_tokens=int(jcfg.get("max_new_tokens", 64)))
        goal = GoalComplianceJudge(
            model_path=goal_path, model_manager=None,
            dtype=gcfg.get("dtype", jcfg.get("dtype", "bfloat16")),
            device=gcfg.get("device", jcfg.get("device", "cuda")),
            max_new_tokens=int(gcfg.get("max_new_tokens", 48)))
        return TaskAwareJudgeRouter(
            content, goal, model_manager=model_manager,
            mapping_version=(cfg.get("router", {}) or {}).get(
                "mapping_version", "jbb_observability_v1"))
    if backend == "multi_signal":
        mcfg = jcfg.get("content_judge", {}) or {}
        gcfg = jcfg.get("goal_judge", {}) or {}
        content = Qwen3GuardJudgeV2(
            model_path=mcfg["model_path"],
            model_manager=None,   # 由 MultiSignalJudge 统一管理加载
            dtype=mcfg.get("dtype", "bfloat16"),
            device=mcfg.get("device", "cuda"),
            max_new_tokens=int(mcfg.get("max_new_tokens", 64)),
        )
        goal = GoalComplianceJudge(
            model_path=gcfg["model_path"],
            model_manager=None,
            dtype=gcfg.get("dtype", "bfloat16"),
            device=gcfg.get("device", "cuda"),
            max_new_tokens=int(gcfg.get("max_new_tokens", 48)),
        )
        return MultiSignalJudge(content, goal, model_manager=model_manager)
    if backend == "qwen3guard":
        return QwenGuardJudge(
            model_path=jcfg["model_path"],
            model_manager=model_manager,
            template_path=jcfg.get("template_path", "prompts/judge/qwenguard_v1.yaml"),
            dtype=jcfg.get("dtype", "float16"),
            device=jcfg.get("device", "cuda"),
            max_new_tokens=int(jcfg.get("max_new_tokens", 128)),
        )
    raise ValueError("unknown judge backend: {}".format(backend))


def build_target(cfg: Dict, model_manager: "ModelManager" = None) -> BaseTarget:
    tcfg = cfg.get("target", {}) or {}
    backend = tcfg.get("backend", "scripted")
    if backend == "api":
        # 黑盒 API Target（openai_chat / anthropic / openai_responses）
        from targets.api_target import build_api_target
        return build_api_target(tcfg)
    if backend == "scripted":
        return ScriptedTarget(model_name=tcfg.get("model_name", "scripted-demo-1"))
    if backend == "hf":
        return HfTarget(
            model_path=tcfg["model_path"],
            model_manager=model_manager,
            dtype=tcfg.get("dtype", "float16"),
            device=tcfg.get("device", "cuda"),
            do_sample=bool(tcfg.get("do_sample", False)),
            max_new_tokens=int(tcfg.get("max_new_tokens", 512)),
            temperature=float(tcfg.get("temperature", 1.0)),
            top_p=float(tcfg.get("top_p", 1.0)),
            quantization=quantization_spec(
                tcfg.get("quantization"), tcfg.get("compute_dtype", "bfloat16")),
        )
    raise ValueError("unknown target backend: {}".format(backend))


def build_evaluator(cfg: Dict, model_manager: "ModelManager" = None) -> BaseEvaluator:
    ecfg = cfg.get("evaluator", {}) or {}
    backend = ecfg.get("backend", "demo")
    if backend == "demo":
        return DemoEvaluator()
    if backend == "strongreject_ft":
        return StrongRejectEvaluator(
            model_path=ecfg["model_path"],
            base_model_path=ecfg.get("base_model_path"),
            model_manager=model_manager,
            dtype=ecfg.get("dtype", "bfloat16"),
            device=ecfg.get("device", "cuda"),
            success_threshold=float(ecfg.get("success_threshold", 0.5)),
        )
    raise ValueError("unknown evaluator backend: {}".format(backend))


def build_memory(cfg: Dict) -> BaseMemory:
    if (cfg.get("memory", {}) or {}).get("enabled", False):
        raise NotImplementedError("真实 Attack Memory 在 Stage 2 接入")
    return NullMemory()


def build_backends_info(cfg: Dict, red: BaseRedAgent, target: BaseTarget,
                        judge: BaseJudge, evaluator: BaseEvaluator) -> Dict[str, Dict]:
    return {
        "red": {"backend": red.name, "template_version": red.template_version},
        "target": {"backend": target.name, "model": getattr(target, "model_name", "")},
        "judge": {"backend": judge.name, "version": judge.version},
        "evaluator": {"backend": evaluator.name,
                      "version": getattr(evaluator, "version", "")},
    }


def load_tasks(cfg: Dict, base_dir: str = ".") -> List[SafetyTask]:
    tasks_file = (cfg.get("experiment", {}) or {}).get(
        "tasks_file", "data/tasks/test.jsonl")
    path = tasks_file if os.path.isabs(tasks_file) else os.path.join(base_dir, tasks_file)
    tasks: List[SafetyTask] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                import json
                tasks.append(SafetyTask.from_dict(json.loads(line)))
    return tasks


class RunnerBundle:
    """按条件装配好的全套组件（共享后端实例，条件间严格同源）。"""

    def __init__(self, cfg: Dict, config_path: str = "configs/stage1.yaml") -> None:
        self.cfg = cfg
        self.config_path = config_path
        self.seed = (cfg.get("experiment", {}) or {}).get("seed", 42)
        self.model_manager = ModelManager()
        self.red_agent = build_red_agent(cfg, random.Random(self.seed),
                                         self.model_manager)
        self.target = build_target(cfg, self.model_manager)
        self.judge = build_judge(cfg, self.model_manager)
        self.evaluator = build_evaluator(cfg, self.model_manager)
        self.memory = build_memory(cfg)
        # V0.3-J：feedback.builder: v2（证据驱动 KEEP/REFINE/SWITCH/UNCERTAIN）
        if (cfg.get("feedback", {}) or {}).get("builder") == "v2":
            from feedback.feedback_builder_v2 import FeedbackBuilderV2
            self.feedback_builder = FeedbackBuilderV2()
        else:
            self.feedback_builder = FeedbackBuilder()
        self.reward_config = RewardConfig(**(cfg.get("reward", {}) or {}))
        self.provenance = collect_provenance(
            config_path, cfg, self.red_agent, self.target, self.judge, self.evaluator,
        )
        self.provenance["model_paths"] = {
            "red": (cfg.get("red_agent", {}) or {}).get("model_path"),
            "target": (cfg.get("target", {}) or {}).get("model_path"),
            "judge": (cfg.get("judge", {}) or {}).get("model_path"),
            "evaluator": (cfg.get("evaluator", {}) or {}).get("model_path"),
        }
        # 量化/精度策略入 provenance（设计：所有条件使用同一量化 Target，
        # 只需记录清楚，不破坏研究设计）
        tcfg = cfg.get("target", {}) or {}
        self.provenance["quantization"] = {
            "hardware": (cfg.get("hardware", {}) or {}),
            "red": {"dtype": (cfg.get("red_agent", {}) or {}).get("dtype")},
            "target": {
                "quantization": quantization_spec(
                    tcfg.get("quantization"), tcfg.get("compute_dtype", "bfloat16")),
                "dtype": tcfg.get("dtype"),
            },
            "judge": {"dtype": (cfg.get("judge", {}) or {}).get("dtype")},
            "evaluator": {"dtype": (cfg.get("evaluator", {}) or {}).get("dtype")},
        }
        self.backends_info = build_backends_info(
            cfg, self.red_agent, self.target, self.judge, self.evaluator)

    def make_coordinator(self, protocol: ExperimentProtocol) -> BaseCoordinator:
        return HeuristicCoordinator(build_scheduler(self.cfg, random.Random(self.seed)))

    def make_reward_fn(self, budget: int) -> RewardFunction:
        return RewardFunction(self.reward_config, budget)

    def make_protocol(self, condition_id: str, condition_cfg: Dict[str, Any],
                      experiment_id: str) -> ExperimentProtocol:
        proto_cfg = self.cfg.get("protocol", {}) or {}
        return ExperimentProtocol(
            experiment_id=experiment_id,
            condition_id=condition_id,
            target_query_budget=int(condition_cfg.get(
                "target_query_budget", proto_cfg.get("target_query_budget", 5))),
            feedback_level=condition_cfg["feedback_level"],
            allow_target_response_history=bool(
                proto_cfg.get("allow_target_response_history", True)),
            memory_enabled=bool(proto_cfg.get("memory_enabled", False)),
            scheduler_type=proto_cfg.get("scheduler", "uniform"),
            training_enabled=bool(proto_cfg.get("training_enabled", False)),
            initial_seed_policy=proto_cfg.get("initial_seed_policy", "fixed_direct"),
        )

    def make_runner(self, protocol: ExperimentProtocol,
                    save_trajectory: bool = True) -> EpisodeRunner:
        # 每个条件独立同种子 RNG，保证同起点；协调器按协议初始化
        scheduler = build_scheduler(self.cfg, random.Random(self.seed))
        coordinator: BaseCoordinator = HeuristicCoordinator(scheduler)
        reward_fn = RewardFunction(self.reward_config, protocol.target_query_budget)
        return EpisodeRunner(
            coordinator=coordinator,
            red_agent=self.red_agent,
            target=self.target,
            judge=self.judge,
            memory=self.memory,
            reward_fn=reward_fn,
            feedback_builder=self.feedback_builder,
            trajectory_store=TrajectoryStore() if save_trajectory else None,
            provenance=self.provenance,
            experiment_name="{}_{}".format(
                (self.cfg.get("experiment", {}) or {}).get("name", "exp"),
                protocol.condition_id),
        )

    def make_offline_evaluator(self) -> OfflineEvaluator:
        return OfflineEvaluator(evaluator=self.evaluator)
