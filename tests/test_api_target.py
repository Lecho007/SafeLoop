# -*- coding: utf-8 -*-
"""API Target 单测（mock HTTP，零真实调用）：三协议 payload/parse、key 隔离、连通测试。"""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from targets.api_target import (
    AnthropicTarget,
    OpenAIChatTarget,
    OpenAIResponsesTarget,
    build_api_target,
    test_connection,
)

CFG = {"provider": "openai_chat", "base_url": "https://api.example.com/v1",
       "model": "my-model", "api_key_env": "TEST_KEY"}


def _cfg(provider):
    return {**CFG, "provider": provider}


class TestPayloads(unittest.TestCase):
    def test_openai_chat_payload_and_parse(self):
        t = OpenAIChatTarget(_cfg("openai_chat"))
        self.assertEqual(t._url(), "https://api.example.com/v1/chat/completions")
        self.assertEqual(t._auth_headers("k1"),
                         {"Authorization": "Bearer k1"})
        p = t._build_payload("hello")
        self.assertEqual(p["messages"], [{"role": "user", "content": "hello"}])
        self.assertEqual(p["model"], "my-model")
        text, u, finish = t._parse({"choices": [{"message": {"content": "world"},
                                                 "finish_reason": "stop"}],
                                    "usage": {"prompt_tokens": 3, "completion_tokens": 2}})
        self.assertEqual(text, "world")
        self.assertEqual(u, {"input_tokens": 3, "output_tokens": 2})
        self.assertEqual(finish, "stop")

    def test_anthropic_payload_and_parse(self):
        t = AnthropicTarget(_cfg("anthropic"))
        self.assertEqual(t._url(), "https://api.example.com/v1/messages")
        h = t._auth_headers("k1")
        self.assertEqual(h["x-api-key"], "k1")
        self.assertIn("anthropic-version", h)
        p = t._build_payload("hello")
        self.assertNotIn("system", p)                    # system 独立参数，不进 messages
        self.assertEqual(p["messages"][0]["role"], "user")
        text, _, finish = t._parse({"content": [{"type": "text", "text": "a"},
                                                {"type": "text", "text": "b"}],
                                    "stop_reason": "end_turn",
                                    "usage": {"input_tokens": 1, "output_tokens": 1}})
        self.assertEqual(text, "ab")
        self.assertEqual(finish, "end_turn")

    def test_openai_responses_payload_and_parse(self):
        t = OpenAIResponsesTarget(_cfg("openai_responses"))
        self.assertEqual(t._url(), "https://api.example.com/v1/responses")
        p = t._build_payload("hello")
        self.assertEqual(p["input"], "hello")            # input 字段而非 messages
        self.assertIn("max_output_tokens", p)
        text, _, finish = t._parse({"output": [{"content": [
            {"type": "output_text", "text": "ok"}]}], "status": "completed"})
        self.assertEqual(text, "ok")
        self.assertEqual(finish, "completed")

    def test_factory_by_provider(self):
        for provider, cls in (("openai_chat", OpenAIChatTarget),
                              ("anthropic", AnthropicTarget),
                              ("openai_responses", OpenAIResponsesTarget)):
            t = build_api_target(_cfg(provider))
            self.assertIsInstance(t, cls)

    def test_unknown_provider_rejected(self):
        with self.assertRaises(ValueError):
            build_api_target({**CFG, "provider": "grpc"})


class TestKeyIsolation(unittest.TestCase):
    def test_key_never_in_describe_or_metadata(self):
        os.environ["TEST_KEY"] = "sk-secret-123"
        try:
            t = OpenAIChatTarget(CFG)
            with mock.patch("targets.api_target._HTTP.post_json",
                            return_value={"choices": [{"message": {"content": "pong"}}]}):
                resp = t.generate("ping")
            blob = json.dumps({"describe": t.describe(),
                               "metadata": resp.metadata}, ensure_ascii=False)
            self.assertNotIn("sk-secret-123", blob)      # key 不入任何描述/元数据
            self.assertIn("api_key_env", blob)            # 只记变量名
            self.assertEqual(t.model_name, "api:openai_chat/my-model")
        finally:
            del os.environ["TEST_KEY"]

    def test_missing_key_env_raises(self):
        t = OpenAIChatTarget({**CFG, "api_key_env": "NO_SUCH_KEY_XYZ"})
        with self.assertRaises(RuntimeError):
            t.generate("ping")


class TestConnection(unittest.TestCase):
    def test_test_connection_ok(self):
        os.environ["TEST_KEY"] = "k"
        try:
            with mock.patch("targets.api_target._HTTP.post_json",
                            return_value={"choices": [{"message": {"content": "pong"}}]}):
                r = test_connection(CFG)
            self.assertTrue(r["ok"])
            self.assertEqual(r["model"], "my-model")
        finally:
            del os.environ["TEST_KEY"]

    def test_test_connection_failure_reported(self):
        os.environ["TEST_KEY"] = "k"   # 凭据就位，模拟网络/服务错误
        try:
            with mock.patch("targets.api_target._HTTP.post_json",
                            side_effect=RuntimeError("boom")):
                r = test_connection(CFG)
            self.assertFalse(r["ok"])
            self.assertIn("boom", r["error"])
        finally:
            del os.environ["TEST_KEY"]


if __name__ == "__main__":
    unittest.main()
