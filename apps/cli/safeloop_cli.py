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

    a = sub.add_parser("api-eval", help="黑盒 API 模型评估")
    a.add_argument("--base-url", required=True)
    a.add_argument("--model", required=True)
    a.add_argument("--provider", default="openai_chat",
                   choices=["openai_chat", "anthropic", "openai_responses"])
    a.add_argument("--api-key-env", default="TARGET_API_KEY")
    a.add_argument("--mode", default="standard",
                   choices=["standard", "guided", "compare"])
    a.add_argument("--max-tasks", type=int, default=3)
    a.add_argument("--test-connection", action="store_true")

    tc = sub.add_parser("test-connection")
    tc.add_argument("--base-url", required=True)
    tc.add_argument("--model", required=True)
    tc.add_argument("--provider", default="openai_chat",
                   choices=["openai_chat", "anthropic", "openai_responses"])
    tc.add_argument("--api-key-env", default="TARGET_API_KEY")

    s = sub.add_parser("serve", help="启动 Web 工作台（SPA + API 单进程单端口）")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8712)

    wb = sub.add_parser("workbench", help="终端向导工作台（rich 交互），其余参数透传")
    wb.add_argument("rest", nargs=argparse.REMAINDER)

    cl = sub.add_parser("cleanup",
                        help="清理 N 天前的排队/取消/失败 run 记录（保留完成 run 与产物文件）")
    cl.add_argument("--days", type=int, default=30)

    rv = sub.add_parser("review", help="标记（--off 取消）高风险案例人工复核")
    rv.add_argument("run_id")
    rv.add_argument("--off", action="store_true")

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
    elif args.cmd == "test-connection":
        from targets.api_target import test_connection
        r = test_connection({"provider": args.provider,
                             "base_url": args.base_url, "model": args.model,
                             "api_key_env": args.api_key_env})
        print(json.dumps(r, ensure_ascii=False, indent=2))
        sys.exit(0 if r["ok"] else 1)
    elif args.cmd == "api-eval":
        from safeloop.agents.main_agent import SafeLoopMainAgent
        api_cfg = {"provider": args.provider, "base_url": args.base_url,
                   "model": args.model, "api_key_env": args.api_key_env}
        if args.test_connection:
            from targets.api_target import test_connection as _tc
            r = _tc(api_cfg)
            print("连接:", json.dumps(r, ensure_ascii=False))
            if not r["ok"]:
                sys.exit(1)
        agent = SafeLoopMainAgent()
        agent.submit("评估 API 模型 {} 的安全风险".format(args.model),
                     target_model=args.model, mode=args.mode,
                     max_tasks=args.max_tasks, api_target=api_cfg)
        report = agent.run()
        print(json.dumps(report["overview"], ensure_ascii=False, indent=2))
    elif args.cmd == "report":
        from safeloop.skills.replay_loader import load_prerun_as_agent
        agent = load_prerun_as_agent(args.run_id)
        r = agent.report
        print(json.dumps(r["overview"], ensure_ascii=False, indent=2))
        print("\nmetrics:", json.dumps(r["metrics"]["user_layer"], ensure_ascii=False))
        print("\n代表案例:")
        for c in r["representative_cases"]:
            print(" -", c["task_id"], c["why_representative"])
    elif args.cmd == "serve":
        import uvicorn
        uvicorn.run("apps.api.server:app", host=args.host, port=args.port)
    elif args.cmd == "workbench":
        from apps.cli.workbench_cli import main as wb_main
        sys.exit(wb_main(list(args.rest)))
    elif args.cmd == "cleanup":
        from safeloop.runs.manager import RunManager
        mgr = RunManager(start_worker=False)
        print(json.dumps(mgr.prune_runs(args.days), ensure_ascii=False, indent=2))
    elif args.cmd == "review":
        from safeloop.runs.manager import RunManager
        mgr = RunManager(start_worker=False)
        mgr.set_reviewed(args.run_id, not args.off)
        print(json.dumps({"run_id": args.run_id, "reviewed": not args.off},
                         ensure_ascii=False))


if __name__ == "__main__":
    main()
