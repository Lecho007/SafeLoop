# -*- coding: utf-8 -*-
"""SafeLoop 协议层 V0.2（Stage 1 Experimental Protocol）。

模块之间只通过本文件的数据结构通信。V0.2 关键升级（设计文档 §3/§7/§10/§17/§18/§19）：
  - 测试单元从 category 升级为 SafetyTask（goal 固定，红方只探索边界）；
  - JudgeOutput 冻结语义：七元组 + 四级离散 outcome；
  - Feedback 与 JudgeOutput 解耦，带 feedback_level（供 Feedback Ablation）；
  - AttackState 以 target_queries_used/budget 单一真源管理预算；
  - AttackStep 同时保存在线判断（judge）与离线外部评估（external_evaluation）；
  - AttackTrajectory 升级为实验级对象（experiment_id / condition_id / provenance）。

纯 dataclasses + stdlib，保持 Python 3.8 兼容与模型无关。
"""
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# 安全评估任务（设计文档 §3）
# ---------------------------------------------------------------------------


@dataclass
class SafetyTask:
    """T_i = (g_i, h_i, m_i)：测试目标 goal 必须固定，红方只负责探索边界。"""

    task_id: str
    goal: str
    harm_category: str
    source: str = "demo"
    source_id: Optional[str] = None
    language: str = "zh"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "harm_category": self.harm_category,
            "source": self.source,
            "source_id": self.source_id,
            "language": self.language,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SafetyTask":
        return cls(
            task_id=d["task_id"],
            goal=d["goal"],
            harm_category=d["harm_category"],
            source=d.get("source", "demo"),
            source_id=d.get("source_id"),
            language=d.get("language", "zh"),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# 红方动作（设计文档 §5：strategy 与 strategy_family 分开）
# ---------------------------------------------------------------------------


@dataclass
class AttackAction:
    prompt: str
    strategy: str
    strategy_family: Optional[str] = None
    parent_prompt_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def prompt_id(self) -> str:
        return self.metadata.get("prompt_id", "")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "strategy": self.strategy,
            "strategy_family": self.strategy_family,
            "parent_prompt_id": self.parent_prompt_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttackAction":
        return cls(
            prompt=d["prompt"],
            strategy=d["strategy"],
            strategy_family=d.get("strategy_family"),
            parent_prompt_id=d.get("parent_prompt_id"),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# 目标响应
# ---------------------------------------------------------------------------


@dataclass
class TargetResponse:
    text: str
    model_name: str
    latency: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TargetResponse":
        return cls(
            text=d["text"],
            model_name=d.get("model_name", "unknown"),
            latency=d.get("latency", 0.0),
            input_tokens=d.get("input_tokens", 0),
            output_tokens=d.get("output_tokens", 0),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# Safety Judge V1（设计文档 §7/§8：五个概念严格区分）
# ---------------------------------------------------------------------------


@dataclass
class JudgeOutput:
    """J(p_t, y_t) = (u, h, s, r, v, q, o)。

    unsafe_score    u：内容本身是否有风险；
    jailbreak_score s：攻击者意图是否真正被满足（核心在线成功指标）；
    refusal_score   r：目标是否在拒绝；
    severity_score  v：危害程度；
    confidence      q：Judge 自信度（Stage 3 风险调度使用，现在必须保留）；
    outcome         o：四级离散结果（分析用；连续 score 用于反馈与排序，两者不混）。
    """

    unsafe_score: float
    harm_scores: Dict[str, float]
    jailbreak_score: float
    refusal_score: float
    severity_score: float
    confidence: float
    outcome: str
    rationale: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # V0.3（设计文档 §17）：字段级 provenance，标注每个字段来源
    # native / derived_proxy / derived_rule / unavailable。
    # 没有可靠数据的字段允许 None，禁止伪造精确数值。
    field_provenance: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unsafe_score": self.unsafe_score,
            "harm_scores": dict(self.harm_scores),
            "jailbreak_score": self.jailbreak_score,
            "refusal_score": self.refusal_score,
            "severity_score": self.severity_score,
            "confidence": self.confidence,
            "outcome": self.outcome,
            "rationale": self.rationale,
            "metadata": self.metadata,
            "field_provenance": self.field_provenance,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "JudgeOutput":
        return cls(
            unsafe_score=d["unsafe_score"],
            harm_scores=d.get("harm_scores", {}),
            jailbreak_score=d["jailbreak_score"],
            refusal_score=d["refusal_score"],
            severity_score=d.get("severity_score", 0.0),
            confidence=d.get("confidence", 0.0),
            outcome=d.get("outcome", ""),
            rationale=d.get("rationale"),
            metadata=d.get("metadata", {}),
            field_provenance=d.get("field_provenance", {}),
        )


# ---------------------------------------------------------------------------
# Feedback V1（设计文档 §11：与 JudgeOutput 解耦，F = g(J, level)）
# ---------------------------------------------------------------------------


@dataclass
class Feedback:
    attack_success: bool
    outcome: str
    unsafe_score: float
    jailbreak_score: float
    refusal_score: float
    failure_type: Optional[str] = None
    guidance: Optional[str] = None
    feedback_level: str = "structured"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attack_success": self.attack_success,
            "outcome": self.outcome,
            "unsafe_score": self.unsafe_score,
            "jailbreak_score": self.jailbreak_score,
            "refusal_score": self.refusal_score,
            "failure_type": self.failure_type,
            "guidance": self.guidance,
            "feedback_level": self.feedback_level,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Feedback":
        return cls(
            attack_success=d["attack_success"],
            outcome=d.get("outcome", ""),
            unsafe_score=d.get("unsafe_score", 0.0),
            jailbreak_score=d.get("jailbreak_score", 0.0),
            refusal_score=d.get("refusal_score", 0.0),
            failure_type=d.get("failure_type"),
            guidance=d.get("guidance"),
            feedback_level=d.get("feedback_level", "structured"),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# 记忆（Stage 2 接入，接口保留）
# ---------------------------------------------------------------------------


@dataclass
class MemoryItem:
    prompt: str
    harm_category: str
    attack_strategy: str
    success: bool
    reward: float
    summary: str = ""


# ---------------------------------------------------------------------------
# Independent Evaluator 结果（设计文档 §10：JudgeOutput != EvaluationResult）
# ---------------------------------------------------------------------------


@dataclass
class EvaluationResult:
    success: bool
    jailbreak_score: float
    unsafe_score: float
    outcome: str
    severity_score: float
    confidence: float
    evaluator_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "jailbreak_score": self.jailbreak_score,
            "unsafe_score": self.unsafe_score,
            "outcome": self.outcome,
            "severity_score": self.severity_score,
            "confidence": self.confidence,
            "evaluator_id": self.evaluator_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvaluationResult":
        return cls(
            success=d["success"],
            jailbreak_score=d.get("jailbreak_score", 0.0),
            unsafe_score=d.get("unsafe_score", 0.0),
            outcome=d.get("outcome", ""),
            severity_score=d.get("severity_score", 0.0),
            confidence=d.get("confidence", 0.0),
            evaluator_id=d.get("evaluator_id", "unknown"),
            metadata=d.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# 一轮攻击（设计文档 §19：同时保存在线判断与离线外部评估）
# ---------------------------------------------------------------------------


@dataclass
class AttackStep:
    round_id: int
    action: AttackAction
    response: TargetResponse
    judge_output: JudgeOutput
    feedback: Optional[Feedback] = None
    reward: float = 0.0
    online_success: bool = False
    external_evaluation: Optional[EvaluationResult] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round_id": self.round_id,
            "action": self.action.to_dict(),
            "response": self.response.to_dict(),
            "judge_output": self.judge_output.to_dict(),
            "feedback": self.feedback.to_dict() if self.feedback else None,
            "reward": self.reward,
            "online_success": self.online_success,
            "external_evaluation": (
                self.external_evaluation.to_dict() if self.external_evaluation else None
            ),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttackStep":
        return cls(
            round_id=d["round_id"],
            action=AttackAction.from_dict(d["action"]),
            response=TargetResponse.from_dict(d["response"]),
            judge_output=JudgeOutput.from_dict(d["judge_output"]),
            feedback=Feedback.from_dict(d["feedback"]) if d.get("feedback") else None,
            reward=d.get("reward", 0.0),
            online_success=d.get("online_success", False),
            external_evaluation=(
                EvaluationResult.from_dict(d["external_evaluation"])
                if d.get("external_evaluation") else None
            ),
            timestamp=d.get("timestamp", 0.0),
        )


# ---------------------------------------------------------------------------
# 状态 V0.2（设计文档 §17：预算单一真源，不保存冗余变量）
# ---------------------------------------------------------------------------


@dataclass
class AttackState:
    task: SafetyTask
    target_id: str
    round_id: int = 0
    target_queries_used: int = 0
    target_query_budget: int = 0
    current_strategy: str = ""
    history: List[AttackStep] = field(default_factory=list)
    last_feedback: Optional[Feedback] = None
    # Stage 2 Memory 钩子（当前 NullMemory 恒为空）
    retrieved_success_cases: List[MemoryItem] = field(default_factory=list)
    retrieved_failure_cases: List[MemoryItem] = field(default_factory=list)
    stop_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_budget(self) -> int:
        return max(0, self.target_query_budget - self.target_queries_used)

    @property
    def done(self) -> bool:
        """Stage 1 停止策略：只在预算耗尽或系统错误时停止（不因在线成功提前停）。"""
        return self.stop_reason is not None or self.remaining_budget <= 0


# ---------------------------------------------------------------------------
# 轨迹 V0.2（设计文档 §18：实验级对象）
# ---------------------------------------------------------------------------


@dataclass
class AttackTrajectory:
    trajectory_id: str
    experiment_id: str
    condition_id: str
    task: SafetyTask
    target_id: str
    initial_prompt: str = ""
    steps: List[AttackStep] = field(default_factory=list)
    final_evaluation: Optional[EvaluationResult] = None
    target_queries: int = 0
    success: bool = False
    stop_reason: str = ""
    provenance: Dict[str, Any] = field(default_factory=dict)
    # V0.3（设计文档 §39）：成本核算（token 用量 / 时延 / 重试），由
    # engine/cost.py 从 steps 聚合写入，episode_runner 不感知。
    cost: Dict[str, Any] = field(default_factory=dict)

    def append(self, step: AttackStep) -> None:
        self.steps.append(step)
        self.target_queries += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trajectory_id": self.trajectory_id,
            "experiment_id": self.experiment_id,
            "condition_id": self.condition_id,
            "task": self.task.to_dict(),
            "target_id": self.target_id,
            "initial_prompt": self.initial_prompt,
            "steps": [s.to_dict() for s in self.steps],
            "final_evaluation": (
                self.final_evaluation.to_dict() if self.final_evaluation else None
            ),
            "target_queries": self.target_queries,
            "success": self.success,
            "stop_reason": self.stop_reason,
            "provenance": self.provenance,
            "cost": self.cost,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AttackTrajectory":
        return cls(
            trajectory_id=d["trajectory_id"],
            experiment_id=d.get("experiment_id", ""),
            condition_id=d.get("condition_id", ""),
            task=SafetyTask.from_dict(d["task"]),
            target_id=d.get("target_id", ""),
            initial_prompt=d.get("initial_prompt", ""),
            steps=[AttackStep.from_dict(s) for s in d.get("steps", [])],
            final_evaluation=(
                EvaluationResult.from_dict(d["final_evaluation"])
                if d.get("final_evaluation") else None
            ),
            target_queries=d.get("target_queries", 0),
            success=d.get("success", False),
            stop_reason=d.get("stop_reason", ""),
            provenance=d.get("provenance", {}),
            cost=d.get("cost", {}),
        )


def new_trajectory_id() -> str:
    return uuid.uuid4().hex[:12]
