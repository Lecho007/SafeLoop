#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v1.1 消融实验 harness（roadmap A4）：记忆与调度分开验证，再 2×2 联合。

条件矩阵（每条件独立 run，全部走 SafeLoopMainAgent 产品路径 + checkpoint）：
  M0/A0: use_memory=False, adaptive=None   —— 基线（固定每任务预算）
  M1/A1: use_memory=True,  adaptive=None   —— 单独验证记忆
  S1/A2: use_memory=False, adaptive=Q      —— 单独验证调度（D(Q)/Yield 口径）
  A3:    use_memory=True,  adaptive=Q      —— 联合

记忆防泄漏（红线 4）：正式测试条件用 warmup 阶段（开发任务子集）积累后
冻结的快照（--warmup-tasks N 先跑并 snapshot；测试条件带 snapshot id）。

用法（真实运行，GPU）：
  PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True $PY scripts/run_v11_ablation.py \
      --conditions M0,M1 --tasks 20 --budget 5 --tag m_ablation
  $PY scripts/run_v11_ablation.py --conditions S0,S1 --adaptive-q 200,300,400 \
      --tasks 20 --budget 5 --tag s_ablation
  $PY scripts/run_v11_ablation.py --conditions A0,A1,A2,A3 --adaptive-q 300 ...

  --dry-run：零 GPU 冒烟（只验证计划/接线/汇总格式，不加载模型）。
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONDITIONS = {
    "M0": {"use_memory": False, "adaptive": None},
    "M1": {"use_memory": True, "adaptive": None},
    "S0": {"use_memory": False, "adaptive": None},        # 固定预算基线
    "S1": {"use_memory": False, "adaptive": "Q"},         # Q 由 --adaptive-q 提供或逐值
    "A0": {"use_memory": False, "adaptive": None},
    "A1": {"use_memory": True, "adaptive": None},
    "A2": {"use_memory": False, "adaptive": "Q"},
    "A3": {"use_memory": True, "adaptive": "Q"},
}


def _run_condition(name, cfg_val, q, args, snapshot_id=None):
    from safeloop.agents.main_agent import SafeLoopMainAgent
    agent = SafeLoopMainAgent(
        config_path=args.config, seed=args.seed)
    overrides = {
        "mode": "standard", "max_tasks": args.tasks,
        "budget_per_task": args.budget, "suite": args.suite,
        "use_memory": cfg_val["use_memory"],
    }
    if cfg_val["adaptive"] == "Q":
        overrides["adaptive_budget"] = int(q)
    if snapshot_id:
        overrides["memory_snapshot_id"] = snapshot_id
    tag = "{}{}{}".format(args.tag, name, "_q{}".format(q) if q else "")
    agent.submit("[v1.1-ablation] {}".format(tag), **overrides)
    agent.run_id = "v11_{}".format(tag)          # 可读编号（检查点/报告对齐）
    agent.run()
    return agent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conditions", default="M0,M1")
    ap.add_argument("--tasks", type=int, default=20)
    ap.add_argument("--budget", type=int, default=5)
    ap.add_argument("--adaptive-q", default="300",
                    help="逗号分隔，S1/A2/A3 逐值跑")
    ap.add_argument("--warmup-tasks", type=int, default=10,
                    help="记忆 warmup 的开发任务数（冻结快照供测试条件用）")
    ap.add_argument("--suite", default="jbb100")
    ap.add_argument("--config", default="configs/hardware/rtx4060_8g_1br.yaml")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tag", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    results = []
    qs = [q for q in args.adaptive_q.split(",") if q]
    conds = [c.strip() for c in args.conditions.split(",") if c.strip()]
    unknown = [c for c in conds if c not in CONDITIONS]
    if unknown:
        print("unknown conditions:", unknown, "可选:", sorted(CONDITIONS))
        return 1

    # ---- 记忆 warmup + 冻结快照（任何 use_memory 条件存在时）
    snapshot_id = None
    if any(CONDITIONS[c]["use_memory"] for c in conds):
        from safeloop.skills.memory import MemoryStore
        from safeloop.agents.main_agent import SafeLoopMainAgent
        tmp = SafeLoopMainAgent(config_path=args.config, seed=args.seed)
        fp_target = tmp  # fingerprint 在 run 时由 cfg 计算；warmup 直接跑
        print("[warmup] use_memory=True on {} dev tasks …".format(
            args.warmup_tasks))
        if args.dry_run:
            snapshot_id = "snap-dryrun"
            print("[warmup] dry-run: skip execution, snapshot =", snapshot_id)
        else:
            agent = SafeLoopMainAgent(config_path=args.config, seed=args.seed)
            agent.submit("[v1.1-warmup] dev slice",
                         mode="standard", max_tasks=args.warmup_tasks,
                         budget_per_task=args.budget, suite=args.suite,
                         use_memory=True)
            agent.run_id = "v11_warmup_{}".format(args.tag)
            agent.run()
            store = MemoryStore(db_path="outputs/memory/memory.db")
            snapshot_id = store.snapshot(
                note="v1.1 warmup {} tasks {}".format(args.warmup_tasks,
                                                      args.tag))
            print("[warmup] snapshot frozen:", snapshot_id,
                  json.dumps(store.stats()))

    # ---- 各条件
    for cond in conds:
        cfg_val = CONDITIONS[cond]
        q_list = qs if cfg_val["adaptive"] == "Q" else [None]
        for q in q_list:
            label = "{}{}{}".format(args.tag, cond,
                                    "_q{}".format(q) if q else "")
            print("\n===== condition {} (memory={}, adaptive={}) =====".format(
                label, cfg_val["use_memory"], q or "off"))
            t0 = time.time()
            if args.dry_run:
                from safeloop.agents.main_agent import (EvaluationPlanner,
                                                        EvaluationRequest)
                req = EvaluationRequest(question=label, mode="standard",
                                        max_tasks=args.tasks,
                                        budget_per_task=args.budget,
                                        suite=args.suite,
                                        use_memory=cfg_val["use_memory"],
                                        adaptive_budget=(
                                            int(q) if q else None),
                                        memory_snapshot_id=snapshot_id)
                plan = EvaluationPlanner(args.config).plan(req)
                rec = {"condition": label, "dry_run": True,
                       "tasks_file": plan.tasks_file,
                       "memory": req.use_memory, "snapshot": snapshot_id,
                       "adaptive_budget": req.adaptive_budget}
                print(json.dumps(rec, ensure_ascii=False))
            else:
                agent = _run_condition(cond, cfg_val, q, args, snapshot_id)
                rep = agent.report or {}
                rec = {"condition": label,
                       "run_id": agent.run_id,
                       "asr_at_budget": ((rep.get("metrics", {})
                                          .get("user_layer", {})
                                          .get("asr_at_budget"))),
                       "auc_b": (rep.get("metrics", {})
                                 .get("user_layer", {}).get("auc_b")),
                       "risk_tasks": rep.get("overview", {}).get("risk_tasks"),
                       "total_tasks": rep.get("overview", {}).get("total_tasks"),
                       "adaptive": rep.get("adaptive"),
                       "elapsed_min": round((time.time() - t0) / 60, 1)}
                print(json.dumps(rec, ensure_ascii=False))
            results.append(rec)

    out = "outputs/reports/v11_ablation{}.json".format(
        "_{}".format(args.tag) if args.tag else "")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"conditions": results, "args": vars(args),
                   "snapshot_id": snapshot_id}, f, ensure_ascii=False, indent=2)
    print("\nsummary ->", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
