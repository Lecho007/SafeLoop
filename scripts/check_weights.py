# -*- coding: utf-8 -*-
"""权重完整性校验：python scripts/check_weights.py [configs...]

按 configs/*.yaml 中注册的 model_path 检查本地权重目录。
- 常规模型：config.json + tokenizer 文件 + 权重分片（*.safetensors/*.bin）；
- StrongREJECT evaluator：LoRA adapter（adapter_config.json + adapter_model.safetensors）
  + gated 底座 gemma-2b（base_model_path，缺失时给出 HF_TOKEN 指引）。
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.io import load_yaml

ROLE_KEYS = [("red_agent", "Red"), ("target", "Target"),
             ("judge", "Judge"), ("evaluator", "Evaluator")]

WEIGHT_EXTS = ("*.safetensors", "*.bin", "*.gguf")


def _has_regular_weights(path: str) -> bool:
    return any(glob.glob(os.path.join(path, ext)) for ext in WEIGHT_EXTS)


def check_role(cfg, key, label) -> bool:
    path = (cfg.get(key, {}) or {}).get("model_path")
    if not path:
        print("[SKIP] {} 未配置 model_path（可能是 scripted 后端）".format(label))
        return True
    if not os.path.isdir(path):
        print("[MISS] {} 目录不存在: {}".format(label, path))
        return False

    is_adapter = os.path.exists(os.path.join(path, "adapter_config.json"))
    if is_adapter:
        has_weights = os.path.exists(os.path.join(path, "adapter_model.safetensors"))
        has_tokenizer = any(glob.glob(os.path.join(path, "tokenizer*")))
        ok = has_weights and has_tokenizer
        print("[{}] {}(LoRA adapter) @ {}".format("OK  " if ok else "WARN", label, path))
        if not has_weights:
            print("       - 缺 adapter_model.safetensors")
        if not has_tokenizer:
            print("       - 缺 tokenizer 文件")
        # gated 底座检查
        base = (cfg.get(key, {}) or {}).get("base_model_path")
        if base:
            base_ok = (os.path.isdir(base)
                       and os.path.exists(os.path.join(base, "config.json"))
                       and _has_regular_weights(base))
            if base_ok:
                print("[OK  ] {} gated 底座 @ {}".format(label, base))
            else:
                print("[MISS] {} gated 底座未就位 @ {}".format(label, base))
                print("       - 请在 HF 接受 google/gemma-2b 协议，设置 HF_TOKEN 后：")
                print("         HF_TOKEN=xxx hf download google/gemma-2b --local-dir {}".format(base))
                ok = False
        return ok

    has_config = os.path.exists(os.path.join(path, "config.json"))
    has_tokenizer = any(glob.glob(os.path.join(path, "tokenizer*")))
    has_weights = _has_regular_weights(path)
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
    for config_path in sys.argv[1:] or [
            "configs/hardware/rtx4060_8g.yaml", "configs/hardware/v100_32g.yaml"]:
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
