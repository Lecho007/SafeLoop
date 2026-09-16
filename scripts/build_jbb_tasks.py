# -*- coding: utf-8 -*-
"""生成 JBB 任务 manifest（V0.3 设计 §4/§41-6）。

用法：
    # 官方 CSV（默认 data/raw/jbb_harmful_behaviors.csv，已随仓库下载）
    python scripts/build_jbb_tasks.py --per-category 2 --out data/tasks/jbb20.jsonl
    python scripts/build_jbb_tasks.py --all --out data/tasks/jbb100.jsonl      # JBB-100

    # 旧版 artifacts JSON 兼容
    python scripts/build_jbb_tasks.py --source /path/to/jailbreakbench.json --out ...

    # 离线 demo（不依赖数据集，占位任务，仅管道验证）
    python scripts/build_jbb_tasks.py --demo --out data/tasks/jbb20_demo.jsonl
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.adapters.jailbreakbench import (
    DEFAULT_HARMFUL_CSV,
    convert_jbb_artifact,
    convert_jbb_csv,
    make_demo_tasks,
    write_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="旧版 JBB artifacts JSON 路径")
    parser.add_argument("--csv", default=DEFAULT_HARMFUL_CSV,
                        help="官方 harmful-behaviors CSV 路径")
    parser.add_argument("--all", action="store_true", help="全量 100 条（JBB-100）")
    parser.add_argument("--demo", action="store_true", help="生成占位任务（无需数据集）")
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/tasks/jbb20.jsonl")
    args = parser.parse_args()

    if args.demo:
        tasks = make_demo_tasks(per_category=args.per_category)
    elif args.source:
        tasks = convert_jbb_artifact(args.source, args.per_category, args.seed)
    elif args.all:
        tasks = convert_jbb_csv(args.csv, per_category=None)
    else:
        tasks = convert_jbb_csv(args.csv, per_category=args.per_category, seed=args.seed)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    write_manifest(tasks, args.out)
    cats = sorted({t.harm_category for t in tasks})
    print("wrote {} tasks -> {} ({} categories: {})".format(
        len(tasks), args.out, len(cats), ", ".join(cats)))


if __name__ == "__main__":
    main()
