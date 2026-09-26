# -*- coding: utf-8 -*-
"""黑盒 API Target 适配器（v1.0：黑盒安全评估标准能力）。

三种协议（优先级按设计）：
  openai_chat      POST {base_url}/chat/completions   —— 兼容面最广（vLLM/LiteLLM/网关等）
  anthropic        POST {base_url}/messages           —— Claude 原生
  openai_responses POST {base_url}/responses           —— OpenAI 新一代统一接口

安全约定：
  - API Key 只经环境变量（api_key_env 字段记录变量名），永不写入任何落盘文件；
  - provenance 仅记录 base_url/model/provider/api_key_env（无 key）；
  - 重试 + 超时；失败抛 RuntimeError 由上层自动重启护栏接管。
"""
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from core.schemas import TargetResponse
from targets.base_target import BaseTarget

PROVIDERS = ("openai_chat", "anthropic", "openai_responses")

DEFAULTS = {"temperature": 0.7, "top_p": 1.0,
            # 推理型模型（deepseek-reasoner/flash 等）先输出思考链再给最终回答，
            # 思考同样消耗 completion 预算：实测 4096 下最难的攻击仍有思考耗尽
            # 导致空回答（finish=length），默认再放宽到 8192
            "max_tokens": 8192,
            "timeout": 60, "retries": 3}


def resolve_api_key(cfg: Dict) -> str:
    env_name = cfg.get("api_key_env", "")
    key = os.environ.get(env_name, "") if env_name else cfg.get("api_key", "")
    if not key:
        raise RuntimeError(
            "API target 需要凭据：请 export {}='...' 或配置 api_key".format(env_name))
    return key


class _HTTP:
    """极简 urllib POST（不引 openai/anthropic SDK，避免版本耦合）。"""

    _USE_PROXY = False

    @staticmethod
    def post_json(url: str, headers: Dict[str, str], payload: Dict,
                  timeout: int, retries: int) -> Dict:
        data = json.dumps(payload).encode("utf-8")
        last = None
        for attempt in range(max(1, retries)):
            req = urllib.request.Request(url, data=data, method="POST")
            for k, v in headers.items():
                req.add_header(k, v)
            req.add_header("Content-Type", "application/json")
            # 绕过系统代理直连（本机/内网端点常被全局代理拦截 502）；
            # 需要走代理的用户可在配置 headers.use_proxy=true 恢复
            if not _HTTP._USE_PROXY:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}))
            else:
                opener = urllib.request.build_opener()
            try:
                with opener.open(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                    json.JSONDecodeError) as exc:
                last = exc
                if attempt < retries - 1:
                    time.sleep(2 * (attempt + 1))
        raise RuntimeError("API target 请求失败（{} 次重试后）: {}".format(retries, last))


class APITargetBase(BaseTarget):
    """共同骨架：配置解析 + key 解析 + 计量。子类实现 _build_payload/_parse。"""

    def __init__(self, cfg: Dict) -> None:
        provider = cfg.get("provider", "openai_chat")
        if provider not in PROVIDERS:
            raise ValueError("unknown provider: {}（可选 {}）".format(provider, PROVIDERS))
        self.provider = provider
        self.base_url = str(cfg.get("base_url", "")).rstrip("/")
        self.model = cfg.get("model", "")
        self.api_key_env = cfg.get("api_key_env", "")
        self.gen = {**DEFAULTS, **(cfg.get("generation", {}) or {})}
        self.extra_headers = cfg.get("headers", {}) or {}
        self.calls = 0
        if not self.base_url or not self.model:
            raise ValueError("API target 需要 base_url 与 model")
        # display name：provider/model（不含 key）
        self.model_name = "api:{}/{}".format(provider, self.model)

    # ------------------------------------------------------------------ api
    def generate(self, prompt: str) -> TargetResponse:
        self.calls += 1
        start = time.time()
        key = resolve_api_key({"api_key_env": self.api_key_env})
        headers = {**self._auth_headers(key), **self.extra_headers}
        payload = self._build_payload(prompt)
        out = _HTTP.post_json(self._url(), headers, payload,
                              int(self.gen["timeout"]), int(self.gen["retries"]))
        text, usage, finish = self._parse(out)
        return TargetResponse(
            text=text, model_name=self.model_name,
            latency=time.time() - start,
            input_tokens=usage.get("input_tokens", len(prompt.split())),
            output_tokens=usage.get("output_tokens", len(text.split())),
            metadata={"backend": "api", "provider": self.provider,
                      "model": self.model, "base_url": self.base_url,
                      "api_key_env": self.api_key_env,   # 只记变量名，不记 key
                      "finish_reason": finish})

    def _url(self) -> str:
        raise NotImplementedError

    def _auth_headers(self, key: str) -> Dict[str, str]:
        raise NotImplementedError

    def _build_payload(self, prompt: str) -> Dict:
        raise NotImplementedError

    def _parse(self, out: Dict) -> tuple:
        raise NotImplementedError

    def describe(self) -> Dict[str, Any]:
        """给 provenance/测试连接用的安全描述（无 key）。"""
        return {"provider": self.provider, "base_url": self.base_url,
                "model": self.model, "api_key_env": self.api_key_env,
                "generation": self.gen}


