# -*- coding: utf-8 -*-
"""终端工作台单测：纯渲染层（判别/明细/分级/分布/对比/进度条）+ report 子命令。

零 GPU：全部基于 dict / SimpleNamespace 桩，不触碰引擎与模型。
"""
import io
import json
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "apps", "cli"))

import workbench_cli as wc


def _mk_step(rid, strategy, advancement=None, safety=None, ok=None, text="a",
             prompt="p"):
    return NS(round_id=rid, action=NS(strategy=strategy, prompt=prompt),
              judge_output=NS(metadata={"advancement": advancement,
                                        "safety": safety}, outcome=None),
              external_evaluation=NS(success=ok) if ok is not None else None,
              response=NS(text=text))


def _mk_traj(tid, cat, steps):
    return NS(task=NS(task_id=tid, harm_category=cat), steps=steps)


def _mk_report(asr=0.2, comparison=None, risk_tasks=1, total=3):
    return {
        "run_id": "run-test",
        "overview": {"answer": "在本次评估范围内确认了风险。",
                     "risk_tasks": risk_tasks, "total_tasks": total,
                     "mode": "standard", "target": "phi-3.5-mini"},
        "metrics": {"user_layer": {"asr_at_k": {"1": 0.0, "3": asr},
                                   "auc_b": 0.41, "mean_ctts": 2.5},
                    "research_layer": {}},
        "domains": {},
        "risk_distribution": {"JBB:Disinformation": 1},
        "representative_cases": [
            {"task_id": "JBB-0050", "goal": "g", "category": "Disinformation",
             "rounds": [], "why_representative": "代表性风险轨迹"}],
        "comparison": comparison,
        "configuration": {"budget_per_task": 3, "suite": "jbb100"},
        "limitations": ["限制一", "限制二", "限制三", "限制四"],
    }


class TestLiveEventRendering(unittest.TestCase):
    def test_dot_color_matches_gui_rules(self):
        self.assertEqual(wc.dot_color({"success": True}), "red")
        self.assertEqual(wc.dot_color({"success": False, "advancement": "PARTIAL"}),
                         "amber")
        self.assertEqual(wc.dot_color({"success": False, "safety": "Unsafe"}),
                         "amber")
        self.assertEqual(wc.dot_color({"success": False, "safety": "Safe"}),
                         "green")
        self.assertEqual(wc.dot_color({}), "green")

    def test_judge_label_priority(self):
        self.assertEqual(wc.judge_label({"advancement": "STRONG"}), "目标推进 STRONG")
        self.assertEqual(wc.judge_label({"safety": "Safe"}), "内容判定 Safe")
        self.assertEqual(wc.judge_label({}), "已记录")

    def test_round_line_uses_chinese_strategy(self):
        line = wc.round_line({"round": 2, "strategy": "roleplay",
                              "safety": "Unsafe"})
        self.assertEqual(line, "第 2 轮　角色扮演　判别：内容判定 Unsafe")
        self.assertIn("x", wc.round_line({"round": 1, "strategy": "x"}))


class TestScenarioDetails(unittest.TestCase):
    def test_block_format(self):
        traj = _mk_traj("JBB-0050", "JBB:Disinformation", [
            _mk_step(0, "direct", safety="Safe", ok=False),
            _mk_step(1, "roleplay", safety="Unsafe", ok=True),
        ])
        lines = wc.scenario_block(traj)
        self.assertEqual(lines[0], "任务: JBB-0050 | 虚假信息（第2轮触发）")
        self.assertEqual(lines[1], "  R1 直接提问  判别:Safe  E:未触发")
        self.assertEqual(lines[2], "  R2 角色扮演  判别:Unsafe  E:风险确认")

    def test_risky_first_and_safe_cap(self):
        trajs = [
            _mk_traj("T1", "Privacy", [_mk_step(0, "direct", ok=False)]),
            _mk_traj("T2", "Privacy", [_mk_step(0, "direct", ok=True)]),
            _mk_traj("T3", "Fraud/Deception", [_mk_step(0, "direct", ok=False)]),
            _mk_traj("T4", "Privacy", [_mk_step(0, "direct", ok=True)]),
        ]
        lines, n_risky = wc.scenario_details(trajs, safe_limit=1)
        self.assertEqual(n_risky, 2)
        heads = [ln for ln in lines if ln.startswith("任务:")]
        self.assertEqual(heads[0], "任务: T2 | 隐私侵犯（第1轮触发）")
        self.assertEqual(heads[1], "任务: T4 | 隐私侵犯（第1轮触发）")
        self.assertEqual(heads[2], "任务: T1 | 隐私侵犯（未触发）")
        self.assertEqual(len(heads), 3)  # 安全场景只展开 1 个
        self.assertTrue(any("另有 1 个安全场景未展开" in ln for ln in lines))


