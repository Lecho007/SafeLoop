#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SafeLoop-CN v0.1 策展：JailBench 公开 seed（MIT，国标五域）→ SafeLoop 任务格式。

路线（docs/roadmap.md P3）：
  - 只用 seed 层做 goal（"应拒绝"类问题）——不用 10800 条越狱增强集，
    攻击变体是红方智能体的职责，题库不能替它打；
  - 跨一级领域轮转抽样 N 条（默认 40），输出与 JBB 同构的 jsonl；
  - 全部标注 review_status=pending_review：交付前需人工两轮审核
    （语义 + 标签），审核通过后改 approved 并升版本号。

用法：
  python scripts/build_safeloop_cn.py [--csv JailBench_seed.csv] [--n 40]
      [--out data/tasks/safeloop_cn_v0.1.jsonl]
CSV 下载：https://github.com/STAIR-BUPT/JailBench （JailBench_seed.csv，公开子集）
"""
import argparse
import csv
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def stratified(rows, n):
    """跨一级领域轮转抽样（与 main_agent._stratified_sample 同语义）。"""
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["cat"], []).append(r)
    cats = sorted(by_cat)
    out, i = [], 0
    while len(out) < n:
        progressed = False
        for c in cats:
            if i < len(by_cat[c]) and len(out) < n:
                out.append(by_cat[c][i])
                progressed = True
        if not progressed:
            break
        i += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="data/raw/jailbench_seed.csv")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--out", default="data/tasks/safeloop_cn_v0.1.jsonl")
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = []
        for raw in reader:
            if len(raw) < 4 or not raw[1].strip():
                continue
            rows.append({"idx": raw[0].strip(), "goal": raw[1].strip(),
                         "cat": raw[2].strip(), "sub": raw[3].strip()})
    # 去重（按 goal）
    seen, uniq = set(), []
    for r in rows:
        if r["goal"] not in seen:
            seen.add(r["goal"])
            uniq.append(r)

    picked = stratified(uniq, args.n)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for i, r in enumerate(picked, 1):
            f.write(json.dumps({
                "task_id": "CN-{:04d}".format(i),
                "goal": r["goal"],
                "harm_category": r["cat"],
                "source": "jailbench_seed",
                "source_id": "JB-{}".format(r["idx"]),
                "language": "zh",
                "metadata": {
                    "feedback_observability": "content_observable",
                    "secondary_domain": r["sub"],
                    "review_status": "pending_review",
                    "license": "MIT (STAIR-BUPT/JailBench)",
                },
            }, ensure_ascii=False) + "\n")

    cats = Counter(r["cat"] for r in picked)
    subs = Counter(r["sub"] for r in picked)
    print("源 CSV：{} 行（去重后 {}）→ 抽样 {}".format(
        len(rows), len(uniq), len(picked)))
    print("输出：{}".format(args.out))
    print("一级领域分布：", dict(sorted(cats.items())))
    print("二级领域 top5：", dict(subs.most_common(5)))
    print("⚠ 全部条目 review_status=pending_review——交付前需人工审核"
          "（语义 + 标签）后改 approved。")


if __name__ == "__main__":
    main()
