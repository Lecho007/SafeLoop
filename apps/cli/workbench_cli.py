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
from safeloop.skills.transcript import (MODE_ZH, build_transcript,  # noqa: F401
                                        e_short, verdict_short)
SCOPE_ZH = {"sample": "抽样测试", "full": "完整测试", "single": "单场景测试"}
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
    """ASR@k（统一读取口径见 evaluation.metrics.asr_at_budget，W0-1）。

    返回 (值, k)：优先报告显式 asr_at_budget 字段（k 未知 → None）；
    其次 asr_at_k 曲线取满预算轮；兼容历史 float 形态。
    """
    if user_layer.get("asr_at_budget") is not None:
        return user_layer["asr_at_budget"], None
    m = user_layer.get("asr_at_k")
    if isinstance(m, dict) and m:
        keys = [x for x in m if str(x).isdigit()]
        if not keys:
            return None, None
        k = max(int(x) for x in keys)
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


def live_frame(r: Dict, agent, t0: float, recent: int = 8):
    """运行画面：状态行取自 RunManager 持久化进度，对话流取自活动 agent。"""
    done = r.get("steps_done", 0)
    total = max(1, r.get("total_steps", 1))
    grid = Table.grid(padding=(0, 1))
    grid.add_column()
    grid.add_row(Text("状态 {} ｜ 进度 {}/{}  {} ｜ 已用 {}".format(
        r.get("status"), done, total, progress_bar(done, total),
        fmt_elapsed(time.time() - t0)), style="bold"))
    events = (getattr(agent, "live_events", None) or []) if agent else []
    if not events:
        grid.add_row(Text("排队中 / 模型加载中…首轮对话完成后在此显示", "dim"))
        if r.get("status") == "QUEUED":
            grid.add_row(Text("（单 GPU 串行队列：前序任务完成后自动开始）", "dim"))
    multi = agent is not None and len(getattr(agent, "trajectories", {}) or {}) > 1
    for ev in events[-recent:]:
        tag = "［{}］".format(ev.get("branch", "")) if multi else ""
        grid.add_row(Text.assemble(("● ", dot_color(ev)),
                                   (tag + round_line(ev), "bold")))
        grid.add_row(Text("  问 " + _clip(ev.get("prompt"), PROMPT_CLIP), "dim"))
        ans = _clip(ev.get("response"), RESPONSE_CLIP)
        grid.add_row(Text("  答 " + (ans or EMPTY_ANSWER), "dim"))
    return Panel(grid, title="SafeLoop 运行中（Ctrl+C 取消）",
                 border_style="cyan", expand=False)


# ------------------------------------------------------------------ 运行控制
def run_with_live(mgr, run_id: str, console: "Console", plain: bool) -> int:
    """跟随 RunManager 队列中的 run：轮询持久化状态；Ctrl=C 走真取消。"""
    from safeloop.runs.manager import TERMINAL
    t0 = time.time()
    seen = 0
    try:
        if plain:  # 非 tty（重定向/日志）：不刷新画面，逐条追加
            while True:
                r = mgr.get_run(run_id)
                agent = mgr.get_agent(run_id)
                if agent:
                    for ev in agent.live_events[seen:]:
                        console.print("● " + round_line(ev))
                        console.print("  问 " + _clip(ev.get("prompt"), PROMPT_CLIP))
                        ans = _clip(ev.get("response"), RESPONSE_CLIP)
                        console.print("  答 " + (ans or EMPTY_ANSWER))
                    seen = len(agent.live_events)
                if r["status"] in TERMINAL:
                    break
                time.sleep(0.5)
        else:
            with Live(console=console, refresh_per_second=2) as live:
                while True:
                    r = mgr.get_run(run_id)
                    agent = mgr.get_agent(run_id)
                    live.update(live_frame(r, agent, t0))
                    if r["status"] in TERMINAL:
                        break
                    time.sleep(0.4)
    except KeyboardInterrupt:
        res = mgr.cancel(run_id)
        console.print("\n[yellow]已请求取消：{}[/yellow]".format(
            res.get("note", "当前调用结束或超时后生效，已完成结果保留。")))
        deadline = time.time() + 5
        while time.time() < deadline:
            if mgr.get_run(run_id)["status"] in TERMINAL:
                break
            time.sleep(0.2)
        return 130
    r = mgr.get_run(run_id)
    if r["status"] == "FAILED":
        console.print("\n[bold red]运行失败：{}[/bold red]".format(
            r.get("error") or "未知错误"))
        return 1
    if r["status"] == "CANCELLED":
        console.print("\n[yellow]已取消。已完成的部分结果保留在历史中"
                      "（可用 resume 子命令续跑）。[/yellow]")
        return 130
    return 0


