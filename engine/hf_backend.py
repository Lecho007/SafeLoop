# -*- coding: utf-8 -*-
"""HF 后端基础设施（V0.3，设计文档 §36/§37）。

V100 32GB 路线：分时加载（sequential loading）——同一时刻只有一个模型驻留 GPU：
    load Red(4B) → 批量生成 → unload → load Target(7B) → … → unload
    load Judge(4B) → 批量判定 → unload →（全部轮次结束后）load Evaluator(2B)。

统一 dtype=float16（不用 BF16，V100 不支持或不适配 checkpoint metadata）。
torch/transformers 一律懒加载：无 GPU 环境也能 import 本模块做协议测试。
"""
from typing import Any, Dict, Optional

def resolve_dtype(dtype: str = "float16"):
    import torch
    return getattr(torch, dtype, torch.float16)


_NF4_ALIASES = ("4bit", "nf4", "int4")


def quantization_spec(quantization, compute_dtype: str = "bfloat16"):
    """规范化量化配置（纯函数，可单测）。

    :param quantization: 配置值 "none"/None/"4bit"/"nf4"/"int4"
    :return: {"mode": "nf4", "compute_dtype": ...} 或 None（不量化）
    """
    if not quantization or str(quantization).lower() in ("none", ""):
        return None
    q = str(quantization).lower()
    if q in _NF4_ALIASES:
        return {"mode": "nf4", "compute_dtype": compute_dtype}
    raise ValueError("unsupported quantization: {}（当前仅支持 4bit/nf4/int4）".format(quantization))


def _device_index(device: str) -> int:
    if device == "cuda":
        return 0
    if device.startswith("cuda:"):
        try:
            return int(device.split(":")[1])
        except ValueError:
            pass
    raise ValueError("量化加载需要 GPU 设备，当前 device={}".format(device))


def _with_cuda_retry(loader, attempts: int = 3, wait_s: int = 30):
    """WSL2 上偶发 'CUDA driver error: device not ready'（驱动级瞬断）：
    加载类操作失败时等待后重试。"""
    import time
    last = None
    for i in range(attempts):
        try:
            return loader()
        except RuntimeError as exc:
            if "CUDA" not in str(exc) and "driver" not in str(exc):
                raise
            last = exc
            time.sleep(wait_s)
    raise last


