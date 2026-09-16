# -*- coding: utf-8 -*-
"""JailbreakBench → SafetyTask 适配器（V0.3 设计 §4/§41-5/6）。

JBB 官方 artifacts（jailbreakbench.github.io / HF `JailbreakBench/JBB-Behaviors`）
为 JSON 数组，元素形如：
    {"index": 0, "goal": "...", "target": "...", "category": "hate", ...}
共 100 条 misuse behaviors、10 个大类。

- stratified sample：每类抽 per_category 条（rng 固定）；
- harm_category 采用 "JBB:<category>" 前缀（不硬编码进框架 taxonomy）；
- --demo 模式：不依赖数据集文件，生成跨 10 类的占位任务（用于离线 smoke）。
"""
import json
import random
from typing import List

from core.schemas import SafetyTask

JBB_CATEGORIES = [
    "hate", "discrimination", "violence", "criminal_planning",
    "illegal_activity", "child_abuse", "sexual_content",
    "privacy_violation", "cybercrime", "misinformation_disinformation",
]


def convert_jbb_artifact(path: str, per_category: int = 2, seed: int = 42) -> List[SafetyTask]:
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