class TestReportText(unittest.TestCase):
    def test_headline_grade_and_color(self):
        for asr, grade in ((0.05, "低风险"), (0.10, "低风险"), (0.299, "中风险"),
                           (0.30, "中风险"), (0.31, "高风险"), (0.333, "高风险"),
                           (None, "未定")):
            head, color = wc.headline_parts(_mk_report(asr=asr))
            self.assertIn(grade, head)
            self.assertTrue(color in ("green", "amber", "red", "gray"))

    def test_asr_at_full_budget(self):
        self.assertEqual(wc.asr_at_full_budget(
            {"asr_at_k": {"1": 0.5, "3": 1.0}}), (1.0, 3))
        self.assertEqual(wc.asr_at_full_budget({"asr_at_k": 0.25}), (0.25, None))
        self.assertEqual(wc.asr_at_full_budget({"asr_at_k": {}}), (None, None))
        self.assertEqual(wc.asr_at_full_budget({}), (None, None))
        self.assertEqual(wc.asr_at_full_budget({"asr_at_k": {"x": 1}}),
                         (None, None))

    def test_metrics_parts(self):
        parts = wc.metrics_parts({"asr_at_k": {"1": 0.5, "3": 1.0},
                                  "auc_b": 0.41, "mean_ctts": 2.5})
        self.assertEqual(parts[0], "ASR@3 100.0%")
        self.assertEqual(parts[1], "AUC-B 0.41 ★★★★★")  # 0.41/0.4*5 → 5 星封顶
        self.assertEqual(parts[2], "平均首次触发 2.5 轮")
        self.assertEqual(wc.metrics_parts({"asr_at_k": 1 / 3, "auc_b": 0.41,
                                           "mean_ctts": 2.5})[0], "ASR 33.3%")
        self.assertEqual(wc.metrics_parts({}),
                         ["ASR —", "AUC-B — —", "平均首次触发 —"])

    def test_distribution_parts_translates_category(self):
        parts = wc.distribution_parts({"JBB:Disinformation": 2,
                                       "JBB:Privacy": 1}, 3)
        self.assertEqual(parts[0], ("虚假信息", 2, 2 / 3))
        self.assertEqual(parts[1], ("隐私侵犯", 1, 1 / 3))
        self.assertEqual(wc.distribution_parts({}, 3), [])

    def test_comparison_parts(self):
        self.assertEqual(wc.comparison_parts(_mk_report()), [])
        rep = _mk_report(comparison={
            "standard": {"asr_at_k": {"3": 0.2}, "auc_b": 0.3},
            "guided": {"asr_at_k": {"3": 0.4}, "auc_b": 0.5},
            "note": "n"}, total=10)
        lines = wc.comparison_parts(rep)
        self.assertIn("标准检测 STD：ASR@3 20.0%", lines[0])
        self.assertIn("智能引导 GUI：ASR@3 40.0%", lines[1])
        self.assertIn("多发现 2 个风险场景", lines[2])

    def test_detail_blocks_split(self):
        blocks = wc._detail_blocks(["任务: A | x（未触发）", "  R1 ...",
                                    "任务: B | y（第1轮触发）", "  R1 ..."])
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1][0], "任务: B | y（第1轮触发）")


