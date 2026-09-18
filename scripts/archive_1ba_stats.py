# -*- coding: utf-8 -*-
"""1B-A 正式归档统计（V0.3-B §14/§15/§16）：效应量 + 置信区间 + 新机制指标。

- ΔHSR/ΔSPR/ΔASR：task-level paired bootstrap 95% CI
- KEEP 遵守率：Wilson 95% CI（避免 30/30 过度表述）
- EAR（有效适应率，§4）：全部反馈决策中产生正向结果的比例
- 首次成功风险率 h_t（§5）：P(first success at t | 未成功)
- FRR 按动作分解（§16）
"""
import json
import math
import random
from collections import Counter
from typing import Dict, List

from memory.trajectory_store import TrajectoryStore

EXP = "stage1b_a_4060"


def wilson_ci(k: int, n: int, z: float = 1.96) -> Dict:
    if n == 0:
        return {"k": 0, "n": 0, "p": None, "ci": [None, None]}
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return {"k": k, "n": n, "p": round(p, 4),
            "ci": [round(max(0, center - half), 4), round(min(1, center + half), 4)]}


def paired_bootstrap_task_level(fn_a, fn_b, trajs_a, trajs_b, n_boot=5000, seed=42):
    """task 级配对 bootstrap：fn(trajs)->float 的差值 CI。"""
    by_a = {t.task.task_id: t for t in trajs_a}
    by_b = {t.task.task_id: t for t in trajs_b}
    ids = sorted(set(by_a) & set(by_b))
    point = fn_b([by_b[i] for i in ids]) - fn_a([by_a[i] for i in ids])
    rng = random.Random(seed)
    deltas = []
    for _ in range(n_boot):
        sample = [ids[rng.randrange(len(ids))] for _ in range(len(ids))]
        sa = [by_a[i] for i in sample]
        sb = [by_b[i] for i in sample]
        deltas.append(fn_b(sb) - fn_a(sa))
    deltas.sort()
    lo = deltas[int(0.025 * n_boot)]
    hi = deltas[int(0.975 * n_boot) - 1]
    return {"delta": round(point, 4), "ci": [round(lo, 4), round(hi, 4)], "n_paired": len(ids)}


def _ext_ok(step) -> bool:
    return bool(step.external_evaluation and step.external_evaluation.success)


def hsr(trajs) -> float:
    s = h = 0
    for t in trajs:
        for prev, cur in zip(t.steps, t.steps[1:]):
            if _ext_ok(prev):
                s += 1
                if cur.action.strategy != prev.action.strategy:
                    h += 1
    return h / s if s else 0.0


def asr5(trajs) -> float:
    if not trajs:
        return 0.0
    return sum(1 for t in trajs if any(_ext_ok(s) for s in t.steps[:5])) / len(trajs)


def ear(trajs) -> Dict:
    """EAR（§4）：正向反馈决策 / 全部反馈决策。
    正向 = (KEEP 且该步 E 成功) + (REFINE/SWITCH/UNCERTAIN 且下一步 E 首次成功)。"""
    good = total = 0
    for t in trajs:
        for i, s in enumerate(t.steps[:-1]):
            fb = s.feedback
            if fb is None or fb.adaptation_action is None:
                continue
            total += 1
            cur_ok = _ext_ok(s)
            next_ok = _ext_ok(t.steps[i + 1])
            prev_ok = _ext_ok(t.steps[i - 1]) if i > 0 else False
            if fb.adaptation_action == "KEEP" and cur_ok:
                good += 1          # 成功时保留 = 正确决策
            elif fb.adaptation_action in ("REFINE", "SWITCH", "UNCERTAIN"):
                if next_ok and not prev_ok and not cur_ok:
                    good += 1      # 未成功时调整且下一轮首次成功
    return {"good": good, "total": total,
            "ear": round(good / total, 4) if total else None}


def first_success_hazard(trajs) -> Dict[str, float]:
    """h_t（§5）：P(first success at t | 此前未成功)。"""
    at_risk = Counter()
    first = Counter()
    for t in trajs:
        for r in range(5):
            if any(_ext_ok(s) for s in t.steps[:r]):
                break  # 已成功，退出风险集
            at_risk[r] += 1
            if r < len(t.steps) and _ext_ok(t.steps[r]):
                first[r] += 1
    return {str(r): round(first[r] / at_risk[r], 4) for r in range(5) if at_risk[r]}


def frr_by_action(trajs) -> Dict:
    """FRR 按动作分解（§16）。响应 = 下一轮 strategy 或 prompt 改变。"""
    resp = Counter()
    tot = Counter()
    for t in trajs:
        for i, s in enumerate(t.steps[:-1]):
            fb = s.feedback
            nxt = t.steps[i + 1]
            if fb is None or fb.adaptation_action is None:
                continue
            if fb.adaptation_action == "KEEP" and _ext_ok(s):
                pass  # KEEP 的响应定义不同，单独用遵守率
            elif fb.adaptation_action in ("REFINE", "SWITCH", "UNCERTAIN"):
                tot[fb.adaptation_action] += 1
                adjusted = (nxt.action.strategy != s.action.strategy
                            or nxt.action.prompt != s.action.prompt)
                if adjusted:
                    resp[fb.adaptation_action] += 1
    return {a: round(resp[a] / tot[a], 4) if tot[a] else None
            for a in ("REFINE", "SWITCH", "UNCERTAIN")}


def main():
    out: Dict = {}
    trajs = {c: TrajectoryStore.load(
        "outputs/trajectories/{}_{}.jsonl".format(EXP, c)) for c in ("C1", "C3")}
    keep_k = keep_n = 0
    for t in trajs["C3"]:
        for prev, cur in zip(t.steps, t.steps[1:]):
            fb = prev.feedback
            if fb is not None and fb.adaptation_action == "KEEP":
                keep_n += 1
                if cur.action.strategy == prev.action.strategy:
                    keep_k += 1
    out["keep_obedience"] = wilson_ci(keep_k, keep_n)
    out["d_hsr"] = paired_bootstrap_task_level(hsr, hsr, trajs["C1"], trajs["C3"])
    out["d_asr5"] = paired_bootstrap_task_level(asr5, asr5, trajs["C1"], trajs["C3"])
    out["d_spr"] = paired_bootstrap_task_level(
        lambda ts: 1 - hsr(ts), lambda ts: 1 - hsr(ts), trajs["C1"], trajs["C3"])
    out["ear"] = {c: ear(trajs[c]) for c in ("C1", "C3")}
    out["first_success_hazard"] = {c: first_success_hazard(trajs[c])
                                   for c in ("C1", "C3")}
    out["frr_by_action_c3"] = frr_by_action(trajs["C3"])
    path = "outputs/reports/stage1b_a_archive_stats.json"
    json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print("\nsaved ->", path)


if __name__ == "__main__":
    main()
