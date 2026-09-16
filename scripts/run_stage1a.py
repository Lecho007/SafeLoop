# -*- coding: utf-8 -*-
"""Stage 1A 入口（V0.3 设计 §21）。

用法：
    python scripts/run_stage1a.py                       # 真实后端（需权重 + GPU）
    python scripts/run_stage1a.py --dry-run             # scripted 后端走同一管道（无 GPU）
    python scripts/run_stage1a.py --config configs/hardware/rtx4060_8g.yaml
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.stage1a import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/hardware/rtx4060_8g.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="scripted/demo 后端验证管道（无需权重与 GPU）")
    args = parser.parse_args()
    main(args.config, dry_run=args.dry_run)
