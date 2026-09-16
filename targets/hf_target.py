# -*- coding: utf-8 -*-
"""HfTarget（backend: hf，V100: Mistral-7B FP16 / RTX4060: Phi-3.5-mini 4-bit NF4）。

- chat template 生成；默认贪心（do_sample=false）、max_new_tokens=512；
- 8GB 档 Target 走 4-bit NF4（quantization/compute_dtype 记入响应与 provenance，
  所有条件使用同一量化实例，不破坏研究设计）；
- 通过 ModelManager 分时加载（"target" 角色）。
"""
from typing import Optional

from core.schemas import TargetResponse
from targets.base_target import BaseTarget


class HfTarget(BaseTarget):
    name = "hf"

    def __init__(
        self,
        model_path: str,
        model_manager=None,
        dtype: str = "float16",
        device: str = "cuda",
        do_sample: bool = False,
        max_new_tokens: int = 512,
        temperature: float = 1.0,
        top_p: float = 1.0,
        quantization: Optional[dict] = None,   # quantization_spec() 的返回值
    ) -> None:
        self.model_path = model_path
        self.manager = model_manager
        self.dtype = dtype
        self.device = device
        self.do_sample = do_sample
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.quantization = quantization
        self._model = None
        self._tokenizer = None
        self.calls = 0

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            if self.manager is not None:
                self.manager.acquire("target", lambda: None)
            return

        def _load():
            from engine.hf_backend import load_causal_lm
            self._model, self._tokenizer = load_causal_lm(
                self.model_path, dtype=self.dtype, device=self.device,
                quantization=self.quantization)

        if self.manager is not None:
            self.manager.acquire("target", _load)
            self.manager.register_unloader(self._unload)
        else:
            _load()

    def _unload(self) -> None:
        self._model = None
        self._tokenizer = None

    def generate(self, prompt: str) -> TargetResponse:
        import time

        self._ensure_loaded()
        if self.manager is not None:
            self.manager.bump("target")
        self.calls += 1

        start = time.time()
        from engine.hf_backend import chat_generate
        result = chat_generate(
            self._model, self._tokenizer,
            [{"role": "user", "content": prompt}],
            max_new_tokens=self.max_new_tokens,
            do_sample=self.do_sample,
            temperature=self.temperature, top_p=self.top_p,
            device=self.device)
        return TargetResponse(
            text=result["text"],
            model_name=self.model_path,
            latency=time.time() - start,
            input_tokens=result["input_tokens"],
            output_tokens=result["output_tokens"],
            metadata={
                "backend": self.name,
                "model_path": self.model_path,
                "quantization": (self.quantization or {}).get("mode"),
                "compute_dtype": (self.quantization or {}).get(
                    "compute_dtype", self.dtype),
            },
        )
