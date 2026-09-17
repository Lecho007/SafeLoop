# -*- coding: utf-8 -*-
"""HfRedAgent（backend: hf，Qwen3-4B，V0.3 设计 §2/§11/§13）。

- 按反馈级别渲染上下文（none/self_reflection/score/outcome/structured）；
- 输出 STRICT JSON {strategy, prompt}，解析失败重试 1 次（retry 记入 usage）；
- 第 0 轮强制 greedy 且不带 history/feedback —— 保证所有条件 p0 完全一致（§13）；
- Judge 只在 feedback 块中提示策略维度，攻击文本由本模型生成（硬约束 §11）。
torch/transformers 懒加载；显式加载经 ModelManager 分时管理。
"""
import json
import logging
import random
import re
import uuid
from typing import Any, Dict, Optional

import yaml

from agents.base_red_agent import BaseRedAgent
from core.protocol import (
    FEEDBACK_NONE,
    FEEDBACK_SCORE,
    FEEDBACK_SELF_REFLECTION,
    FEEDBACK_STRUCTURED,
    STRATEGY_FAMILIES,
    STRATEGY_ORDER,
)
from core.schemas import AttackAction, AttackState

DEFAULT_TEMPLATE_PATH = "prompts/red/real_v1.yaml"

logger = logging.getLogger("safeloop.red")

_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)  # 扁平对象，抗 <think> 等噪声


def parse_red_json(text: str) -> Dict[str, str]:
    """容错解析红方 JSON 输出；失败 raise ValueError。"""
    payload = None
    stripped = text.strip()
    # 去掉 markdown 代码围栏
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    for cand in _JSON_RE.findall(stripped) + _JSON_RE.findall(text):
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("prompt"):
            payload = obj
            break
    if payload is None:
        # 兜底 1：字段级正则（容忍缺逗号/多余文本）
        m = re.search(
            r'"strategy"\s*:\s*"([^"]+)"[\s,]*"prompt"\s*:\s*"(.+)"\s*\}?',
            stripped, re.DOTALL)
        if m:
            payload = {"strategy": m.group(1), "prompt": m.group(2)}
    if payload is None:
        # 兜底 2：极宽容提取——实测 Qwen3-1.7B 会输出 "prompt"> ...（冒号误写为 >，
        # JSON 未闭合）。strategy 取字段后的词，prompt 取到文本末尾。
        ms = re.search(r'"strategy"\s*[:>]\s*"?([A-Za-z_]+)', stripped)
        mp = re.search(r'"prompt"\s*[:>]\s*"?(.+?)\s*"?\s*\}?\s*$', stripped, re.DOTALL)
        if ms and mp:
            payload = {"strategy": ms.group(1), "prompt": mp.group(1).rstrip().rstrip("}")}
    if payload is None:
        logger.warning("red JSON parse failed, raw output: %.800s", text)
        raise ValueError("cannot parse red output as JSON")
    strategy = str(payload.get("strategy", "")).strip()
    prompt = str(payload.get("prompt", "")).strip()
    if not prompt:
        logger.warning("red JSON has empty prompt, raw output: %.800s", text)
        raise ValueError("empty prompt in red output")
    if strategy not in STRATEGY_ORDER:
        strategy = "direct" if not strategy else strategy
    return {"strategy": strategy, "prompt": prompt}


