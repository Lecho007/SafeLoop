#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SafeLoop 终端工作台（CLI GUI）：向导式参数 → 实时对话流 → 彩色结果报告。

用法（在仓库根目录）：
  python apps/cli/workbench_cli.py                       # 交互向导（目标 → 模式 → 场景数）
  python apps/cli/workbench_cli.py --mode standard -n 3  # 带参数直接跑
  python apps/cli/workbench_cli.py --base-url URL --model NAME   # 在线 API 黑盒
  python apps/cli/workbench_cli.py report outputs/reports/run-x_report.json

渲染逻辑拆为纯函数（输入 report dict / trajectory 桩 → 文本片段），
rich 只做上色包装；terms.py 术语/分级与网页 GUI 完全共用。
"""
import argparse
import json
import os
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
_WORKBENCH = os.path.join(_REPO, "apps", "workbench")
if _WORKBENCH not in sys.path:
    sys.path.insert(0, _WORKBENCH)
os.chdir(_REPO)

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from terms import CATEGORY_ZH, STRATEGY_ZH, compare_verdict, risk_grade, stars

MODE_ZH = {"standard": "标准检测", "guided": "智能引导", "compare": "对比检测"}
MODE_DUR = {"standard": "约 6-10 分钟", "guided": "约 6-10 分钟",
            "compare": "约 12-20 分钟"}
# terms.risk_grade 返回语义色名，映射到 rich 样式
RICH_OF = {"red": "bold red", "amber": "yellow", "green": "green", "gray": "dim"}
BAR_WIDTH = 22
PROMPT_CLIP = 240   # 与网页 GUI 实况区一致
RESPONSE_CLIP = 360


# ------------------------------------------------------------------ 纯渲染层
def dot_color(ev: Dict) -> str:
    """红=独立评审命中；黄=Unsafe/PARTIAL；绿=安全。与网页 GUI 同规则。"""
    if ev.get("success"):
        return "red"
    if ev.get("advancement") == "PARTIAL" or ev.get("safety") == "Unsafe":
        return "amber"
    return "green"


def judge_label(ev: Dict) -> str:
    """GUI 同款：有推进度→目标推进；否则内容判定；再否则已记录。"""
    if ev.get("advancement"):
        return "目标推进 " + str(ev["advancement"])
    if ev.get("safety"):
        return "内容判定 " + str(ev["safety"])
    return "已记录"


def round_line(ev: Dict) -> str:
    strat = STRATEGY_ZH.get(ev.get("strategy"), ev.get("strategy") or "?")
    return "第 {} 轮　{}　判别：{}".format(ev.get("round"), strat, judge_label(ev))


def _clip(text: Optional[str], limit: int) -> str:
    text = (text or "").replace("\n", " ").strip()
    return text if len(text) <= limit else text[:limit] + "…"


EMPTY_ANSWER = "（空回答）"


def count_empty_answers(trajectories) -> int:
    """回答文本为空的轮数——推理型模型回答预算耗尽/上游拦截的信号。"""
    n = 0
    for t in trajectories or []:
        for s in getattr(t, "steps", []) or []:
            if not (getattr(getattr(s, "response", None), "text", None) or "").strip():
                n += 1
    return n


def _step_ok(s) -> bool:
    ev = getattr(s, "external_evaluation", None)
    return bool(ev and getattr(ev, "success", False))


def verdict_short(s) -> str:
    meta = getattr(s.judge_output, "metadata", None) or {}
    return (meta.get("advancement") or meta.get("safety")
            or getattr(s.judge_output, "outcome", None) or "—")


def e_short(s) -> str:
    return "风险确认" if _step_ok(s) else "未触发"


def scenario_block(traj) -> List[str]:
    """'任务: JBB-0050 | 虚假信息（第2轮触发）' + 每轮一行紧凑明细。"""
    cat = (getattr(traj.task, "harm_category", "") or "").replace("JBB:", "")
    cat_zh = CATEGORY_ZH.get(cat, cat or "未分类")
    first = next((i + 1 for i, s in enumerate(traj.steps) if _step_ok(s)), None)
    lines = ["任务: {} | {}（{}）".format(
        traj.task.task_id, cat_zh,
        "第{}轮触发".format(first) if first else "未触发")]
    for s in traj.steps:
        strat = getattr(s.action, "strategy", None)
        lines.append("  R{} {}  判别:{}  E:{}".format(
            getattr(s, "round_id", 0) + 1, STRATEGY_ZH.get(strat, strat or "?"),
            verdict_short(s), e_short(s)))
    return lines


def scenario_details(trajectories: List, safe_limit: int = 3
                     ) -> Tuple[List[str], int]:
    """风险场景全列 + 安全场景取前 safe_limit 个。返回 (行列表, 风险场景数)。"""
    risky = {i for i, t in enumerate(trajectories) if any(_step_ok(s) for s in t.steps)}
    lines: List[str] = []
    for i, t in enumerate(trajectories):
        if i in risky:
            lines.extend(scenario_block(t))
    shown_safe = 0
    for i, t in enumerate(trajectories):
        if i not in risky and shown_safe < safe_limit:
            lines.extend(scenario_block(t))
            shown_safe += 1
    hidden = len(trajectories) - len(risky) - shown_safe
    if hidden > 0:
        lines.append("… 另有 {} 个安全场景未展开".format(hidden))
    return lines, len(risky)


def asr_at_full_budget(user_layer: Dict) -> Tuple[Optional[float], Optional[int]]:
    """ASR@k：asr_at_k 是按轮次曲线 dict（如 {"1":0.5,"3":1.0}），取满预算轮的值。

    兼容历史 float 形态；返回 (值, k)。
    """
    m = user_layer.get("asr_at_k")
    if isinstance(m, dict) and m:
        try:
            k = max(int(x) for x in m)
        except ValueError:
            return None, None
        return m.get(str(k)), k
    if isinstance(m, (int, float)):
        return float(m), None
    return None, None


def headline_parts(report: Dict) -> Tuple[str, str]:
    """(结论标题文本, 语义色名)。"""
    asr, _ = asr_at_full_budget((report.get("metrics") or {}).get("user_layer") or {})
    grade, color = risk_grade(asr)
    ov = report.get("overview") or {}
    head = "风险档位：{} ｜ {}/{} 个场景确认风险 ｜ 目标 {} ｜ 模式 {}".format(
        grade, ov.get("risk_tasks"), ov.get("total_tasks"),
        ov.get("target"), MODE_ZH.get(ov.get("mode"), ov.get("mode")))
    return head, color


def metrics_parts(user_layer: Dict) -> List[str]:
    asr, k = asr_at_full_budget(user_layer)
    auc = user_layer.get("auc_b")
    ctts = user_layer.get("mean_ctts")
    return ["{} {}".format("ASR@{}".format(k) if k else "ASR",
                           "—" if asr is None else "{:.1%}".format(asr)),
            "AUC-B {} {}".format("—" if auc is None else "{:.2f}".format(auc),
                                 stars(auc)),
            "平均首次触发 {}".format("—" if ctts is None else "{:.1f} 轮".format(ctts))]


def distribution_parts(risk_distribution: Dict, total: int
                       ) -> List[Tuple[str, int, float]]:
    out = []
    for cat, cnt in (risk_distribution or {}).items():
        raw = (cat or "").replace("JBB:", "")
        out.append((CATEGORY_ZH.get(raw, raw or str(cat)), cnt,
                    (cnt / total) if total else 0.0))
    return out


def comparison_parts(report: Dict) -> List[str]:
    comp = report.get("comparison") or {}
    if not comp:
        return []
    n = (report.get("overview") or {}).get("total_tasks") or 0
    lines = []
    asrs = {}
    for key, zh in (("standard", "标准检测 STD"), ("guided", "智能引导 GUI")):
        m = comp.get(key) or {}
        asr, k = asr_at_full_budget(m)
        asrs[key] = asr
        auc = m.get("auc_b")
        lines.append("{}：ASR@{} {} ｜ AUC-B {} {}".format(
            zh, k if k else "k", "—" if asr is None else "{:.1%}".format(asr),
            "—" if auc is None else "{:.2f}".format(auc), stars(auc)))
    verdict = compare_verdict(asrs["standard"], asrs["guided"], n)
    if verdict:
        lines.append("结论：" + verdict)
    if comp.get("note"):
        lines.append("注：" + comp["note"])
    return lines


def progress_bar(done: int, total: int, width: int = 26) -> str:
    ratio = (done / total) if total else 0.0
    filled = min(width, int(ratio * width + 0.5))
    return "▓" * filled + "░" * (width - filled)


def fmt_elapsed(seconds: float) -> str:
    return "{:02d}:{:02d}".format(int(seconds) // 60, int(seconds) % 60)


def _detail_blocks(lines: List[str]) -> List[List[str]]:
    blocks, cur = [], []
    for ln in lines:
        if ln.startswith("任务:") and cur:
            blocks.append(cur)
            cur = []
        cur.append(ln)
    if cur:
        blocks.append(cur)
    return blocks


# ------------------------------------------------------------------ rich 包装
def render_report(console: "Console", report: Dict,
                  detail_lines: Optional[List[str]] = None,
                  report_path: Optional[str] = None,
                  primary_note: Optional[str] = None) -> None:
    head, color = headline_parts(report)
    console.print(Panel(head, title="体检结论",
                        border_style=RICH_OF.get(color, color), expand=False))

    ul = ((report.get("metrics") or {}).get("user_layer") or {})
    mt = Table.grid(padding=(0, 3))
    for part in metrics_parts(ul):
        mt.add_row(part)
    console.print(mt)

    dist = report.get("risk_distribution") or {}
    if dist:
        total = (report.get("overview") or {}).get("total_tasks") or 1
        dt = Table.grid(padding=(0, 2))
        dt.add_column(justify="right", min_width=12)
        dt.add_column()
        dt.add_column(justify="right")
        for zh, cnt, ratio in distribution_parts(dist, total):
            filled = min(BAR_WIDTH, int(ratio * BAR_WIDTH + 0.5))
            dt.add_row(zh, "[red]▇[/red]" * filled + "[dim]╌[/dim]" * (BAR_WIDTH - filled),
                       str(cnt))
        console.print(Panel(dt, title="风险分布", border_style="red", expand=False))

    if detail_lines:
        blocks = _detail_blocks(detail_lines)
        st = Table.grid(padding=(0, 1))
        for block in blocks:
            risky = any("E:风险确认" in ln for ln in block)
            st.add_row(Text(block[0], style="bold red" if risky else "bold green"))
            for ln in block[1:]:
                st.add_row(Text("  " + ln))
        title = "场景明细" + ("（{}）".format(primary_note) if primary_note else "")
        console.print(Panel(st, title=title, border_style="cyan", expand=False))
    else:
        for c in (report.get("representative_cases") or [])[:3]:
            cat = (c.get("category") or "").replace("JBB:", "")
            console.print("· {} {} — {}".format(
                c.get("task_id"), CATEGORY_ZH.get(cat, cat), c.get("why_representative")))

    comp_lines = comparison_parts(report)
    if comp_lines:
        console.print(Panel("\n".join(comp_lines), title="对比检测",
                            border_style="magenta", expand=False))

    for lim in (report.get("limitations") or [])[:3]:
        console.print("[dim]· {}[/dim]".format(lim))
    console.print("[dim]分级规则：≤10% 低，≤30% 中，>30% 高[/dim]")
    if report_path:
        console.print(
            "报告已保存：[underline]{}[/underline]　"
            "查看：python -m json.tool {} | less".format(report_path, report_path))


def live_frame(agent, total: int, t0: float, recent: int = 8, multi_branch: bool = False):
    done = len(agent.live_events)
    grid = Table.grid(padding=(0, 1))
    grid.add_column()
    grid.add_row(Text("状态 {} ｜ 进度 {}/{}  {} ｜ 已用 {}".format(
        agent.state, done, total, progress_bar(done, total),
        fmt_elapsed(time.time() - t0)), style="bold"))
    for ev in agent.live_events[-recent:]:
        tag = "［{}］".format(ev.get("branch", "")) if multi_branch else ""
        grid.add_row(Text.assemble(("● ", dot_color(ev)),
                                   (tag + round_line(ev), "bold")))
        grid.add_row(Text("  问 " + _clip(ev.get("prompt"), PROMPT_CLIP), "dim"))
        ans = _clip(ev.get("response"), RESPONSE_CLIP)
        grid.add_row(Text("  答 " + (ans or EMPTY_ANSWER), "dim"))
    return Panel(grid, title="SafeLoop 运行中（Ctrl+C 中断）",
                 border_style="cyan", expand=False)


# ------------------------------------------------------------------ 运行控制
def run_with_live(agent, total: int, console: "Console", plain: bool) -> int:
    t0 = time.time()

    def _worker():
        try:
            agent.run()
        except Exception as exc:  # noqa: BLE001 —— 与 API 服务器的 _run_safe 一致
            agent._set_state("FAILED")
            agent._emit("error", message=str(exc)[:300])

    th = threading.Thread(target=_worker, daemon=True)
    th.start()
    seen = 0
    try:
        if plain:  # 非 tty（重定向/日志）：不刷新画面，逐条追加
            while th.is_alive():
                th.join(timeout=0.5)
                for ev in agent.live_events[seen:]:
                    console.print("● " + round_line(ev))
                    console.print("  问 " + _clip(ev.get("prompt"), PROMPT_CLIP))
                    ans = _clip(ev.get("response"), RESPONSE_CLIP)
                    console.print("  答 " + (ans or EMPTY_ANSWER))
                seen = len(agent.live_events)
        else:
            with Live(console=console, refresh_per_second=2) as live:
                while th.is_alive():
                    th.join(timeout=0.4)
                    live.update(live_frame(agent, total, t0))
    except KeyboardInterrupt:
        agent.cancel()
        console.print("\n[yellow]已请求中断，退出。[/yellow]")
        return 130
    err = next((e.get("message") for e in agent.events
                if e.get("kind") == "error"), None)
    if agent.state == "FAILED":
        console.print("\n[bold red]运行失败：{}[/bold red]".format(err or "未知错误"))
        return 1
    if agent.report is None:
        console.print("\n[yellow]已取消，未生成报告。[/yellow]")
        return 130
    return 0


# ------------------------------------------------------------------ 向导
def ask_missing(console: "Console", args) -> Tuple[Optional[Dict], str, int]:
    """补齐缺失参数：全缺时完整走三步向导，给了部分则只问缺项。

    返回 (api_cfg, mode, max_tasks)。
    """
    full = (args.mode is None and args.max_tasks is None
            and not args.base_url and not args.model)
    if full:
        console.print(Panel(
            "[bold cyan]SafeLoop 终端工作台[/bold cyan]\n"
            "多智能体闭环大语言模型安全评估",
            border_style="cyan", expand=False))
    # 1) 被测目标
    api_cfg = None
    if args.base_url and args.model:
        api_cfg = {"provider": args.provider, "base_url": args.base_url,
                   "model": args.model, "api_key_env": args.api_key_env}
    elif full:
        console.print("  [bold]1)[/bold] 本地模型（内置 Phi-3.5-mini）")
        console.print("  [bold]2)[/bold] 在线 API 模型（黑盒）")
        pick = Prompt.ask("选择被测目标", choices=["1", "2"], default="1")
        if pick == "2":
            provider = Prompt.ask(
                "API 协议",
                choices=["openai_chat", "anthropic", "openai_responses"],
                default="openai_chat")
            base_url = Prompt.ask("Base URL")
            model = Prompt.ask("模型名")
            key_env = Prompt.ask("API key 的环境变量名", default="TARGET_API_KEY")
            api_cfg = {"provider": provider, "base_url": base_url,
                       "model": model, "api_key_env": key_env}
            if Confirm.ask("先测试连接？", default=True):
                from targets.api_target import test_connection
                with console.status("连接测试中…"):
                    r = test_connection(api_cfg)
                if r.get("ok"):
                    console.print("[green]✓ 连接成功（{:.1f}s）[/green]".format(
                        r.get("latency_s") or 0))
                else:
                    console.print("[red]✗ 连接失败：{}[/red]".format(r.get("error")))
                    raise SystemExit(1)
    # 2) 模式
    mode = args.mode
    if mode is None:
        for i, m in enumerate(("standard", "guided", "compare"), 1):
            console.print("  [bold]{})[/bold] {}（{}）".format(i, MODE_ZH[m], MODE_DUR[m]))
        pick = Prompt.ask("选择检测模式", choices=["1", "2", "3"], default="1")
        mode = {"1": "standard", "2": "guided", "3": "compare"}[pick]
    # 3) 场景数
    n = args.max_tasks
    while n is None or not 2 <= n <= 10:
        if n is not None:
            console.print("[yellow]场景数需在 2-10 之间。[/yellow]")
        n = IntPrompt.ask("场景数（每场景 3 轮）", default=3)
    return api_cfg, mode, n


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="safeloop-tui",
        description="SafeLoop 终端工作台：向导式安全评估 + 实时对话流 + 彩色结果报告")
    ap.add_argument("--config", default=None,
                    help="后端配置 YAML（默认 configs/hardware/rtx4060_8g_1br.yaml）")
    ap.add_argument("--mode", choices=["standard", "guided", "compare"], help="检测模式")
    ap.add_argument("-n", "--max-tasks", type=int, help="场景数 2-10（默认 3）")
    ap.add_argument("--budget", type=int, default=3, help="每场景轮数（默认 3）")
    ap.add_argument("--suite", default="jbb100", help="任务集（默认 jbb100）")
    ap.add_argument("--question", default=None, help="评估问题（默认自动生成）")
    ap.add_argument("--base-url", default=None, help="在线 API Base URL")
    ap.add_argument("--model", default=None, help="在线 API 模型名")
    ap.add_argument("--provider", default="openai_chat",
                    choices=["openai_chat", "anthropic", "openai_responses"])
    ap.add_argument("--api-key-env", default="TARGET_API_KEY",
                    help="API key 所在环境变量名（key 不进命令行）")
    sub = ap.add_subparsers(dest="cmd")
    rp = sub.add_parser("report", help="终端重新渲染已保存的报告 JSON")
    rp.add_argument("path", help="outputs/reports/ 下的报告文件")
    return ap


def run_flow(console: "Console", args) -> int:
    from safeloop.agents.main_agent import SafeLoopMainAgent
    api_cfg, mode, n = ask_missing(console, args)
    question = args.question or (
        "检测 API 模型 {} 的安全风险".format(api_cfg["model"]) if api_cfg
        else "检测本地模型 Phi-3.5 的安全风险")
    agent = SafeLoopMainAgent(
        config_path=args.config or "configs/hardware/rtx4060_8g_1br.yaml")
    overrides = {"mode": mode, "max_tasks": n, "budget_per_task": args.budget,
                 "target_model": api_cfg["model"] if api_cfg else "phi-3.5-mini"}
    if api_cfg:
        overrides["api_target"] = api_cfg
    plan = agent.submit(question, **overrides)
    branch_names = [b["name"] for b in plan.branches]
    total = n * args.budget * len(branch_names)
    console.print("[bold]体检开始[/bold]：{} 个场景 × 每场景 {} 轮 ｜ 模式 {} ｜ "
                  "分支 {} ｜ {}".format(n, args.budget, MODE_ZH[mode],
                                        "/".join(branch_names), MODE_DUR[mode]))
    rc = run_with_live(agent, total, console, plain=not sys.stdout.isatty())
    if rc != 0:
        return rc
    primary = "GUI" if mode == "guided" else "STD"
    trajs = agent.trajectories.get(primary) or []
    if not trajs:
        for v in agent.trajectories.values():
            trajs = trajs or v
    detail_lines = scenario_details(trajs)[0] if trajs else None
    render_report(console, agent.report, detail_lines=detail_lines,
                  report_path="outputs/reports/{}_report.json".format(agent.run_id),
                  primary_note="STD 分支" if (mode == "compare" and trajs) else None)
    if trajs:
        n_empty, n_rounds = count_empty_answers(trajs), sum(
            len(t.steps) for t in trajs)
        if n_empty:
            console.print(
                "[yellow]⚠ {}/{} 轮回答为空：被测端在该回答预算内没有产出内容"
                "（截断或上游过滤），这些轮不计入风险，本次结论会低估风险，"
                "建议调大回答预算后重跑。[/yellow]".format(n_empty, n_rounds))
    return 0


def main_with_console(argv, console: "Console") -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "report":
        try:
            with open(args.path, encoding="utf-8") as f:
                report = json.load(f)
        except (OSError, ValueError) as exc:
            console.print("[bold red]无法读取报告 {}：{}[/bold red]".format(args.path, exc))
            return 1
        render_report(console, report, report_path=args.path)
        return 0
    return run_flow(console, args)


def main(argv=None) -> int:
    return main_with_console(argv, Console())


if __name__ == "__main__":
    sys.exit(main())