def load_causal_lm(model_path: str, dtype: str = "float16", device: str = "cuda",
                   quantization: Optional[dict] = None):
    """加载因果 LM + tokenizer（懒导入 transformers）。

    :param quantization: quantization_spec() 的返回值；4-bit NF4 走
        BitsAndBytesConfig + device_map，此时数值精度由 compute_dtype 决定。
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=False)
    tokenizer = _with_cuda_retry(lambda: tokenizer)
    if quantization:
        from transformers import BitsAndBytesConfig
        spec = dict(quantization)
        model = _with_cuda_retry(lambda: AutoModelForCausalLM.from_pretrained(
            model_path,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True,
                bnb_4bit_compute_dtype=resolve_dtype(spec.get("compute_dtype", dtype)),
            ),
            device_map={"": _device_index(device)},
            attn_implementation="sdpa",   # 避免 eager 大矩阵 matmul（CUBLAS 崩溃根因）
        ))
    else:
        model = _with_cuda_retry(lambda: AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=resolve_dtype(dtype),
            device_map=None,
            attn_implementation="sdpa",
        ))
        model.to(device)
    model.eval()
    return model, tokenizer


def load_sequence_classifier(model_path: str, dtype: str = "float16", device: str = "cuda"):
    """加载序列分类器（StrongREJECT 本地权重 fallback 路径）。"""
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_path, torch_dtype=resolve_dtype(dtype),
    )
    model.to(device)
    model.eval()
    return model, tokenizer


def chat_generate(model, tokenizer, messages, max_new_tokens: int = 256,
                   do_sample: bool = False, temperature: float = 1.0,
                   top_p: float = 1.0, device: str = "cuda",
                   template_kwargs: Optional[dict] = None) -> Dict[str, Any]:
    """按 chat template 生成，返回 {text, input_tokens, output_tokens}。

    template_kwargs 传给 apply_chat_template（如 Qwen3 的 enable_thinking=False）；
    模板不认识该参数时自动回退为无参调用。
    """
    import torch

    def _apply(with_kwargs):
        kw = template_kwargs if with_kwargs else {}
        return tokenizer.apply_chat_template(
            messages, tokenize=True, add_generation_prompt=True,
            return_tensors="pt", **kw).to(device)

    try:
        prompt_ids = _apply(True)
    except TypeError:
        prompt_ids = _apply(False)
    kwargs = dict(
        inputs=prompt_ids,
        attention_mask=torch.ones_like(prompt_ids),  # pad==eos 时必须显式传入
        max_new_tokens=max_new_tokens,
        do_sample=do_sample,
        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
    )
    if do_sample:
        kwargs.update(temperature=temperature, top_p=top_p)

    def _gen():
        with torch.no_grad():
            return model.generate(**kwargs)

    try:
        out = _gen()
    except RuntimeError as exc:
        # WSL2/笔记本 GPU 上偶发瞬时 CUBLAS 错误：清缓存后重试一次
        if "CUDA error" not in str(exc):
            raise
        torch.cuda.empty_cache()
        out = _gen()
    new_tokens = out[0][prompt_ids.shape[1]:]
    return {
        "text": tokenizer.decode(new_tokens, skip_special_tokens=True),
        "input_tokens": int(prompt_ids.shape[1]),
        "output_tokens": int(new_tokens.shape[0]),
    }


def generate_from_text(model, tokenizer, text: str, max_new_tokens: int = 64,
                       do_sample: bool = False, temperature: float = 1.0,
                       top_p: float = 1.0, device: str = "cuda") -> Dict[str, Any]:
    """对已渲染好的完整 prompt 文本生成（Qwen3Guard 官方模板路径：
    apply_chat_template 已内含 assistant 头与 <think> 预填充，不能再加 generation prompt）。"""
    import torch

    inputs = tokenizer(text, return_tensors="pt",
                       add_special_tokens=False).to(device)
    attention_mask = inputs.get("attention_mask")
    if attention_mask is None:
        attention_mask = torch.ones_like(inputs["input_ids"])
    kwargs = dict(
        input_ids=inputs["input_ids"],
        attention_mask=attention_mask,
        max_new_tokens=max_new_tokens,
        do_sample=do_sample,
        pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
    )
    if do_sample:
        kwargs.update(temperature=temperature, top_p=top_p)

    def _gen():
        with torch.no_grad():
            return model.generate(**kwargs)

    try:
        out = _gen()
    except RuntimeError as exc:
        if "CUDA error" not in str(exc):
            raise
        torch.cuda.empty_cache()
        out = _gen()
    new_tokens = out[0][inputs["input_ids"].shape[1]:]
    return {
        "text": tokenizer.decode(new_tokens, skip_special_tokens=True),
        "input_tokens": int(inputs["input_ids"].shape[1]),
        "output_tokens": int(new_tokens.shape[0]),
    }


class ModelManager:
    """单卡分时加载管理器：acquire(role) 时先释放上一个角色。

    role ∈ {"red", "target", "judge", "evaluator"}；loader/unloader 由各 Adapter
    注册。无 HF 后端（scripted/demo）时完全不触发加载。
    """

    def __init__(self) -> None:
        self._current_role: Optional[str] = None
        self._unloader: Optional[Any] = None
        self.loaded_roles: list = []
        self.call_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    def acquire(self, role: str, loader) -> None:
        """确保 role 对应模型驻留；切换角色时先卸载上一个（释放显存）。"""
        if self._current_role != role:
            self.release()
            loader()
            self._current_role = role
            if role not in self.loaded_roles:
                self.loaded_roles.append(role)

    def register_unloader(self, unloader) -> None:
        self._unloader = unloader

    def release(self) -> None:
        if self._unloader is not None:
            try:
                self._unloader()
            finally:
                self._unloader = None
        if self._current_role is not None:
            self._current_role = None
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    def count(self, role: str) -> int:
        return self.call_counts.get(role, 0)

    def bump(self, role: str) -> None:
        self.call_counts[role] = self.call_counts.get(role, 0) + 1

    @property
    def current_role(self) -> Optional[str]:
        return self._current_role

    def summary(self) -> Dict[str, int]:
        return dict(self.call_counts)