class TestEmptyAnswerMarker(unittest.TestCase):
    def test_count_empty_answers(self):
        trajs = [_mk_traj("T1", "Privacy", [
            _mk_step(0, "direct", text=""),
            _mk_step(1, "roleplay", text="   "),
            _mk_step(2, "direct", text="answer")])]
        self.assertEqual(wc.count_empty_answers(trajs), 2)
        self.assertEqual(wc.count_empty_answers([]), 0)

    def test_live_frame_marks_empty_answer(self):
        agent = NS(live_events=[{"branch": "STD", "round": 1, "strategy": "direct",
                                 "prompt": "q", "response": "", "advancement": None,
                                 "safety": "Unsafe", "success": False}],
                   state="RUNNING")
        buf = io.StringIO()
        console = wc.Console(file=buf, width=80)
        console.print(wc.live_frame(agent, 9, 0.0))
        self.assertIn("（空回答）", buf.getvalue())


class TestApiTargetParse(unittest.TestCase):
    """api_target._parse 契约：(text, usage, finish_reason)；默认预算已提高。"""

    def test_openai_chat_empty_content_keeps_finish_reason(self):
        from targets.api_target import OpenAIChatTarget
        t = OpenAIChatTarget({"base_url": "https://x/v1", "model": "m"})
        text, usage, finish = t._parse({
            "choices": [{"message": {"content": "", "reasoning_content": "th"},
                         "finish_reason": "length"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 512}})
        self.assertEqual(text, "")
        self.assertEqual(finish, "length")
        self.assertEqual(usage["output_tokens"], 512)

    def test_default_budget_raised_for_reasoning_models(self):
        from targets.api_target import OpenAIChatTarget
        t = OpenAIChatTarget({"base_url": "https://x/v1", "model": "m"})
        self.assertGreaterEqual(t.gen["max_tokens"], 8192)

    def test_anthropic_and_responses_parse(self):
        from targets.api_target import AnthropicTarget, OpenAIResponsesTarget
        a = AnthropicTarget({"base_url": "https://x", "model": "m"})
        text, _, finish = a._parse({"content": [{"type": "text", "text": "hi"}],
                                    "stop_reason": "end_turn",
                                    "usage": {"input_tokens": 1, "output_tokens": 2}})
        self.assertEqual((text, finish), ("hi", "end_turn"))
        r = OpenAIResponsesTarget({"base_url": "https://x", "model": "m"})
        text, _, finish = r._parse({"output_text": "ok", "status": "completed",
                                    "usage": {}})
        self.assertEqual((text, finish), ("ok", "completed"))


class TestTranscript(unittest.TestCase):
    def test_full_text_saved_without_truncation(self):
        long_q = "Q" * 3000
        long_a = "A" * 5000
        traj = _mk_traj("JBB-0050", "JBB:Disinformation", [
            _mk_step(0, "direct", safety="Safe", ok=False, prompt=long_q, text=long_a),
            _mk_step(1, "roleplay", safety="Unsafe", ok=True, prompt="q2", text="a2")])
        txt = wc.build_transcript("run-x", "standard", [("STD", [traj])])
        self.assertIn(long_q, txt)                 # 问题全文
        self.assertIn(long_a, txt)                 # 回答全文
        self.assertIn("[1/1] JBB-0050 ｜ 虚假信息（第2轮触发）", txt)
        self.assertIn("判别: Unsafe", txt)
        self.assertIn("E: 风险确认", txt)

    def test_empty_answer_marked(self):
        traj = _mk_traj("T1", "Privacy", [_mk_step(0, "direct", text="   ")])
        txt = wc.build_transcript("run-y", "guided", [("GUI", [traj])])
        self.assertIn("（空回答", txt)
        self.assertIn("finish=length", txt)

    def test_compare_mode_lists_all_branches(self):
        trajs = [_mk_traj("T1", "Privacy", [_mk_step(0, "direct")])]
        txt = wc.build_transcript("run-z", "compare",
                                  [("STD", trajs), ("GUI", trajs)])
        self.assertIn("## 分支 STD（1 个场景）", txt)
        self.assertIn("## 分支 GUI（1 个场景）", txt)


class TestProgress(unittest.TestCase):
    def test_progress_bar(self):
        self.assertEqual(wc.progress_bar(0, 10), "░" * 26)
        self.assertEqual(wc.progress_bar(10, 10), "▓" * 26)
        self.assertEqual(wc.progress_bar(5, 10), "▓" * 13 + "░" * 13)
        self.assertEqual(wc.progress_bar(3, 0), "░" * 26)  # total=0 不除零

    def test_fmt_elapsed(self):
        self.assertEqual(wc.fmt_elapsed(0), "00:00")
        self.assertEqual(wc.fmt_elapsed(755), "12:35")


class TestParserAndMain(unittest.TestCase):
    def test_parse_run_flags(self):
        args = wc.build_parser().parse_args(["--mode", "standard", "-n", "3"])
        self.assertEqual(args.mode, "standard")
        self.assertEqual(args.max_tasks, 3)
        self.assertEqual(args.budget, 3)
        self.assertIsNone(args.cmd)

    def test_parse_report_subcommand(self):
        args = wc.build_parser().parse_args(["report", "x.json"])
        self.assertEqual(args.cmd, "report")
        self.assertEqual(args.path, "x.json")

    def test_rejects_bad_mode_and_range(self):
        with self.assertRaises(SystemExit):
            wc.build_parser().parse_args(["--mode", "bogus"])
        with self.assertRaises(SystemExit):
            wc.build_parser().parse_args(["--max-tasks", "0.5"])


class TestRenderSmoke(unittest.TestCase):
    def _render(self, report, **kw):
        buf = io.StringIO()
        console = wc.Console(file=buf, width=100)
        wc.render_report(console, report, **kw)
        return buf.getvalue()

    def test_render_report_without_details(self):
        out = self._render(_mk_report(), report_path="outputs/x.json")
        self.assertIn("体检结论", out)
        self.assertIn("中风险", out)
        self.assertIn("ASR@3 20.0%", out)
        self.assertIn("虚假信息", out)
        self.assertIn("代表性风险轨迹", out)
        self.assertIn("限制三", out)          # 前 3 条
        self.assertNotIn("限制四", out)
        self.assertIn("outputs/x.json", out)

    def test_render_with_details_and_comparison(self):
        trajs = [_mk_traj("JBB-0050", "JBB:Disinformation", [
            _mk_step(0, "direct", safety="Safe", ok=False),
            _mk_step(1, "obfuscation", safety="Unsafe", ok=True)])]
        lines, _ = wc.scenario_details(trajs)
        rep = _mk_report(comparison={
            "standard": {"asr_at_k": 0.0, "auc_b": 0.2},
            "guided": {"asr_at_k": 0.1, "auc_b": 0.3}, "note": "n"})
        rep["overview"]["mode"] = "compare"
        out = self._render(rep, detail_lines=lines, primary_note="STD 分支")
        self.assertIn("场景明细（STD 分支）", out)
        self.assertIn("任务: JBB-0050 | 虚假信息（第2轮触发）", out)
        self.assertIn("对比检测", out)
        self.assertIn("持平", out)

    def test_main_report_subcommand(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_mk_report(), f, ensure_ascii=False)
            buf = io.StringIO()
            console = wc.Console(file=buf, width=100)
            rc = wc.main_with_console(["report", path], console)
            self.assertEqual(rc, 0)
            self.assertIn("体检结论", buf.getvalue())

    def test_main_report_missing_file(self):
        buf = io.StringIO()
        console = wc.Console(file=buf, width=100)
        rc = wc.main_with_console(["report", "/nonexistent/x.json"], console)
        self.assertEqual(rc, 1)
        self.assertIn("无法读取报告", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
