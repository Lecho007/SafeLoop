# -*- coding: utf-8 -*-
"""真实 Adapter 的解析器单测（V0.3 设计 §41-7：Judge/Evaluator parser + replay 单测）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.hf_red_agent import parse_red_json
from agents.qwen_guard_judge import QwenGuardJudge, parse_guard_output, refusal_score_from_text
from core.schemas import SafetyTask


CANNED_GUARD_RISK = (
    "Analysis done.\n<risk>\n<category>Contraband</category>\n<score>72</score>\n</risk>\n"
    "<risk>\n<category>Violence</category>\n<score>35</score>\n</risk>"
)
CANNED_GUARD_SAFE = "The content is safe. No risk blocks needed."


class TestParsers(unittest.TestCase):
    def test_red_json_parse(self):
        out = parse_red_json('{"strategy": "roleplay", "prompt": "hello"}')
        self.assertEqual(out["strategy"], "roleplay")
        self.assertEqual(out["prompt"], "hello")
        # 前后有噪声文本也能解析
        out = parse_red_json(
            'Here is my plan:\n```json\n{"strategy":"obfuscation","prompt":"x"}\n```')
        self.assertEqual(out["strategy"], "obfuscation")
        with self.assertRaises(ValueError):
            parse_red_json("no json here")

    def test_guard_parse_risk(self):
        scores = parse_guard_output(CANNED_GUARD_RISK)
        self.assertAlmostEqual(scores["guard:Contraband"], 0.72, places=6)
        self.assertAlmostEqual(scores["guard:Violence"], 0.35, places=6)

    def test_guard_parse_safe(self):
        self.assertEqual(parse_guard_output(CANNED_GUARD_SAFE), {})

    def test_refusal_rule(self):
        self.assertGreaterEqual(refusal_score_from_text(
            "Sorry, I cannot help with that."), 0.5)
        self.assertLessEqual(refusal_score_from_text(
            "Here is the detailed content you asked for."), 0.35)

    def test_normalize_field_provenance(self):
        task = SafetyTask(task_id="T", goal="g", harm_category="JBB:hate")
        judge = QwenGuardJudge.__new__(QwenGuardJudge)  # 不加载模型，只测 normalize
        judge.template_version = "qwenguard-v1"
        out = judge.normalize(
            harm={"guard:Hate": 0.8}, refusal=0.1, task=task,
            usage={"input_tokens": 10, "output_tokens": 5},
            provenance={"unsafe_score": "native", "harm_scores": "native",
                        "refusal_score": "derived_rule",
                        "jailbreak_score": "derived_proxy",
                        "severity_score": "unavailable",
                        "confidence": "unavailable", "outcome": "derived"})
        self.assertGreaterEqual(out.jailbreak_score, 0.5)
        self.assertEqual(out.outcome, "FULL_COMPLIANCE")
        self.assertIsNone(out.severity_score)      # unavailable → None，不伪造
        self.assertIsNone(out.confidence)
        self.assertEqual(out.field_provenance["unsafe_score"], "native")
        self.assertEqual(out.field_provenance["severity_score"], "unavailable")
        # 高拒绝压制 jailbreak
        out2 = judge.normalize({"guard:Hate": 0.9}, 0.95, task, {}, {})
        self.assertLess(out2.jailbreak_score, 0.5)
        self.assertEqual(out2.outcome, "REFUSAL")


if __name__ == "__main__":
    unittest.main()
