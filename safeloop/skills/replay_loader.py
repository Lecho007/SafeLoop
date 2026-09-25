# -*- coding: utf-8 -*-
"""预跑数据回放器：把 1B-R 等历史 run 装载成 MainAgent 形态（零 GPU 秒级）。"""
from safeloop.agents.main_agent import (EvaluationPlan, EvaluationRequest,
                                        SafeLoopMainAgent)


def load_prerun_as_agent(source: str = "stage1b_r_4060") -> SafeLoopMainAgent:
    from engine.checkpoint import load_checkpoint, rebuild_from_payload
    from memory.trajectory_store import TrajectoryStore
    agent = SafeLoopMainAgent()
    agent.run_id = "replay-{}".format(source)
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
            path = "outputs/evaluations/stage1b_r_4060_BR_{}.jsonl".format(br)
            try:
                ts = TrajectoryStore.load(path)
            except FileNotFoundError:
                payloads = load_checkpoint(
                    "outputs/checkpoints/stage1b_r_4060_{}.json".format(br))
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
