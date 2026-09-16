# -*- coding: utf-8 -*-
"""生成 JBB 任务 manifest（V0.3 设计 §4/§41-6）。

用法：
    # 真实数据：先下载 JBB behaviors 官方 artifacts（jailbreakbench.github.io）
    python scripts/build_jbb_tasks.py --source /path/to/jailbreakbench.json \
        --per-category 2 --out data/tasks/jbb20.jsonl

    # 离线 demo（不依赖数据集，占位任务，仅管道验证）
    python scripts/build_jbb_tasks.py --demo --out data/tasks/jbb20_demo.jsonl
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.adapters.jailbreakbench import (
    convert_jbb_artifact,
    make_demo_tasks,
    write_manifest,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", help="JBB behaviors JSON 文件路径")
    parser.add_argument("--demo", action="store_true", help="生成占位任务（无需数据集）")
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data/tasks/jbb20.jsonl")
    args = parser.parse_args()

    if args.demo:
        tasks = make_demo_tasks(per_category=args.per_category)
    elif args.source:
        tasks = convert_jbb_artifact(args.source, args.per_category, args.seed)
    else:
        parser.error("需要 --source 或 --demo 之一")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    write_manifest(tasks, args.out)
    cats = sorted({t.harm_category for t in tasks})
    print("wrote {} tasks -> {} ({} categories: {})".format(
        len(tasks), args.out, len(cats), ", ".join(cats)))


if __name__ == "__main__":
    main()
