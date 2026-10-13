# -*- coding: utf-8 -*-
"""历史 run 回放器：把任意真实 run（或内置演示数据）装载成 MainAgent 形态（零 GPU 秒级）。

W0-2：source 为真实 run_id（outputs/evaluations/{run_id}_*.jsonl 存在）时加载该
run 的轨迹与报告；仅当无对应文件时回退到 1B-R 演示数据，并标记 is_demo=True——
演示数据绝不静默顶替真实检测数据。
"""
import glob
import json
import os


def load_run_branches(run_id: str, outputs_dir: str = "outputs") -> dict:
    """outputs/evaluations/{run_id}_{branch}.jsonl → {branch: [AttackTrajectory]}。"""
    from memory.trajectory_store import TrajectoryStore
    out = {}
    for path in glob.glob(os.path.join(
            outputs_dir, "evaluations", "{}_*.jsonl".format(run_id))):
        base = os.path.basename(path)[:-6]  # strip .jsonl
        branch = base.rsplit("_", 1)[1] if "_" in base else base
        try:
            out[branch] = TrajectoryStore.load(path)
        except Exception:  # noqa: BLE001 损坏文件跳过，不让单个坏档阻塞回放
            continue
    return out


def load_prerun_as_agent(source: str = "stage1b_r_4060",
                         outputs_dir: str = "outputs"):
    from engine.checkpoint import load_checkpoint, rebuild_from_payload
    from memory.trajectory_store import TrajectoryStore
    from safeloop.agents.main_agent import (EvaluationPlan, EvaluationRequest,
                                            SafeLoopMainAgent)
    agent = SafeLoopMainAgent()
    agent.run_id = "replay-{}".format(source)

    branches = ({} if source == "stage1b_r_4060"   # 演示源固定走映射路径
                else load_run_branches(source, outputs_dir))
    if branches:
        # ---------------- 真实 run：按 run_id 加载轨迹与（可选）已存报告
        agent.is_demo = False
        report = None
        rp = os.path.join(outputs_dir, "reports", "{}_report.json".format(source))
        if os.path.exists(rp):
            try:
                with open(rp, encoding="utf-8") as f:
                    report = json.load(f)
            except ValueError:
                report = None
        budget = ((report or {}).get("configuration") or {}).get(
            "budget_per_task") or 5
        req = EvaluationRequest(question="[replay] {}".format(source),
                                budget_per_task=budget)
        req.mode = ("guided" if set(branches) == {"GUI"}
                    else "compare" if "GUI" in branches else "standard")
        plan_branches = [{"name": name, "domain": "all",
                          "mode": "ACTIVE" if name == "GUI" else "SHADOW"}
                         for name in branches]
        agent.plan = EvaluationPlan(
            plan_id="replay", request=req,
            tasks_file="data/tasks/jbb100_full.jsonl",
            n_tasks=sum(len(v) for v in branches.values()),
            domains={"content": 0, "goal": 0}, branches=plan_branches,
            config_path="configs/hardware/rtx4060_8g_1br.yaml")
        agent.trajectories = dict(branches)
        if report is not None:
            agent.report = report
        else:
            from safeloop.skills.report import ReportSkill
            agent.report = ReportSkill().build(agent.run_id, agent.plan,
                                               branches)
        agent.state = "COMPLETED"
        agent._emit("replay_ready", source=source,
                    branches={k: len(v) for k, v in branches.items()})
        return agent

    # ---------------- 演示数据（1B-R 研究产物）：STD←A,C / GUI←B,D
    agent.is_demo = True
    req = EvaluationRequest(question="[replay] {}".format(source), mode="compare")
    agent.plan = EvaluationPlan(
        plan_id="replay", request=req, tasks_file="data/tasks/jbb100_full.jsonl",
        n_tasks=100, domains={"content": 70, "goal": 30},
        branches=[{"name": "STD", "domain": "all", "mode": "SHADOW"},
                  {"name": "GUI", "domain": "all", "mode": "ACTIVE"}],
        config_path="configs/hardware/rtx4060_8g_1br.yaml")
    trajs = {"STD": [], "GUI": []}
    for name, brs in (("STD", ("A", "C")), ("GUI", ("B", "D"))):
        for br in brs:
            path = os.path.join(
                outputs_dir, "evaluations",
                "stage1b_r_4060_BR_{}.jsonl".format(br))
            try:
                ts = TrajectoryStore.load(path)
            except FileNotFoundError:
                payloads = load_checkpoint(os.path.join(
                    outputs_dir, "checkpoints",
                    "stage1b_r_4060_{}.json".format(br)))
                ts = [rebuild_from_payload(p, 5)[2] for p in payloads]
            for t in ts:
                t.condition_id = name
            trajs[name].extend(ts)
    agent.trajectories = trajs
    from safeloop.skills.report import ReportSkill
    agent.report = ReportSkill().build(agent.run_id, agent.plan, trajs)
    agent.state = "COMPLETED"
    agent._emit("replay_ready", source=source,
                branches={k: len(v) for k, v in trajs.items()})
    return agent
