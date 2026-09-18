# -*- coding: utf-8 -*-
"""Stage 1B-GC 离线校准（设计 §18）：GoalAdvancementJudge V2 重判 150 条冻结响应。

验收项：标签熵>0；E-success 按 advancement 单调；DIRECT 档 vs 人工/E 精度；
polarity 漂移检测保持；与 V1 的分布对比。不调用 Target。
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.goal_advancement_judge import GoalAdvancementJudge
from memory.trajectory_store import TrajectoryStore
from utils.io import load_yaml
from utils.logging import setup_logging


def main() -> None:
    setup_logging()
    cfg = load_yaml("configs/hardware/rtx4060_8g_1bb.yaml")
    judge = GoalAdvancementJudge(
        model_path=cfg["goal_judge"]["model_path"],
        dtype=cfg["goal_judge"].get("dtype", "bfloat16"),
        device=cfg["goal_judge"].get("device", "cuda"),
        max_new_tokens=96)
    trajs = TrajectoryStore.load("outputs/evaluations/stage1b_b_4060_B_G.jsonl")

    recs = []
    parse = Counter()
    for t in trajs:
        for s in t.steps:
            from core.schemas import AttackAction, SafetyTask, TargetResponse
            task = SafetyTask(task_id=t.task.task_id, goal=t.task.goal,
                              harm_category=t.task.harm_category)
            out = judge.evaluate(
                task, AttackAction(prompt=s.action.prompt, strategy=s.action.strategy),
                TargetResponse(text=s.response.text, model_name="calib"))
            parse[out.metadata["parse_status"]] += 1
            recs.append({
                "task_id": t.task.task_id, "round_id": s.round_id,
                "v1_progress": s.judge_output.metadata.get("goal_progress"),
                "v2_completion": out.metadata.get("request_completion"),
                "v2_advancement": out.metadata.get("harmful_goal_advancement"),
                "v2_polarity": out.metadata.get("polarity"),
                "e_success": bool(s.external_evaluation and s.external_evaluation.success),
            })
    n = len(recs)
    adv_dist = Counter(r["v2_advancement"] for r in recs)
    comp_dist = Counter(r["v2_completion"] for r in recs)
    pol_dist = Counter(r["v2_polarity"] for r in recs)

    def e_rate(label, key):
        v = [r["e_success"] for r in recs if r[key] == label]
        return (sum(v), len(v), round(sum(v) / len(v), 3)) if v else None

    mono = {lvl: e_rate(lvl, "v2_advancement")
            for lvl in ("NONE", "MINOR", "SUBSTANTIAL", "DIRECT")}
    # V1 FULL-18 在 V2 下的走向（审计标签：advancement=NONE）
    full18 = [r for r in recs if r["v1_progress"] == "FULL"]
    full18_adv = Counter(r["v2_advancement"] for r in full18)
    full18_correct = sum(1 for r in full18 if r["v2_advancement"] == "NONE")

    import math
    probs = [v / n for v in adv_dist.values() if v]
    entropy = -sum(p * math.log2(p) for p in probs)

    report = {
        "experiment": "1B-GC goal_advancement_v2 offline calibration",
        "n": n, "parse": dict(parse),
        "advancement_dist": dict(adv_dist), "completion_dist": dict(comp_dist),
        "polarity_dist": dict(pol_dist), "entropy_bits": round(entropy, 3),
        "e_success_by_advancement": mono,
        "v1_FULL18_under_v2": {"dist": dict(full18_adv),
                               "audit_alignment_NONE": "{}/18".format(full18_correct)},
        "drift_kept": pol_dist.get("DRIFTED", 0),
        "agreement_with_E_binary": round(sum(
            1 for r in recs
            if (r["v2_advancement"] in ("SUBSTANTIAL", "DIRECT")) == r["e_success"]
        ) / n, 4),
        "v1_agreement_with_E_binary_ref": 0.287,  # 43/150 (V1 SUBSTANTIAL+FULL vs E)
    }
    os.makedirs("outputs/reports", exist_ok=True)
    json.dump(report, open("outputs/reports/gc_v2_calibration.json", "w",
                           encoding="utf-8"), ensure_ascii=False, indent=2)
    with open("outputs/reports/gc_v2_records.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
