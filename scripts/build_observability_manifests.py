# -*- coding: utf-8 -*-
"""生成 Stage 1B-A 三套任务 manifest（V0.3-B 设计 §5，映射冻结于
data/mappings/jbb_observability_v1.yaml，进入 1B 后不再修改）。

输出：
    data/tasks/jbb100_full.jsonl               # 全量 + observability 元数据
    data/tasks/jbb_content_observable.jsonl    # Stage 1B-A 主实验集
    data/tasks/jbb_goal_compliance.jsonl       # Stage 1B-B 实验集
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.io import load_yaml

MAPPING_PATH = "data/mappings/jbb_observability_v1.yaml"
SOURCE = "data/tasks/jbb100.jsonl"


def main() -> None:
    mapping = load_yaml(MAPPING_PATH)
    cat_map = mapping["categories"]
    version = mapping["version"]

    tasks = [json.loads(l) for l in open(SOURCE, encoding="utf-8")]
    full, content, compliance = [], [], []
    for t in tasks:
        cat = t["harm_category"].replace("JBB:", "")
        spec = cat_map.get(cat)
        if spec is None:
            raise KeyError("category not in mapping: {}（mapping_version={}）".format(
                cat, version))
        t["metadata"] = t.get("metadata") or {}
        t["metadata"]["feedback_observability"] = spec["feedback_observability"]
        t["metadata"]["observability_reason"] = spec["observability_reason"]
        t["metadata"]["mapping_version"] = version
        t["metadata"]["mapping_ambiguous"] = spec.get("ambiguous", False)
        full.append(t)
        (content if spec["feedback_observability"] == "content_observable"
         else compliance).append(t)

    outs = {
        "data/tasks/jbb100_full.jsonl": full,
        "data/tasks/jbb_content_observable.jsonl": content,
        "data/tasks/jbb_goal_compliance.jsonl": compliance,
    }
    for path, items in outs.items():
        with open(path, "w", encoding="utf-8") as f:
            for t in items:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        print("{} -> {} tasks".format(path, len(items)))
    from collections import Counter
    print("content_observable categories:",
          dict(Counter(t["harm_category"] for t in content)))


if __name__ == "__main__":
    main()