# ------------------------------------------------------------------ 向导
def _suite_rows(args) -> List[Dict]:
    """读取任务集原始行（task_id/goal/harm_category/metadata），供场景菜单与校验。"""
    suite = getattr(args, "suite", None) or "jbb100"
    if suite == "jbb100":
        path = "data/tasks/jbb100_full.jsonl"
    elif os.path.exists(suite):
        path = suite
    else:
        path = "data/tasks/{}.jsonl".format(suite)
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def resolve_scenario_id(user_input: str, rows: List[Dict]) -> str:
    """场景输入归一化：'50'→'JBB-0050'，大小写不敏感；找不到抛 ValueError。"""
    u = (user_input or "").strip().upper()
    if u.isdigit():
        u = "JBB-{:04d}".format(int(u))
    for r in rows:
        if str(r.get("task_id", "")).upper() == u:
            return r["task_id"]
    raise ValueError("任务集中找不到场景 {}（示例: {}）".format(
        user_input, "、".join(str(r.get("task_id")) for r in rows[:3])))


def estimate_duration(total_rounds: int) -> str:
    """按轮数估算时长（实测单轮 0.7-1.5 分钟：红方生成+被测回答+裁判）。"""
    lo, hi = total_rounds * 0.7, total_rounds * 1.5

    def fmt(m: float) -> str:
        return "{:.1f} 小时".format(m / 60.0) if m >= 90 else "{:.0f} 分钟".format(m)

    return "约 {}-{}".format(fmt(lo), fmt(hi))


def pick_scenario(console: "Console", rows: List[Dict]) -> str:
    """单场景选择：先选危害类别，再选具体场景。"""
    by_cat: Dict[str, List[Dict]] = {}
    for r in rows:
        by_cat.setdefault(r.get("harm_category") or "未分类", []).append(r)
    cats = sorted(by_cat)
    console.print("选择危害类别：")
    for i, c in enumerate(cats, 1):
        zh = CATEGORY_ZH.get(c.replace("JBB:", ""), c)
        console.print("  [bold]{})[/bold] {}（{} 个场景）".format(i, zh, len(by_cat[c])))
    pick = Prompt.ask("类别编号", choices=[str(i) for i in range(1, len(cats) + 1)])
    tasks = by_cat[cats[int(pick) - 1]]
    console.print("选择场景：")
    for i, r in enumerate(tasks, 1):
        console.print("  [bold]{})[/bold] {} ｜ {}".format(
            i, r.get("task_id"), (r.get("goal") or "")[:56]))
    pick2 = Prompt.ask("场景编号", choices=[str(i) for i in range(1, len(tasks) + 1)])
    return str(tasks[int(pick2) - 1]["task_id"])


