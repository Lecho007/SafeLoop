# -*- coding: utf-8 -*-
"""Calibration-A（V0.3-J 设计 §11）：JBB 官方 judge_comparison 300 条。

用 Qwen3Guard V2（官方模板）判 (prompt, target_response)，
将 proxy（Unsafe & NoRefusal）与 human_majority（1=jailbreak success）对比。
注意：Qwen3Guard 不是 jailbreak success judge，这里只验证方向性信息。

用法：python scripts/calibrate_judge.py [configs/hardware/rtx4060_8g.yaml]
"""
import csv
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.qwen_guard_judge_v2 import Qwen3GuardJudgeV2
from core.schemas import AttackAction, SafetyTask, TargetResponse
from utils.io import load_yaml
from utils.logging import setup_logging

CSV_PATH = "data/raw/jbb_judge_comparison.csv"   # 官方 300 条 split


def main() -> None:
    setup_logging()
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "configs/hardware/rtx4060_8g.yaml")
    rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
    print("official judge_comparison rows:", len(rows))

    judge = Qwen3GuardJudgeV2(
        model_path=cfg["judge"]["model_path"],
        dtype=cfg["judge"].get("dtype", "bfloat16"),
        device=cfg["judge"].get("device", "cuda"),
        max_new_tokens=int(cfg["judge"].get("max_new_tokens", 64)),
    )

    tp = fp = fn = tn = 0
    parse = Counter()
    confusion = Counter()
    records = []
    for i, r in enumerate(rows):
        task = SafetyTask(task_id="JBB-JC-{:03d}".format(int(r["Index"])),
                          goal=r["goal"], harm_category="JBB:judge_comparison",
                          language="en")
        action = AttackAction(prompt=r["prompt"], strategy="calibration")
        response = TargetResponse(text=r["target_response"], model_name="calib")
        out = judge.evaluate(task, action, response)
        parse[out.metadata["parse_status"]] += 1
        pred = out.outcome == "LIKELY_COMPLIANCE"   # Unsafe & No Refusal
        human = r["human_majority"] == "1"
        confusion[("pred" if pred else "other", "human1" if human else "human0")] += 1
        if pred and human:
            tp += 1
        elif pred and not human:
            fp += 1
        elif not pred and human:
            fn += 1
        else:
            tn += 1
        if i % 50 == 0:
            print("  {}/{} processed".format(i, len(rows)))
        records.append({
            "index": r["Index"],
            "safety": out.metadata["safety"],
            "refusal": out.metadata["refusal"],
            "outcome": out.outcome,
            "parse_status": out.metadata["parse_status"],
            "human_majority": human,
            "human_votes": [r["human1"], r["human2"], r["human3"]],
            "other_judges": {k: r[k] for k in
                             ("harmbench_cf", "gpt4_cf", "llamaguard2_cf", "llama3_cf")},
        })

    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = (2 * prec * rec / (prec + rec)) if prec and rec else None
    report = {
        "experiment": "calibration_A_jbb_judge_comparison",
        "n": len(rows),
        "parse_status": dict(parse),
        "proxy_likely_compliance_vs_human_jailbroken": {
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec, 4) if rec is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "agreement": round((tp + tn) / len(rows), 4),
        },
        "confusion": {"{}|{}".format(k[0], k[1]): v for k, v in sorted(confusion.items())},
        "note": "Qwen3Guard 不是 jailbreak success judge；此处只验证 Safety×Refusal "
                "proxy 是否携带方向性信息（human_majority=1 表示人类判定越狱成功）",
    }
    os.makedirs("outputs/reports", exist_ok=True)
    with open("outputs/reports/calibration_A.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open("outputs/reports/calibration_A_records.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps(report["proxy_likely_compliance_vs_human_jailbroken"], indent=2))
    print("confusion:", report["confusion"])
    print("parse:", dict(parse))
    print("saved -> outputs/reports/calibration_A.json")


if __name__ == "__main__":
    main()
