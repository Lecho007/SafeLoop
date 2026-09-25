#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SafeLoop CLI（v1.0 设计 §二十一）：evaluate / compare / report / replay。"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


def main():
    ap = argparse.ArgumentParser(prog="safeloop")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("evaluate")
    e.add_argument("--target", default="phi-3.5-mini")
    e.add_argument("--suite", default="jbb100")
    e.add_argument("--budget", type=int, default=5)
    e.add_argument("--mode", default="standard",
                   choices=["standard", "guided", "compare"])
    e.add_argument("--max-tasks", type=int, default=None)
    e.add_argument("--question", default=None)

    c = sub.add_parser("compare")
    c.add_argument("--target", default="phi-3.5-mini")
    c.add_argument("--suite", default="jbb100")
    c.add_argument("--max-tasks", type=int, default=None)

    r = sub.add_parser("report")
    r.add_argument("run_id", help="replay 源或 run id")

    args = ap.parse_args()
    from utils.logging import setup_logging
    setup_logging()

    if args.cmd == "evaluate":
        from safeloop.agents.main_agent import SafeLoopMainAgent
        agent = SafeLoopMainAgent()
        q = args.question or "评估 {} 的安全风险".format(args.target)
        agent.submit(q, target_model=args.target, mode=args.mode,
                     budget_per_task=args.budget, max_tasks=args.max_tasks)
        report = agent.run()
        print(json.dumps(report["overview"], ensure_ascii=False, indent=2))
        print("metrics:", json.dumps(report["metrics"]["user_layer"], ensure_ascii=False))
    elif args.cmd == "compare":
        from safeloop.agents.main_agent import SafeLoopMainAgent
        agent = SafeLoopMainAgent()
        agent.submit("对比评估 {} 的安全风险".format(args.target),
                     target_model=args.target, mode="compare",
                     max_tasks=args.max_tasks)
        report = agent.run()
        print(json.dumps(report["comparison"], ensure_ascii=False, indent=2))
    elif args.cmd == "report":
        from safeloop.skills.replay_loader import load_prerun_as_agent
        agent = load_prerun_as_agent(args.run_id)
        r = agent.report
        print(json.dumps(r["overview"], ensure_ascii=False, indent=2))
        print("\nmetrics:", json.dumps(r["metrics"]["user_layer"], ensure_ascii=False))
        print("\n代表案例:")
        for c in r["representative_cases"]:
            print(" -", c["task_id"], c["why_representative"])


if __name__ == "__main__":
    main()
