# -*- coding: utf-8 -*-
"""在线经验效用估计（roadmap A2）：记忆排序信号——不是攻击成功标签。

q(m) = w1·新颖性 + w2·观察信息量 + w3·与已有记忆的差异度
全部来自在线可见状态（prompt 历史、裁判输出结构），独立评估器（StrongREJECT）
的结果永不进入本估计（红线 1）。
"""
from typing import Dict, List, Optional

from core.reward import _char_ngrams, cosine_similarity


def _sim(a: str, b: str) -> float:
    return cosine_similarity(_char_ngrams(a, n=3), _char_ngrams(b, n=3))


class OnlineUtilityEstimator:
    """复用 core.reward 的三元字符 n-gram 相似度（R_novelty 同源实现）。"""

    def __init__(self, w_novelty=0.5, w_info=0.3, w_divergence=0.2) -> None:
        self.w = (w_novelty, w_info, w_divergence)

    # ------------------------------------------------------------------ 分量
    @staticmethod
    def novelty(prompt: str, history_prompts: List[str]) -> float:
        """与当前轨迹历史 prompt 的最大相似度 → 1-sim（与 R_novelty 同式）。"""
        if not history_prompts:
            return 1.0
        return 1.0 - max(_sim(prompt, p) for p in history_prompts)

    @staticmethod
    def info_content(judge_metadata: Optional[Dict],
                     history_outcomes: List[str]) -> float:
        """观察信息量：解析成功 + 出现轨迹内新 outcome + 类别信号齐全。"""
        if not judge_metadata:
            return 0.3
        score = 0.0
        if judge_metadata.get("parse_status") != "FAILED":
            score += 0.4
        outcome = (judge_metadata.get("safety")
                   or judge_metadata.get("advancement") or "")
        if outcome and outcome not in history_outcomes:
            score += 0.4
        if judge_metadata.get("safety") and judge_metadata.get("refusal") is not None:
            score += 0.2
        return min(1.0, score)

    @staticmethod
    def divergence(strategy_summary: str,
                   existing_summaries: List[str]) -> float:
        """与已有同类记忆的差异度（1 - 最大相似）。"""
        if not existing_summaries:
            return 1.0
        return 1.0 - max(_sim(strategy_summary, s) for s in existing_summaries)

    # ------------------------------------------------------------------ 总分
    def evaluate(self, prompt: str, history_prompts: List[str],
                 judge_metadata: Optional[Dict],
                 history_outcomes: List[str],
                 existing_summaries: Optional[List[str]] = None) -> Dict:
        n = self.novelty(prompt, history_prompts)
        i = self.info_content(judge_metadata, history_outcomes)
        d = self.divergence(prompt, existing_summaries or [])
        w1, w2, w3 = self.w
        return {"quality": round(w1 * n + w2 * i + w3 * d, 4),
                "novelty": round(n, 4), "info": round(i, 4),
                "divergence": round(d, 4)}
