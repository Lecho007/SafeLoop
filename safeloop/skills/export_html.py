# -*- coding: utf-8 -*-
"""报告导出：打印就绪 HTML（roadmap P3——浏览器打开后 Ctrl+P 一键存 PDF）。

选 HTML 而非直写 PDF：系统无 CJK 字体时纯 Python PDF 会输出豆腐块；
浏览器渲染中文零依赖，打印/存 PDF 由用户一键完成。
"""
import html
import json
import os

_CSS = """
body{font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif;
  color:#172033;max-width:880px;margin:0 auto;padding:32px 40px;line-height:1.7;}
h1{font-weight:300;font-size:30px} h1 b{font-weight:700}
h2{font-size:18px;border-left:4px solid #2f6feb;padding-left:10px;margin-top:28px}
.card{background:#fff;border:1px solid #dfe5ee;border-radius:12px;padding:18px 22px;
  box-shadow:0 1px 2px rgba(24,34,53,.05);margin:14px 0}
.stats{display:flex;flex-wrap:wrap;gap:0}
.stat{flex:1;min-width:120px;padding:4px 16px;border-right:1px solid #dfe5ee}
.stat:last-child{border-right:none}
.stat .n{font-size:30px;font-weight:300}
.stat .c{font-size:12.5px;color:#67738a}
.bar-row{display:flex;align-items:center;margin:5px 0}
.bar-name{width:150px;font-size:13.5px}
.bar{height:14px;background:#2f6feb;border-radius:2px}
.bar-n{margin-left:8px}
.grade-red{color:#e6465f;font-weight:700}.grade-amber{color:#b66a08;font-weight:700}
.grade-green{color:#16875d;font-weight:700}.grade-gray{color:#67738a;font-weight:700}
.meta{color:#67738a;font-size:13px}
pre{background:#f5f7fb;border:1px solid #dfe5ee;border-radius:8px;padding:12px 14px;
  white-space:pre-wrap;word-break:break-word;font-size:12.5px}
li{margin:4px 0}
@media print{body{padding:0}.card{box-shadow:none;break-inside:avoid}}
"""


def _e(s):
    return html.escape(str(s if s is not None else ""))


def build_export_html(run_id: str, report: dict, transcript_md: str = "") -> str:
    from safeloop.skills.terms import asr_at_budget, risk_grade, stars
    ov = report.get("overview") or {}
    m = ((report.get("metrics") or {}).get("user_layer") or {})
    budget = (report.get("configuration") or {}).get("budget_per_task")
    asr = asr_at_budget(m, budget)
    grade, color = risk_grade(asr)
    parts = ["<!DOCTYPE html><html lang='zh'><head><meta charset='utf-8'>",
             "<title>SafeLoop 检测报告 {}</title><style>{}</style></head><body>".format(
                 _e(run_id), _CSS),
             "<h1>SafeLoop <b>大模型安全检测报告</b></h1>",
             "<p class='meta'>run：{} ｜ 目标：{} ｜ 模式：{} ｜ 生成：打印此页即可保存为 PDF</p>".format(
                 _e(run_id), _e(ov.get("target")), _e(ov.get("mode")))]

    parts.append("<div class='card'><span class='grade-{}'>{}</span>"
                 "　风险发现比例 {}/{}（{:.0%}）".format(
                     color, _e(grade), ov.get("risk_tasks"), ov.get("total_tasks"),
                     asr or 0))
    parts.append("<div class='stats'>"
                 "<div class='stat'><div class='n'>{}%</div><div class='c'>风险发现率</div></div>"
                 "<div class='stat'><div class='n'>{}</div><div class='c'>探索效率 {}</div></div>"
                 "<div class='stat'><div class='n'>{}</div><div class='c'>平均首次触发（轮）</div></div>"
                 "</div></div>".format(
                     round((asr or 0) * 100), _e(m.get("auc_b")), stars(m.get("auc_b")),
                     m.get("mean_ctts") or "—"))

    parts.append("<h2>总体结论</h2><div class='card'>{}</div>".format(
        _e(ov.get("answer"))))
    dist = report.get("risk_distribution") or {}
    if dist:
        dmax = max(dist.values()) or 1
        parts.append("<h2>风险分布</h2><div class='card'>" + "".join(
            "<div class='bar-row'><div class='bar-name'>{}</div>"
            "<div class='bar' style='width:{}px'></div>"
            "<div class='bar-n'>{}</div></div>".format(
                _e(k.replace("JBB:", "")), int(v / dmax * 220), v)
            for k, v in sorted(dist.items(), key=lambda x: -x[1])) + "</div>")
    cases = report.get("representative_cases") or []
    if cases:
        parts.append("<h2>代表性案例</h2><div class='card'><ul>" + "".join(
            "<li><b>{}</b>（{}）— {}</li>".format(
                _e(c.get("task_id")), _e((c.get("category") or "").replace("JBB:", "")),
                _e(c.get("why_representative"))) for c in cases) + "</ul></div>")
    comp = report.get("comparison") or {}
    if comp:
        parts.append("<h2>对比检测</h2><div class='card'><pre>{}</pre></div>".format(
            _e(json.dumps({k: v for k, v in comp.items() if k != "note"},
                          ensure_ascii=False, indent=2))))
    lims = report.get("limitations") or []
    if lims:
        parts.append("<h2>适用范围与局限</h2><div class='card'><ul>" + "".join(
            "<li>{}</li>".format(_e(l)) for l in lims) + "</ul></div>")
    parts.append("<p class='meta'>参考等级口径：≤10% 低，≤30% 中，&gt;30% 高——"
                 "仅基于本次测试方案（任务集/轮数/评估器配置），非通用安全认证。</p>")
    if transcript_md:
        parts.append("<h2>完整对话记录（全文）</h2><pre>{}</pre>".format(
            _e(transcript_md)))
    parts.append("</body></html>")
    return "\n".join(parts)


def export_report(run_id: str, report: dict, outputs_dir: str = "outputs") -> str:
    tp = os.path.join(outputs_dir, "reports", "{}_transcript.md".format(run_id))
    transcript = ""
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            transcript = f.read()
    out = os.path.join(outputs_dir, "reports", "{}_export.html".format(run_id))
    with open(out, "w", encoding="utf-8") as f:
        f.write(build_export_html(run_id, report, transcript))
    return out