def ask_missing(console: "Console", args) -> Dict:
    """补齐缺失参数：全缺时完整走向导，给了部分则只问缺项。

    返回 {api_cfg, mode, scope, n_tasks, scenario_id, budget}。
    scope: sample=跨类别抽样 n 个场景 / full=任务集全部场景 / single=指定单场景。
    """
    full = (args.mode is None and args.scope is None and args.max_tasks is None
            and args.scenario is None and not args.base_url and not args.model)
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
    # 2) 测试范围
    rows = _suite_rows(args)
    scenario_id = None
    if args.scenario:
        scope = "single"
        scenario_id = resolve_scenario_id(args.scenario, rows)
    elif args.scope:
        scope = args.scope
    elif full:
        console.print("  [bold]1)[/bold] 抽样测试 — 跨危害类别均匀抽取若干场景（推荐）")
        console.print("  [bold]2)[/bold] 完整测试 — 任务集全部 {} 个场景（耗时长）".format(len(rows)))
        console.print("  [bold]3)[/bold] 单场景测试 — 指定一个场景反复多轮，深度测试")
        pick = Prompt.ask("选择测试范围", choices=["1", "2", "3"], default="1")
        scope = {"1": "sample", "2": "full", "3": "single"}[pick]
    else:
        scope = "sample"
    # 3) 场景范围参数
    n_tasks = None
    if scope == "sample":
        n_tasks = args.max_tasks
        while n_tasks is None or not 2 <= n_tasks <= 20:
            if n_tasks is not None:
                console.print("[yellow]场景数需在 2-20 之间。[/yellow]")
            n_tasks = IntPrompt.ask("场景数（跨类别抽样）", default=3)
    elif scope == "single":
        if scenario_id is None:
            scenario_id = pick_scenario(console, rows)
        else:
            row = next(r for r in rows if r["task_id"] == scenario_id)
            console.print("单场景：{} ｜ {}".format(
                scenario_id, (row.get("goal") or "")[:60]))
    # 4) 模式
    mode = args.mode
    if mode is None:
        for i, m in enumerate(("standard", "guided", "compare"), 1):
            console.print("  [bold]{})[/bold] {}".format(i, MODE_ZH[m]))
        pick = Prompt.ask("选择检测模式", choices=["1", "2", "3"], default="1")
        mode = {"1": "standard", "2": "guided", "3": "compare"}[pick]
    # 5) 每场景轮数（完整向导时询问；带参数跑默认 3）
    budget = args.budget
    if budget is None:
        if full:
            while budget is None or not 1 <= budget <= 10:
                budget = IntPrompt.ask("每个场景查询轮数", default=3)
        else:
            budget = 3
    elif not 1 <= budget <= 10:
        console.print("[yellow]轮数需在 1-10 之间，已修正为 3。[/yellow]")
        budget = 3
    return {"api_cfg": api_cfg, "mode": mode, "scope": scope,
            "n_tasks": n_tasks, "scenario_id": scenario_id, "budget": budget}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="safeloop-tui",
        description="SafeLoop 终端工作台：向导式安全评估 + 实时对话流 + 彩色结果报告")
    ap.add_argument("--config", default=None,
                    help="后端配置 YAML（默认 configs/hardware/rtx4060_8g_1br.yaml）")
    ap.add_argument("--mode", choices=["standard", "guided", "compare"], help="检测模式")
    ap.add_argument("--scope", choices=["sample", "full", "single"],
                    help="测试范围：sample=跨类别抽样 n 个（默认）/ full=全部场景 / single=单场景")
    ap.add_argument("--scenario", default=None,
                    help="单场景测试：任务 ID（JBB-0050）或编号（50）")
    ap.add_argument("-n", "--max-tasks", type=int, help="场景数 2-20（默认 3，仅 sample 范围）")
    ap.add_argument("--budget", type=int, default=None, help="每场景查询轮数 1-10（默认 3）")
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
    sub.add_parser("history", help="列出运行历史（含导入的旧 run）")
    rs = sub.add_parser("resume", help="续跑已取消/失败的 run（从检查点恢复）")
    rs.add_argument("run_id")
    return ap


def _open_manager():
    from safeloop.runs.manager import RunManager
    return RunManager()


def _render_finished(console: "Console", mgr, run_id: str, mode: str) -> None:
    """终态后的统一呈现：报告 + 空回答警示 + transcript 路径（零 GPU 回放装载）。"""
    from safeloop.skills.replay_loader import load_prerun_as_agent
    a = load_prerun_as_agent(run_id)
    primary = "GUI" if mode == "guided" else "STD"
    trajs = a.trajectories.get(primary) or []
    if not trajs:
        for v in a.trajectories.values():
            trajs = trajs or v
    detail_lines = scenario_details(trajs)[0] if trajs else None
    render_report(console, a.report, detail_lines=detail_lines,
                  report_path="outputs/reports/{}_report.json".format(run_id),
                  primary_note="STD 分支" if (mode == "compare" and trajs) else None)
    if trajs:
        n_empty, n_rounds = count_empty_answers(trajs), sum(
            len(t.steps) for t in trajs)
        if n_empty:
            console.print(
                "[yellow]⚠ {}/{} 轮回答为空：被测端在该回答预算内没有产出内容"
                "（截断或上游过滤），这些轮不计入风险，本次结论会低估风险，"
                "建议调大回答预算后重跑。[/yellow]".format(n_empty, n_rounds))
    r = mgr.get_run(run_id)
    arts = {x["kind"]: x["path"] for x in r.get("artifacts", [])}
    if "transcript" in arts:
        console.print("完整对话记录（问答全文、无截断）：[underline]{}[/underline]".format(
            arts["transcript"]))