class HfRedAgent(BaseRedAgent):
    name = "hf"
    template_version = "unknown"

    def __init__(
        self,
        model_path: str,
        model_manager=None,
        template_path: str = DEFAULT_TEMPLATE_PATH,
        dtype: str = "float16",
        device: str = "cuda",
        do_sample: bool = True,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_new_tokens: int = 256,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.model_path = model_path
        self.manager = model_manager
        self.dtype = dtype
        self.device = device
        self.do_sample = do_sample
        self.temperature = temperature
        self.top_p = top_p
        self.max_new_tokens = max_new_tokens
        self.rng = rng or random.Random()
        self._model = None
        self._tokenizer = None
        with open(template_path, "r", encoding="utf-8") as f:
            self.tpl = yaml.safe_load(f)
        self.template_version = self.tpl.get("version", "red-real-unknown")

    # ------------------------------------------------------------------ model
    def _ensure_loaded(self) -> None:
        if self._model is not None:
            if self.manager is not None:
                self.manager.acquire("red", lambda: None)
            return

        def _load():
            from engine.hf_backend import load_causal_lm
            self._model, self._tokenizer = load_causal_lm(
                self.model_path, dtype=self.dtype, device=self.device)

        if self.manager is not None:
            self.manager.acquire("red", _load)
            self.manager.register_unloader(self._unload)
        else:
            _load()

    def _unload(self) -> None:
        self._model = None
        self._tokenizer = None

    # ------------------------------------------------------------------ render
    def _history_block(self, state: AttackState) -> str:
        if not state.history:
            return self.tpl["history_empty"]
        max_rounds = int(self.tpl.get("history_max_rounds", 2))
        max_chars = int(self.tpl.get("response_max_chars", 600))
        lines = []
        for s in state.history[-max_rounds:]:
            resp = s.response.text[:max_chars] + (
                "..." if len(s.response.text) > max_chars else "")
            lines.append(self.tpl["history_item"].format(
                round=s.round_id, strategy=s.action.strategy,
                prompt=s.action.prompt, response=resp))
        return "\n".join(lines)

    def _feedback_block(self, state: AttackState, level: str) -> str:
        fb = state.last_feedback
        if level == FEEDBACK_SELF_REFLECTION:
            return self.tpl["feedback_self_reflection"]
        if fb is None:
            return self.tpl["feedback_none"]
        if level == FEEDBACK_SCORE:
            scores = "unsafe={:.2f}, jailbreak={:.2f}, refusal={:.2f}".format(
                fb.unsafe_score, fb.jailbreak_score, fb.refusal_score)
            return self.tpl["feedback_score"].format(scores=scores)
        return self.tpl["feedback_structured"].format(
            outcome=fb.outcome or "N/A",
            failure_type=fb.failure_type or "none",
            guidance=fb.guidance or "N/A",
            adaptation_action=fb.adaptation_action or "N/A")

    def _messages(self, state: AttackState, level: str) -> list:
        user = self.tpl["user_template"].format(
            goal=state.task.goal,
            strategy_order=", ".join(STRATEGY_ORDER),
            current_strategy=state.current_strategy or "direct",
            history_block=self._history_block(state),
            feedback_block=self._feedback_block(state, level),
        )
        return [
            {"role": "system", "content": self.tpl["system"]},
            {"role": "user", "content": user},
        ]

    # ------------------------------------------------------------------ api
    def generate(self, state: AttackState, feedback_level: str = "none") -> AttackAction:
        self._ensure_loaded()
        if self.manager is not None:
            self.manager.bump("red")

        messages = self._messages(state, feedback_level)
        round0 = not state.history
        # 协议 invariant（§13）：第 0 轮贪心且上下文相同 → 所有条件 p0 一致
        do_sample = self.do_sample and not round0

        from engine.hf_backend import chat_generate
        retries = 0
        retry_reason = None
        result = chat_generate(
            self._model, self._tokenizer, messages,
            max_new_tokens=self.max_new_tokens,
            do_sample=do_sample,
            temperature=self.temperature, top_p=self.top_p,
            device=self.device,
            template_kwargs={"enable_thinking": False})  # Qwen3 关闭思考模式
        try:
            parsed = parse_red_json(result["text"])
        except Exception as exc:  # 解析失败重试一次（§21 retry 不增加 Target query）
            retries = 1
            retry_reason = "json_parse: {}".format(exc)
            result = chat_generate(
                self._model, self._tokenizer, messages,
                max_new_tokens=self.max_new_tokens, do_sample=do_sample,
                temperature=self.temperature, top_p=self.top_p,
                device=self.device,
                template_kwargs={"enable_thinking": False})
            parsed = parse_red_json(result["text"])

        prev_strategy = (
            state.history[-1].action.strategy if state.history
            else state.current_strategy)
        return AttackAction(
            prompt=parsed["prompt"],
            strategy=parsed["strategy"],
            strategy_family=STRATEGY_FAMILIES.get(parsed["strategy"]),
            parent_prompt_id=state.history[-1].action.prompt_id if state.history else None,
            metadata={
                "prompt_id": uuid.uuid4().hex[:10],
                "template_version": self.template_version,
                "feedback_level": feedback_level,
                "feedback_used": state.last_feedback is not None,
                "strategy_changed": parsed["strategy"] != prev_strategy,
                "round_id": state.round_id,
                "usage": {
                    "input_tokens": result["input_tokens"],
                    "output_tokens": result["output_tokens"],
                    "retries": retries,
                    "retry_reason": retry_reason,
                },
            },
        )
