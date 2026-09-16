# -*- coding: utf-8 -*-
"""实验协议（设计文档 §31）：protocol 与 backend 分离，条件只改 protocol 字段。"""
from dataclasses import dataclass, field
from typing import Any, Dict

# 四级攻击结果（设计文档 §6.3）
OUTCOME_REFUSAL = "REFUSAL"
OUTCOME_PARTIAL_REFUSAL = "PARTIAL_REFUSAL"
OUTCOME_PARTIAL_COMPLIANCE = "PARTIAL_COMPLIANCE"
OUTCOME_FULL_COMPLIANCE = "FULL_COMPLIANCE"
OUTCOMES = (
    OUTCOME_REFUSAL,
    OUTCOME_PARTIAL_REFUSAL,
    OUTCOME_PARTIAL_COMPLIANCE,
    OUTCOME_FULL_COMPLIANCE,
)

# 四级反馈（设计文档 §12）
FEEDBACK_NONE = "none"
FEEDBACK_SCORE = "score"
FEEDBACK_OUTCOME = "outcome"
FEEDBACK_STRUCTURED = "structured"
# C_SR 基线（V0.3 设计 §12）：红方自我反思（keep/refine/switch），Judge 不参与。
# 作为反馈级别变体实现：builder 返回 None（与 none 相同），红方按反思模式渲染指令。
FEEDBACK_SELF_REFLECTION = "self_reflection"
FEEDBACK_LEVELS = (
    FEEDBACK_NONE,
    FEEDBACK_SCORE,
    FEEDBACK_OUTCOME,
    FEEDBACK_STRUCTURED,
    FEEDBACK_SELF_REFLECTION,
)

# 策略 → 策略族（设计文档 §5：分析 ASR(h,z) 的统计基础）
STRATEGY_FAMILIES = {
    "direct": "plain",
    "roleplay": "persona",
    "reframing": "framing",
    "obfuscation": "encoding",
    "multi_turn": "incremental",
}

# Stage 1 固定轮换顺序（协议级常量，写入 provenance 保证可复现）
STRATEGY_ORDER = ["direct", "roleplay", "reframing", "obfuscation", "multi_turn"]

INITIAL_SEED_POLICIES = {
    "fixed_direct": "direct",   # 所有条件第 0 轮使用 direct，保证 p0 完全一致
}


@dataclass
class ExperimentProtocol:
    """一个实验条件的完整协议描述。"""

    experiment_id: str
    condition_id: str
    target_query_budget: int
    feedback_level: str
    allow_target_response_history: bool = True
    memory_enabled: bool = False
    scheduler_type: str = "uniform"
    training_enabled: bool = False
    initial_seed_policy: str = "fixed_direct"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "condition_id": self.condition_id,
            "target_query_budget": self.target_query_budget,
            "feedback_level": self.feedback_level,
            "allow_target_response_history": self.allow_target_response_history,
            "memory_enabled": self.memory_enabled,
            "scheduler_type": self.scheduler_type,
            "training_enabled": self.training_enabled,
            "initial_seed_policy": self.initial_seed_policy,
            "metadata": self.metadata,
        }
