# -*- coding: utf-8 -*-
"""双硬件配置档测试（V0.3.1：V100 32G / RTX4060 8G）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.factory import RunnerBundle
from engine.hf_backend import quantization_spec
from utils.io import load_yaml

V100_CFG = "configs/hardware/v100_32g.yaml"
RTX_CFG = "configs/hardware/rtx4060_8g.yaml"


class TestQuantSpec(unittest.TestCase):
    def test_none(self):
        self.assertIsNone(quantization_spec(None))
        self.assertIsNone(quantization_spec("none"))
        self.assertIsNone(quantization_spec(""))

    def test_nf4_aliases(self):
        for alias in ("4bit", "nf4", "int4", "NF4"):
            spec = quantization_spec(alias, "bfloat16")
            self.assertEqual(spec, {"mode": "nf4", "compute_dtype": "bfloat16"})

    def test_unsupported(self):
        with self.assertRaises(ValueError):
            quantization_spec("8bit")


class TestHardwareConfigs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v100 = load_yaml(V100_CFG)
        cls.rtx = load_yaml(RTX_CFG)

    def test_hardware_blocks(self):
        self.assertEqual(self.rtx["hardware"]["vram_gb"], 8)
        self.assertEqual(self.v100["hardware"]["vram_gb"], 32)
        for cfg in (self.v100, self.rtx):
            self.assertTrue(cfg["runtime"]["sequential_loading"])
            self.assertTrue(cfg["runtime"]["round_batched"])

    def test_rtx4060_lineup(self):
        # 1.7B(bf16) + Phi-3.5-mini(NF4) + Qwen3Guard-0.6B(bf16) + StrongREJECT(fp16)
        self.assertIn("Qwen3-1.7B", self.rtx["red_agent"]["model_path"])
        self.assertEqual(self.rtx["red_agent"]["dtype"], "bfloat16")
        self.assertIn("Phi-3.5-mini", self.rtx["target"]["model_path"])
        self.assertEqual(self.rtx["target"]["quantization"], "nf4")
        self.assertEqual(self.rtx["target"]["compute_dtype"], "bfloat16")
        self.assertIn("Qwen3Guard-Gen-0.6B", self.rtx["judge"]["model_path"])
        self.assertEqual(self.rtx["judge"].get("quantization"), None)
        self.assertEqual(self.rtx["evaluator"]["dtype"], "bfloat16")
        # StrongREJECT：LoRA adapter + gated gemma-2b 底座
        self.assertTrue(self.rtx["evaluator"]["base_model_path"])

    def test_v100_lineup_fp16_no_quantization(self):
        self.assertIn("Qwen3-4B", self.v100["red_agent"]["model_path"])
        self.assertIn("Mistral-7B", self.v100["target"]["model_path"])
        self.assertIsNone(quantization_spec(self.v100["target"].get("quantization")))
        self.assertEqual(self.v100["red_agent"]["dtype"], "float16")

    def test_protocol_identical_across_hardware(self):
        """硬件改变 ≠ 研究协议改变：两档的实验协议字段完全一致。"""
        keys = ("experiment", "protocol")
        for k in keys:
            v1 = {x: y for x, y in self.v100[k].items() if x != "name"}
            v2 = {x: y for x, y in self.rtx[k].items() if x != "name"}
            self.assertEqual(v1, v2, k)

    def test_bundle_provenance_records_quantization(self):
        bundle = RunnerBundle(self.rtx, RTX_CFG)
        quant = bundle.provenance["quantization"]
        self.assertEqual(quant["target"]["quantization"],
                         {"mode": "nf4", "compute_dtype": "bfloat16"})
        self.assertEqual(quant["hardware"]["gpu"], "RTX4060_Laptop")
        # V100 档不量化
        bundle_v = RunnerBundle(self.v100, V100_CFG)
        self.assertIsNone(bundle_v.provenance["quantization"]["target"]["quantization"])


if __name__ == "__main__":
    unittest.main()
