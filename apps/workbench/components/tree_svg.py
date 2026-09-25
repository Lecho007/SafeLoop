# -*- coding: utf-8 -*-
"""决策树 SVG 组件（系统路由树 + 单任务决策路径树，纯字符串生成，无 streamlit 依赖）。"""
from typing import Any, Dict, List, Optional

# 设计令牌（v2 融合版）
DEEP, PANEL, TRACE = "#f7f8fb", "#ffffff", "#dfe5ee"
LENS, RISK, WARN, SAFE, LIVE = "#2f6feb", "#e6465f", "#b66a08", "#16875d", "#7556d8"
SIGNAL_HEX = {"risk": RISK, "warn": WARN, "safe": SAFE, None: "#9db0c4"}

ACTION_ZH = {"KEEP": "保持", "REFINE": "细化", "SWITCH": "换策略",
             "REALIGN": "回正", "UNCERTAIN": "不确定"}
STRATEGY_ZH = {"direct": "直接提问", "roleplay": "角色扮演",
               "reframing": "换角度提问", "obfuscation": "混淆表述",
               "multi_turn": "分步引导"}


# ============================================================ 系统路由树
def system_routing_tree(active_domain: Optional[str] = None,
                        active_role: Optional[str] = None) -> str:
    """系统级路由树（Tab 0 hero 下方；Tab 1 实况联动复用）。

    active_domain: "content"/"goal"（任务加载时所属分支高亮）
    active_role:   "judge"/"control"/"evaluator"（对应节点脉冲）
    """
    def glow(node_id: str) -> str:
        if active_role and active_role in node_id:
            return 'filter="url(#rglow)"'
        return ""

    def dim(domain: str) -> str:
        if active_domain and active_domain != domain:
            return ' opacity="0.35"'
        return ""

    c_dim, g_dim = dim("content"), dim("goal")
    return """<svg viewBox="0 0 860 400" width="100%" class="rt-svg">
<defs>
 <filter id="rglow" x="-60%" y="-60%" width="220%" height="220%">
  <feDropShadow dx="0" dy="0" stdDeviation="5" flood-color="{lens}"/></filter>
 <marker id="rar" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
  <path d="M0,0 L6,3 L0,6 z" fill="{trace}"/></marker>
</defs>
<style>
 .rt-n{{fill:{panel};stroke:{trace};stroke-width:1.3}}
 .rt-t{{font-size:14px;font-weight:600;fill:#172033}}
 .rt-s{{font-size:10.5px;fill:#67738a}}
 .rt-e{{stroke:{trace};stroke-width:1.8;fill:none}}
 .rt-hot{{stroke:{lens};stroke-width:1.6}}
 .rt-flow{{stroke:{lens};stroke-width:2.4;stroke-linecap:round;
   stroke-dasharray:5 13;opacity:0;fill:none;
   filter:drop-shadow(0 0 4px rgba(47,111,235,.5));
   animation:rtflow 1s linear infinite, rtrelay 4.2s infinite}}
 @keyframes rtflow{{to{{stroke-dashoffset:-18}}}}
 @keyframes rtrelay{{0%{{opacity:0}}4%{{opacity:1}}14%{{opacity:1}}
   20%{{opacity:0}}100%{{opacity:0}}}}
</style>
<path class="rt-e" d="M430 60 L 200 105"/><path class="rt-e" d="M430 60 L 660 105"/>
<path class="rt-e" d="M200 160 L 200 210"/><path class="rt-e" d="M660 160 L 660 210"/>
<path class="rt-e" d="M200 265 L 330 300"/><path class="rt-e" d="M660 265 L 530 300"/>
<path class="rt-e" d="M430 330 L 430 352"/>
<path class="rt-flow" style="animation-delay:0s,0s" d="M430 60 L {dl} 105"/>
<path class="rt-flow" style="animation-delay:0s,.5s" d="M{dl} 160 L {dl} 210"/>
<path class="rt-flow" style="animation-delay:0s,1.1s" d="M{dl} 265 L {dcx} 300"/>
<path class="rt-flow" style="animation-delay:0s,1.8s" d="M{dcx} 330 L 430 352"/>
<rect class="rt-n" x="330" y="18" width="200" height="44" rx="9" {glow_root}/>
<text x="430" y="37" text-anchor="middle" class="rt-t">安全任务池</text>
<text x="430" y="53" text-anchor="middle" class="rt-s">内置安全场景（original goal 固定）</text>
<g{c_dim}><rect class="rt-n" x="110" y="107" width="180" height="54" rx="9"/>
<text x="200" y="128" text-anchor="middle" class="rt-t">内容可观测域 70%</text>
<text x="200" y="146" text-anchor="middle" class="rt-s">虚假信息 入侵 隐私 欺诈 …</text></g>
<g{g_dim}><rect class="rt-n" x="570" y="107" width="180" height="54" rx="9"/>
<text x="660" y="128" text-anchor="middle" class="rt-t">目标合规域 30%</text>
<text x="660" y="146" text-anchor="middle" class="rt-s">冒充专家 经济损害 政务操纵</text></g>
<g{c_dim}><rect class="rt-n rt-hot" x="110" y="212" width="180" height="54" rx="9" id="judge-content" {glow_jc}/>
<text x="200" y="233" text-anchor="middle" class="rt-t">内容安全裁判</text>
<text x="200" y="251" text-anchor="middle" class="rt-s">内容风险 + 拒绝信号</text></g>
<g{g_dim}><rect class="rt-n rt-hot" x="570" y="212" width="180" height="54" rx="9" id="judge-goal" {glow_jg}/>
<text x="660" y="233" text-anchor="middle" class="rt-t">目标推进裁判</text>
<text x="660" y="251" text-anchor="middle" class="rt-s">有害目标推进 + 极性</text></g>
<g{c_dim}><rect class="rt-n" x="110" y="272" width="180" height="44" rx="9" {glow_ctrl_c}/>
<text x="200" y="290" text-anchor="middle" class="rt-s">观察记录（默认）</text>
<text x="200" y="304" text-anchor="middle" class="rt-s">引导反馈（实验）</text></g>
<g{g_dim}><rect class="rt-n" x="570" y="272" width="180" height="44" rx="9" {glow_ctrl_g}/>
<text x="660" y="290" text-anchor="middle" class="rt-s">观察记录（默认）</text>
<text x="660" y="304" text-anchor="middle" class="rt-s">引导反馈（实验）</text></g>
<rect class="rt-n" x="330" y="300" width="200" height="44" rx="9" {glow_eval}/>
<text x="430" y="318" text-anchor="middle" class="rt-t">独立评审官</text>
<text x="430" y="334" text-anchor="middle" class="rt-s">离线裁决，闭环外</text>
<text x="430" y="392" text-anchor="middle" class="rt-s" fill="#7E9AB0">
安全任务 → 专业裁判 → 观察或引导 → 完整轨迹 → 独立评审（默认观察不干预，引导为实验能力）</text>
</svg>""".format(lens=LENS, panel=PANEL, trace=TRACE,
                dl=(660 if active_domain == "goal" else 200),
                dcx=(530 if active_domain == "goal" else 330),
                glow_root=glow("root"),
                glow_jc=glow("judge-content"), glow_jg=glow("judge-goal"),
                glow_ctrl_c=glow("control-content"),
                glow_ctrl_g=glow("control-goal"),
                glow_eval=glow("evaluator"),
                c_dim=c_dim, g_dim=g_dim)


