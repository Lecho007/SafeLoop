# -*- coding: utf-8 -*-
"""DeepSeek 黑盒安全体检（v1.0 黑盒 API Target 能力的真实验证）。

配置：provider=openai_chat, base_url=https://api.deepseek.com/v1,
      model=deepseek-flash, api key 仅经环境变量 TARGET_API_KEY。
3 个目标合规域任务 × 每任务 3 轮 = 9 次 Target 查询；
裁判=本地 Qwen3Guard-0.6B（观察），独立评审=StrongREJECT（离线）。
Key 绝不写入任何落盘文件。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if not os.environ.get("TARGET_API_KEY"):
    sys.exit("请先设置环境变量 TARGET_API_KEY（key 只经环境变量传入，永不落盘——红线 4），"
             "例如：export TARGET_API_KEY=sk-...")

from safeloop.agents.main_agent import SafeLoopMainAgent
from safeloop.skills.report import ReportSkill

API_CFG = {"provider": "openai_chat",
           "base_url": "https://api.deepseek.com/v1",
           "model": "deepseek-flash",
           "api_key_env": "TARGET_API_KEY"}


def main() -> None:
    agent = SafeLoopMainAgent()
    agent.submit("评估 DeepSeek 模型的安全风险（黑盒 API）", mode="standard",
                 max_tasks=3, budget_per_task=3, api_target=API_CFG)
    report = agent.run()
    os.makedirs("outputs/reports", exist_ok=True)
    path = "outputs/reports/deepseek_blackbox_report.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    ov = report["overview"]
    print(json.dumps({"answer": ov["answer"],
                      "risk_tasks": ov["risk_tasks"],
                      "total": ov["total_tasks"],
                      "cases": [c["task_id"] for c in
                                report["representative_cases"]]},
                     ensure_ascii=False, indent=1))
    print("report ->", path)


if __name__ == "__main__":
    main()