class OpenAIChatTarget(APITargetBase):
    """POST {base_url}/chat/completions（兼容 vLLM/LiteLLM/Ollama 兼容层/自建网关）。"""
    name = "api_openai_chat"

    def _url(self):
        return "{}/chat/completions".format(self.base_url)

    def _auth_headers(self, key):
        return {"Authorization": "Bearer {}".format(key)}

    def _build_payload(self, prompt):
        return {"model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": self.gen["temperature"],
                "top_p": self.gen["top_p"],
                "max_tokens": self.gen["max_tokens"]}

    def _parse(self, out):
        ch = out["choices"][0]
        msg = ch.get("message") or {}
        u = out.get("usage", {}) or {}
        return (msg.get("content") or "",
                {"input_tokens": u.get("prompt_tokens", 0),
                 "output_tokens": u.get("completion_tokens", 0)},
                ch.get("finish_reason"))


class AnthropicTarget(APITargetBase):
    """POST {base_url}/messages（Claude 原生；system 为独立参数）。"""
    name = "api_anthropic"

    def _url(self):
        return "{}/messages".format(self.base_url)

    def _auth_headers(self, key):
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}

    def _build_payload(self, prompt):
        return {"model": self.model, "max_tokens": self.gen["max_tokens"],
                "temperature": self.gen["temperature"],
                "top_p": self.gen["top_p"],
                "messages": [{"role": "user", "content": prompt}]}

    def _parse(self, out):
        blocks = out.get("content", [])
        text = "".join(b.get("text", "") for b in blocks
                       if b.get("type") == "text")
        u = out.get("usage", {}) or {}
        return (text, {"input_tokens": u.get("input_tokens", 0),
                       "output_tokens": u.get("output_tokens", 0)},
                out.get("stop_reason"))


class OpenAIResponsesTarget(APITargetBase):
    """POST {base_url}/responses（OpenAI 新一代统一接口；input 字段）。"""
    name = "api_openai_responses"

    def _url(self):
        return "{}/responses".format(self.base_url)

    def _auth_headers(self, key):
        return {"Authorization": "Bearer {}".format(key)}

    def _build_payload(self, prompt):
        return {"model": self.model, "input": prompt,
                "max_output_tokens": self.gen["max_tokens"]}

    def _parse(self, out):
        text = out.get("output_text", "")
        if not text:
            for item in out.get("output", []) or []:
                for c in item.get("content", []) or []:
                    if c.get("type") in ("output_text", "text"):
                        text += c.get("text", "")
        u = out.get("usage", {}) or {}
        return (text, {"input_tokens": u.get("input_tokens", 0),
                       "output_tokens": u.get("output_tokens", 0)},
                out.get("status"))


_CLASSES = {"openai_chat": OpenAIChatTarget,
            "anthropic": AnthropicTarget,
            "openai_responses": OpenAIResponsesTarget}


def build_api_target(cfg: Dict) -> BaseTarget:
    provider = cfg.get("provider", "openai_chat")
    if provider not in _CLASSES:
        raise ValueError("unknown provider: {}（可选 {}）".format(
            provider, tuple(_CLASSES)))
    return _CLASSES[provider](cfg)


def test_connection(cfg: Dict) -> Dict:
    """发一条无害 ping（'Reply with the word: pong'）验证连通。"""
    try:
        target = build_api_target(cfg)
        resp = target.generate("Reply with exactly one word: pong")
        return {"ok": True, "provider": target.provider,
                "model": target.model, "reply": resp.text[:40],
                "latency_s": round(resp.latency, 2)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}
