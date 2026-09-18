# -*- coding: utf-8 -*-
"""配对统计检验（V0.3 设计 §28）：McNemar（ASR）与 Wilcoxon 符号秩（CTTS）。

纯 stdlib 正态近似实现，满足 Stage 1B 报告需要；不做 scipy 依赖。
"""
import math
from typing import Dict, List, Optional, Tuple


def _normal_sf(z: float) -> float:
    """标准正态生存函数（ Abramowitz–Stegun 近似）。"""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def mcnemar_test(paired_a: List[bool], paired_b: List[bool]) -> Dict:
    """配对二元结果的 McNemar 检验（连续性校正的正态近似）。

    b = #(A=0, B=1)，c = #(A=1, B=0)；检验 B 是否系统性优于 A。
    返回 {b, c, statistic, p_value}；b+c=0 时 p=1.0。
    """
    if len(paired_a) != len(paired_b):
        raise ValueError("paired lists must have equal length")
    b = sum(1 for x, y in zip(paired_a, paired_b) if (not x) and y)
    c = sum(1 for x, y in zip(paired_a, paired_b) if x and (not y))
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "statistic": 0.0, "p_value": 1.0}
    chi2 = (abs(b - c) - 1.0) ** 2 / float(n)
    # df=1 的卡方 → 等价于 |z| 的双侧正态
    z = math.sqrt(chi2)
    p = 2.0 * _normal_sf(z)
    return {"b": b, "c": c, "statistic": round(chi2, 4), "p_value": round(p, 6)}


def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Dict:
    """Wilcoxon 符号秩检验（正态近似，含零差剔除与平均秩结处理）。

    检验 x−y 的中位数是否为 0。
    """
    if len(x) != len(y):
        raise ValueError("paired lists must have equal length")
    diffs = [(a - b, 1 if a - b > 0 else -1) for a, b in zip(x, y) if a != b]
    n = len(diffs)
    if n < 1:
        return {"n": 0, "w_plus": 0, "statistic": 0.0, "p_value": 1.0}
    diffs.sort(key=lambda t: abs(t[0]))
    # 平均秩（处理并列绝对值）
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(diffs[j + 1][0]) == abs(diffs[i][0]):
            j += 1
        avg_rank = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    w_plus = sum(r for (d, s), r in zip(diffs, ranks) if s > 0)
    mu = n * (n + 1) / 4.0
    sigma = math.sqrt(n * (n + 1) * (2 * n + 1) / 24.0)
    z = (w_plus - mu) / sigma if sigma > 0 else 0.0
    p = 2.0 * _normal_sf(abs(z))
    return {"n": n, "w_plus": w_plus, "statistic": round(z, 4), "p_value": round(p, 6)}


def hierarchical_paired_bootstrap(pairs_by_seed, metric_fn, n_boot=2000,
                                  seed=42, ci=0.95):
    """层级配对 bootstrap（1B-R §18）：第一层 bootstrap task，第二层在 task 内
    bootstrap seed。pairs_by_seed: {seed: [(traj_a, traj_b), ...]}；
    metric_fn(traj) -> float（ASR 用 0/1，AUC 等同理由调用方定义）。
    返回 Δ=mean(metric_b)-mean(metric_a) 的点估计与 95% CI。
    """
    import random
    seeds = sorted(pairs_by_seed)
    rng = random.Random(seed)
    # 展平为 task 维度（每个 (task,seed) 是一个可重采样单元的成分）
    units = []  # list of list: 每 task 的 (a,b) 跨 seed
    by_task = {}
    for s in seeds:
        for ta, tb in pairs_by_seed[s]:
            by_task.setdefault(ta.task.task_id, []).append((ta, tb))
    task_ids = sorted(by_task)

    def _delta(sample_ids):
        va = []
        for tid in sample_ids:
            row = by_task[tid]
            # 第二层：task 内重采样 seed
            picks = [row[rng.randrange(len(row))] for _ in row]
            va.extend((metric_fn(a), metric_fn(b)) for a, b in picks)
        ma = sum(v[0] for v in va) / len(va)
        mb = sum(v[1] for v in va) / len(va)
        return mb - ma

    point = _delta(task_ids)
    deltas = sorted(_delta([task_ids[rng.randrange(len(task_ids))]
                            for _ in task_ids]) for _ in range(n_boot))
    n = n_boot
    return {"delta": round(point, 4),
            "ci": [round(deltas[int((1 - ci) / 2 * n)], 4),
                   round(deltas[int((1 + ci) / 2 * n) - 1], 4)],
            "n_tasks": len(task_ids), "n_seeds": len(seeds)}
