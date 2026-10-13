# -*- coding: utf-8 -*-
"""经验块渲染（roadmap A1）：把长期记忆检索结果渲染进红方模板。

硬约束（§13 不变量）：round 0（state.history 为空）**永不注入经验**——
保证跨条件 p0 逐字一致，记忆只在 round 1+ 与反馈/历史一起生效。
经验只有"过程观察"（outcome_proxy），永不包含独立评估结论。
"""

SUMMARY_MAX = 160


def _clip(text, limit=SUMMARY_MAX):
    text = (str(text or "")).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def build_experience_block(success_cases, failure_cases, round0: bool,
                           empty_text="(none)") -> str:
    """round0=True 或无经验 → empty_text；否则渲染为紧凑经验条目。"""
    if round0:
        return empty_text          # §13：round-0 上下文零差异
    items = []
    for case in list(success_cases or [])[:2]:
        items.append(_render_case(case, positive=True))
    for case in list(failure_cases or [])[:2]:
        items.append(_render_case(case, positive=False))
    if not items:
        return empty_text
    return "\n".join(items)


def _render_case(case, positive: bool) -> str:
    strategy = getattr(case, "strategy", "") or "?"
    summary = _clip(getattr(case, "strategy_summary", ""))
    obs = _clip(getattr(case, "observation_summary", ""))
    outcome = getattr(case, "outcome_proxy", "") or ""
    tag = "SEEMED USEFUL (observation only, not a success label)" if positive \
        else "LOW YIELD (repeated exploration of little value)"
    return ("- [{strategy}] {outcome} | {summary} | observed: {obs} | {tag}"
            .format(strategy=strategy, outcome=outcome, summary=summary,
                    obs=obs, tag=tag))
