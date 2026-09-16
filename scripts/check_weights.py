# -*- coding: utf-8 -*-
"""权重完整性校验：python scripts/check_weights.py

按 configs/*.yaml 中注册的 model_path 检查本地权重目录
（config.json + tokenizer 文件 + 至少一个权重分片）。
"""
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.io import load_yaml

ROLE_KEYS = [("red_agent", "Red (Qwen3-4B)"),
             ("target", "Target (Mistral-7B-Instruct-v0.3)"),
             ("judge", "Judge (Qwen3Guard-Gen-4B)"),
             ("evaluator", "Evaluator (StrongREJECT gemma-2b)")]

WEIGHT_EXTS = ("*.safetensors", "*.bin", "*.gguf")


def check_role(cfg, key, label) -> bool:
    path = (cfg.get(key, {}) or {}).get("model_path")
    if not path:
        print("[SKIP] {} 未配置 model_path（可能是 scripted 后端）".format(label))
        return True
    if not os.path.isdir(path):
        print("[MISS] {} 目录不存在: {}".format(label, path))
        return False
    has_config = os.path.exists(os.path.join(path, "config.json"))
    has_tokenizer = any(glob.glob(os.path.join(path, "tokenizer*")))
    has_weights = any(
        glob.glob(os.path.join(path, ext)) for ext in WEIGHT_EXTS)
    ok = has_config and has_tokenizer and has_weights
    status = "OK  " if ok else "WARN"
    print("[{}] {} @ {}".format(status, label, path))
    if not has_config:
        print("       - 缺 config.json")
    if not has_tokenizer:
        print("       - 缺 tokenizer 文件")
    if not has_weights:
        print("       - 缺权重文件（*.safetensors / *.bin）")
    return ok


def main() -> int:
    all_ok = True
    for config_path in sys.argv[1:] or ["configs/stage1a.yaml"]:
        if not os.path.exists(config_path):
            continue
        cfg = load_yaml(config_path)
        print("== {} ==".format(config_path))
        for key, label in ROLE_KEYS:
            all_ok &= check_role(cfg, key, label)
    print("\nweight check: {}".format("PASS" if all_ok else "INCOMPLETE"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
