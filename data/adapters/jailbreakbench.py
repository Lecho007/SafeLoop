# -*- coding: utf-8 -*-
"""JailbreakBench → SafetyTask 适配器（V0.3 设计 §4/§41-5/6）。

官方数据已下载到 data/raw/（HF `JailbreakBench/JBB-Behaviors` 的 CSV）：
    harmful-behaviors.csv：100 misuse behaviors、10 大类（Index/Goal/Target/
    Behavior/Category/Source）
    benign-behaviors.csv：100 benign behaviors（留作 OverRefusal/Judge sanity，
    不进入 ASR 主实验）。

- stratified sample：每类抽 per_category 条（rng 固定）；
- harm_category 采用 "JBB:<category>" 前缀（不硬编码进框架 taxonomy）；
- --demo 模式：不依赖数据集文件，生成跨 10 类的占位任务（用于离线 smoke）。
"""
import csv
import json
import random
from typing import List, Optional

from core.schemas import SafetyTask

JBB_CATEGORIES = [
    "hate", "discrimination", "violence", "criminal_planning",
    "illegal_activity", "child_abuse", "sexual_content",
    "privacy_violation", "cybercrime", "misinformation_disinformation",
]

DEFAULT_HARMFUL_CSV = "data/raw/jbb_harmful_behaviors.csv"


def load_jbb_csv(path: str = DEFAULT_HARMFUL_CSV) -> List[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return [
            {
                "index": int(row["Index"]),
                "goal": row["Goal"],
                "target": row["Target"],
                "category": row["Category"],
                "source": row.get("Source", ""),
            }
            for row in csv.DictReader(f)
        ]


def convert_jbb_csv(path: str = DEFAULT_HARMFUL_CSV, per_category: Optional[int] = 2,
                    seed: int = 42) -> List[SafetyTask]:
    """官方 CSV → SafetyTask；per_category=None 表示全量（JBB-100）。"""
    behaviors = load_jbb_csv(path)
    by_cat = {}
    for b in behaviors:
        by_cat.setdefault(b["category"], []).append(b)
    rng = random.Random(seed)
    tasks: List[SafetyTask] = []
    for cat in sorted(by_cat):
        pool = sorted(by_cat[cat], key=lambda b: b["index"])
        picked = pool if per_category is None else rng.sample(
            pool, min(per_category, len(pool)))
        for b in picked:
            tasks.append(SafetyTask(
                task_id="JBB-{:04d}".format(b["index"]),
                goal=b["goal"],
                harm_category="JBB:{}".format(cat),
                source="jailbreakbench",
                source_id=str(b["index"]),
                language="en",
                metadata={"jbb_target": b["target"], "jbb_source": b["source"]},
            ))
    return tasks


def convert_jbb_artifact(path: str, per_category: int = 2, seed: int = 42) -> List[SafetyTask]:
    """旧版 artifacts JSON（{"index","goal","target","category"} 数组）兼容入口。"""
    with open(path, "r", encoding="utf-8") as f:
        behaviors = json.load(f)
    by_cat = {}
    for b in behaviors:
        by_cat.setdefault(b.get("category", "uncategorized"), []).append(b)
    rng = random.Random(seed)
    tasks: List[SafetyTask] = []
    for cat in sorted(by_cat):
        pool = sorted(by_cat[cat], key=lambda b: b.get("index", 0))
        picked = rng.sample(pool, min(per_category, len(pool)))
        for b in picked:
            tasks.append(SafetyTask(
                task_id="JBB-{:04d}".format(int(b.get("index", len(tasks)))),
                goal=b["goal"],
                harm_category="JBB:{}".format(cat),
                source="jailbreakbench",
                source_id=str(b.get("index")),
                language="en",
                metadata={"jbb_target": b.get("target", "")},
            ))
    return tasks


def make_demo_tasks(per_category: int = 2, total_categories: int = 10) -> List[SafetyTask]:
    """无数据集文件时的占位任务（DEMO，smoke 用；不包含真实有害内容）。"""
    tasks: List[SafetyTask] = []
    idx = 0
    for cat in JBB_CATEGORIES[:total_categories]:
        for k in range(per_category):
            idx += 1
            tasks.append(SafetyTask(
                task_id="DEMO-JBB-{:04d}".format(idx),
                goal="[DEMO] Probe whether the target complies with a request in "
                     "the '{}' risk area (placeholder goal, pipeline smoke only).".format(cat),
                harm_category="JBB:{}".format(cat),
                source="demo",
                source_id="{:04d}".format(idx),
                language="en",
                metadata={"variant": k},
            ))
    return tasks


def write_manifest(tasks: List[SafetyTask], out_path: str) -> str:
    with open(out_path, "w", encoding="utf-8") as f:
        for t in tasks:
            f.write(json.dumps(t.to_dict(), ensure_ascii=False) + "\n")
    return out_path
