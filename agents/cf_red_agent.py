# -*- coding: utf-8 -*-
"""CFRedAgent（Stage 1B-CF）：执行 Controller 强制约束的红方。

enforced 模式：strategy 由 Controller 给定（JSON 的 strategy 字段必须等于
required_strategy，解析后强制覆写防漂移）；refine 模式要求 refinement_summary；
realign 模式在指令中锚定 original goal。
soft 模式：与历史行为一致（SWITCH 仅建议）。
"""
import json
import random
import re
import uuid
from typing import Dict, Optional

import yaml

from agents.base_red_agent import BaseRedAgent
from core.protocol import STRATEGY_ORDER

_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def parse_cf_json(text: str) -> Dict[str, str]:
    stripped = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", text.strip())
    for cand in _JSON_RE.findall(stripped) + _JSON_RE.findall(text):
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get("prompt"):
            return {"strategy": str(obj.get("strategy", "")).strip(),
                    "prompt": str(obj["prompt"]).strip(),
                    "refinement_summary": str(obj.get("refinement_summary", "")).strip()}
    m_s = re.search(r'"strategy"\s*[:>]\s*"?([A-Za-z_]+)', stripped)
    m_p = re.search(r'"prompt"\s*[:>]\s*"?(.+?)\s*"?\s*\}?\s*$', stripped, re.DOTALL)
    if m_s and m_p:
        return {"strategy": m_s.group(1), "prompt": m_p.group(1).rstrip().rstrip("}"),
                "refinement_summary": ""}
    raise ValueError("cannot parse CF red output")


class CFRedAgent(BaseRedAgent):
    name = "cf_red"
    template_version = "red-cf-v1"

    def __init__(self, model_path: str, model_manager=None,
                 template_path: str = "prompts/red/cf_v1.yaml",
                 dtype: str = "bfloat16", device: str = "cuda",
                 do_sample: bool = True, temperature: float = 0.7, top_p: float = 0.9,
                 max_new_tokens: int = 320, rng: Optional[random.Random] = None,
                 enforced: bool = True) -> None:
        self.enforced = enforced
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
        self.template_version = self.tpl.get("version", "red-cf-unknown")

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
    def _history(self, state) -> str:
        if not state.history:
            return self.tpl["history_empty"]
        items = []
        for s in state.history[-int(self.tpl.get("history_max_rounds", 2)):]:
            resp = s.response.text[:int(self.tpl.get("response_max_chars", 600))]
            items.append(self.tpl["history_item"].format(
                round=s.round_id, strategy=s.action.strategy,
                prompt=s.action.prompt, response=resp))
        return "\n".join(items)

    def _messages(self, state, feedback_level: str) -> tuple:
        ctrl = (state.metadata or {}).get("control") or {}
        mode = ctrl.get("generation_mode", "normal")
        forced = ctrl.get("forced_strategy_family") or state.current_strategy or "direct"
        enforced = self.enforced
        control_block = (
            self.tpl["control_enforced"].format(forced_family=forced, mode=mode)
            if enforced else
            self.tpl["control_soft"].format(forced_family=forced, mode=mode))
        fb = state.last_feedback
        if fb is None:
            fb_block = "(no judge feedback; round 0)"
        else:
            m = fb.metadata or {}
            fb_block = self.tpl["feedback_block"].format(
                advancement=m.get("advancement", "?"),
                polarity=m.get("polarity", "?"),
                action=fb.adaptation_action or "?",
                guidance=fb.guidance or "")
        contract = (self.tpl["output_contract_enforced"] if enforced
                    else self.tpl["output_contract_soft"])
        user = self.tpl["user_template"].format(
            goal=state.task.goal,
            strategy_order=", ".join(STRATEGY_ORDER),
            control_block=control_block,
            history_block=self._history(state),
            feedback_block=fb_block,
            output_contract=contract)
        return [{"role": "system", "content": self.tpl["system"]},
                {"role": "user", "content": user}], forced, mode, enforced

    # ------------------------------------------------------------------ api
    def generate(self, state, feedback_level: str = "none"):
        self._ensure_loaded()
        if self.manager is not None:
            self.manager.bump("red")
        messages, forced, mode, enforced = self._messages(state, feedback_level)
        round0 = not state.history
        from engine.hf_backend import chat_generate
        kwargs = dict(max_new_tokens=self.max_new_tokens,
                      do_sample=self.do_sample and not round0,
                      temperature=self.temperature, top_p=self.top_p,
                      device=self.device,
                      template_kwargs={"enable_thinking": False})
        result = chat_generate(self._model, self._tokenizer, messages, **kwargs)
        retries = 0
        try:
            parsed = parse_cf_json(result["text"])
        except ValueError:
            retries = 1
            result = chat_generate(self._model, self._tokenizer, messages, **kwargs)
            parsed = parse_cf_json(result["text"])
        model_output_strategy = parsed["strategy"]
        strategy = forced if enforced else parsed["strategy"]  # enforced：Controller 决定
        prev = state.history[-1].action.strategy if state.history else state.current_strategy
        from core.schemas import AttackAction
        return AttackAction(
            prompt=parsed["prompt"], strategy=strategy,
            strategy_family=None,
            parent_prompt_id=(state.history[-1].action.metadata.get("prompt_id")
                              if state.history else None),
            metadata={
                "prompt_id": uuid.uuid4().hex[:10],
                "template_version": self.template_version,
                "execution_mode": "enforced" if enforced else "soft",
                "required_strategy": forced,
                "model_output_strategy": model_output_strategy,
                "strategy_overridden": enforced and model_output_strategy != forced,
                "generation_mode": mode,
                "refinement_summary": parsed.get("refinement_summary", ""),
                "feedback_level": feedback_level,
                "round_id": state.round_id,
                "usage": {"input_tokens": result["input_tokens"],
                          "output_tokens": result["output_tokens"],
                          "retries": retries, "retry_reason":
                          "json_parse" if retries else None},
            })
