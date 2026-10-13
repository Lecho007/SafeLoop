# -*- coding: utf-8 -*-
"""完整对话存档（roadmap P3：无截断的逐轮问答全文，产品层统一实现）。

所有入口（CLI / GUI / API）经 RunManager 在 run 收尾时统一落盘
outputs/reports/{run_id}_transcript.md。
"""
from typing import List

from safeloop.skills.terms import CATEGORY_ZH, STRATEGY_ZH

MODE_ZH = {"standard": "标准检测", "guided": "智能引导", "compare": "对比检测"}


def _step_ok(s) -> bool:
    ev = getattr(s, "external_evaluation", None)
    return bool(ev and getattr(ev, "success", False))


def verdict_short(s) -> str:
    meta = getattr(s.judge_output, "metadata", None) or {}
    return (meta.get("advancement") or meta.get("safety")
            or getattr(s.judge_output, "outcome", None) or "—")


def e_short(s) -> str:
    return "风险确认" if _step_ok(s) else "未触发"


def build_transcript(run_id: str, mode: str, branches) -> str:
    """完整对话存档（无截断）：每场景逐轮的红方问题/被测回答全文 + 判别 + E 结论。"""
    lines = ["# SafeLoop 完整对话记录", "",
             "- run: {} ｜ 模式: {}".format(run_id, MODE_ZH.get(mode, mode)),
             "- 内容：全部场景、逐轮红方问题与被测回答**全文**（不截断）、裁判判别、独立评审结论", ""]
    for branch, trajs in branches:
        lines += ["", "---", "", "## 分支 {}（{} 个场景）".format(branch, len(trajs)), ""]
        for n, t in enumerate(trajs, 1):
            cat = (getattr(t.task, "harm_category", "") or "").replace("JBB:", "")
            zh = CATEGORY_ZH.get(cat, cat or "未分类")
            first = next((k + 1 for k, s in enumerate(t.steps) if _step_ok(s)), None)
            dom = (getattr(t.task, "metadata", {}) or {}).get("feedback_observability") or "—"
            tag = "第{}轮触发".format(first) if first else "未触发"
            lines += ["## [{}/{}] {} ｜ {}（{}） ｜ 域: {}".format(
                n, len(trajs), t.task.task_id, zh, tag, dom), ""]
            lines += ["**测试目标（全程固定）**：{}".format(
                getattr(t.task, "goal", "") or "（未记录）"), ""]
            for s in t.steps:
                strat = getattr(s.action, "strategy", None)
                lines += ["### R{} ｜ {} ｜ 判别: {} ｜ E: {}".format(
                    getattr(s, "round_id", 0) + 1, STRATEGY_ZH.get(strat, strat or "?"),
                    verdict_short(s), e_short(s)), "", "**红方问题**", "", "```text",
                    (getattr(s.action, "prompt", "") or "（空）"), "```", "",
                    "**被测回答**", "", "```text"]
                ans = (getattr(s.response, "text", "") or "").strip()
                lines += [ans if ans else
                          "（空回答——回答预算内无最终内容：多为思考耗尽 finish=length 或上游拦截）",
                          "```", ""]
    return "\n".join(lines) + "\n"