def run_flow(console: "Console", args) -> int:
    from safeloop.runs.manager import RunSpec
    sel = ask_missing(console, args)
    api_cfg, mode = sel["api_cfg"], sel["mode"]
    scope, n_tasks = sel["scope"], sel["n_tasks"]
    scenario_id, budget = sel["scenario_id"], sel["budget"]
    question = args.question or (
        "检测 API 模型 {} 的安全风险".format(api_cfg["model"]) if api_cfg
        else "检测本地模型 Phi-3.5 的安全风险")
    mgr = _open_manager()
    spec = RunSpec(
        mode=mode, scope=scope,
        scenario_ids=[scenario_id] if scenario_id else [],
        rounds=budget, sample_size=n_tasks or 3, suite=args.suite,
        question=question,
        target_model=api_cfg["model"] if api_cfg else "phi-3.5-mini",
        api_target=api_cfg,
        config_path=args.config or "configs/hardware/rtx4060_8g_1br.yaml")
    run_id = mgr.submit(spec)
    n_effective = 1 if scope == "single" else (n_tasks if scope == "sample" else 100)
    total = n_effective * budget * (2 if mode == "compare" else 1)
    est = estimate_duration(total)
    scope_desc = {"sample": "抽样 {} 个场景（跨类别）".format(n_tasks),
                  "full": "全部场景", "single": "单场景 {}".format(scenario_id)}[scope]
    if scope == "full":
        console.print("[yellow]⚠ 完整测试：约 {} 个场景 × 每场景 {} 轮 ≈ {} 轮查询，{}。"
                      "建议先用抽样测试验证链路后再跑全量。[/yellow]".format(
                          n_effective, budget, total, est))
    console.print("[bold]体检已排队[/bold]：{} ｜ 每场景 {} 轮 ｜ 模式 {} ｜ {} ｜ {}"
                  .format(scope_desc, budget, MODE_ZH[mode], est, run_id))
    rc = run_with_live(mgr, run_id, console, plain=not sys.stdout.isatty())
    if rc == 0:
        _render_finished(console, mgr, run_id, mode)
    return rc


def _cmd_history(console: "Console") -> int:
    mgr = _open_manager()
    rows = mgr.list_runs(limit=30)
    if not rows:
        console.print("暂无历史运行。")
        return 0
    t = Table(title="运行历史（最近 {}）".format(len(rows)))
    for col, kw in (("run_id", {"no_wrap": True}), ("状态", {}),
                    ("模式", {}), ("范围", {}), ("目标", {}),
                    ("轮数", {"justify": "right"}), ("进度", {"justify": "right"}),
                    ("创建时间", {})):
        t.add_column(col, **kw)
    for r in rows:
        t.add_row(r["run_id"], r["status"], r["mode"], r["scope"],
                  str(r["target"] or ""),
                  "{}/{}".format(r["steps_done"], r["total_steps"] or "?"),
                  "{}".format(r["rounds"]),
                  str(r["created_at"] or "")[:19])
    console.print(t)
    console.print("[dim]续跑：python apps/cli/workbench_cli.py resume <run_id>"
                  " ｜ 重看报告：report outputs/reports/<run_id>_report.json[/dim]")
    return 0


def _cmd_resume(console: "Console", run_id: str) -> int:
    mgr = _open_manager()
    try:
        mgr.resume(run_id)
    except (KeyError, ValueError) as exc:
        console.print("[bold red]{}[/bold red]".format(exc))
        return 1
    r = mgr.get_run(run_id)
    console.print("[bold]已重新排队[/bold]：{}（从检查点续跑）".format(run_id))
    rc = run_with_live(mgr, run_id, console, plain=not sys.stdout.isatty())
    if rc == 0:
        _render_finished(console, mgr, run_id, r.get("spec", {}).get("mode", "standard"))
    return rc


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
    if args.cmd == "history":
        return _cmd_history(console)
    if args.cmd == "resume":
        return _cmd_resume(console, args.run_id)
    try:
        return run_flow(console, args)
    except (ValueError, OSError) as exc:
        console.print("[bold red]{}[/bold red]".format(exc))
        return 1


def main(argv=None) -> int:
    return main_with_console(argv, Console())


if __name__ == "__main__":
    sys.exit(main())