# ============================================================ 单任务决策路径树
def decision_path_tree(rounds: List[Dict[str, Any]], verdict: Optional[str] = None,
                       live: bool = False,
                       trigger_round: Optional[int] = None,
                       progress: Optional[int] = None) -> str:
    """逐轮决策路径：节点=轮次（策略+信号色），边=决策动作。

    rounds: tree_model 产出的节点列表；live=True 时给活跃节点加脉冲。
    progress（演示模式）：先渲染完整骨架（暗色），已完成的前 progress 个节点
    及其之间的边点亮——已完成的边带流动光效，表示决策走到了哪里。
    """
    if not rounds:
        return ("<div style='color:#67738a;padding:20px;text-align:center'>"
                "决策树将在任务开始后逐轮生长</div>")
    n = len(rounds)
    w, h = max(760, n * 180 + 80), 240
    gap = (w - 120) / max(1, n)
    parts = ['<svg viewBox="0 0 {} {}" width="100%">'.format(w, h),
             '<defs><filter id="dglow" x="-60%" y="-60%" width="220%" height="220%">'
             '<feDropShadow dx="0" dy="0" stdDeviation="6" flood-color="{}"/>'
             '</filter></defs>'.format(LENS),
             '<style>.dn{fill:%s;stroke:%s;stroke-width:1.5}'
             '.dn.done{fill:%s;stroke:%s;stroke-width:2}'
             '.dt{font-size:13px;font-weight:600;fill:#172033}'
             '.ds{font-size:11px;fill:#67738a}'
             '.de{stroke:%s;stroke-width:2;fill:none}'
             '.de.done{stroke:%s;stroke-width:2.4;'
             'stroke-dasharray:6 12;animation:deflow 1s linear infinite;'
             'filter:drop-shadow(0 0 4px rgba(47,111,235,.5))}'
             '@keyframes deflow{to{stroke-dashoffset:-18}}'
             '.dl{font-size:12px;font-weight:600;fill:%s}'
             '.dl.dim{fill:#9db0c4}</style>'
             % (PANEL, TRACE, "#eef5ff", LENS, "#c9d6e6", LENS, LENS)]
    for i, nd in enumerate(rounds):
        cx = 70 + int(gap * i)
        sig = SIGNAL_HEX.get(nd.get("signal"))
        state = nd.get("state", "decided")
        done = (progress is not None and i < progress)
        stroke = sig if (done or state in ("judged", "decided")
                         and progress is None) else TRACE
        if progress is not None and not done:
            stroke = "#c9d6e6"
        active = ' filter="url(#dglow)"' if (live and state in ("red",) and
                                            i == len(rounds) - 1) else ""
        node_cls = ' class="dn done"' if done else ' class="dn"'
        parts.append('<circle cx="{}" cy="70" r="30" {} fill="{}" stroke="{}" '
                     'stroke-width="2.4" {}/>'.format(
                         cx, node_cls, "#eef5ff" if done else PANEL,
                         stroke, active))
        if nd.get("signal"):
            parts.append('<circle cx="{}" cy="70" r="8" fill="{}"/>'
                         .format(cx, sig))
        if trigger_round and nd.get("round") == trigger_round:
            parts.append('<circle cx="{}" cy="70" r="36" fill="none" '
                         'stroke="{}" stroke-width="2" stroke-dasharray="4 4"/>'
                         '<text x="{}" y="34" text-anchor="middle" fill="{}" '
                         'font-size="11" font-weight="700">触发</text>'
                         .format(cx, RISK, cx, RISK))
        parts.append('<text x="{}" y="120" text-anchor="middle" class="dt">第{}轮</text>'
                     .format(cx, nd.get("round", i + 1)))
        strat = nd.get("strategy")
        if strat:
            parts.append('<text x="{}" y="138" text-anchor="middle" class="ds">{}</text>'
                         .format(cx, STRATEGY_ZH.get(strat, strat)))
        sigtxt = {"risk": "推进显著", "warn": "部分推进", "safe": "未推进"}.get(
            nd.get("signal"), "判定中" if state == "red" else "")
        if sigtxt:
            parts.append('<text x="{}" y="156" text-anchor="middle" class="ds" '
                         'fill="{}">{}</text>'.format(cx, sig, sigtxt))
        if i < n - 1 and nd.get("action"):
            act = nd["action"]
            zh = ACTION_ZH.get(act, act)
            x1, x2 = cx + 32, cx + int(gap) - 32
            edge_done = (progress is not None and i + 1 < progress)
            ecls = "de done" if edge_done else ("de" if progress is None else "de")
            parts.append('<path class="{}" d="M{} 70 L {} 70"/>'
                         .format(ecls, x1, x2))
            lcls = "dl dim" if (progress is not None and not edge_done) else "dl"
            parts.append('<text x="{}" y="60" text-anchor="middle" class="{}">{}</text>'
                         .format((x1 + x2) // 2, lcls, zh))
    if verdict:
        vc = RISK if "风险" in verdict else SAFE
        parts.append('<rect x="{}" y="185" width="150" height="34" rx="17" fill="{}" '
                     'fill-opacity="0.16" stroke="{}" stroke-width="1.5"/>'
                     .format(w - 170, vc, vc))
        parts.append('<text x="{}" y="207" text-anchor="middle" fill="{}" '
                     'font-size="14" font-weight="700">⚖️ {}</text>'
                     .format(w - 95, vc, verdict))
    parts.append('<defs><marker id="dar" markerWidth="8" markerHeight="8" refX="6" '
                 'refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 z" fill="{}"/>'
                 '</marker></defs>'.format(TRACE))
    parts.append("</svg>")
    return "".join(parts)
