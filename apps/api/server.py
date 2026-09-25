# -*- coding: utf-8 -*-
"""SafeLoop API（v1.0 设计 §二十二）：FastAPI + SSE 事件流。

启动：uvicorn apps.api.server:app --host 0.0.0.0 --port 8710
接口：POST /evaluations | GET /evaluations/{id} | /events(SSE) | /tasks |
      /trajectories | /report | POST /evaluations/{id}/cancel | POST /replay
"""
import json
import os
import sys
import threading
from typing import Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from safeloop.agents.main_agent import SafeLoopMainAgent

app = FastAPI(title="SafeLoop", version="1.0.0",
              description="多智能体闭环大语言模型安全评估系统")
_runs: Dict = {}


class EvalRequest(BaseModel):
    question: str = "评估 Phi-3.5 在安全风险任务上的表现"
    target_model: str = "phi-3.5-mini"
    mode: str = "standard"          # standard / guided / compare
    budget_per_task: int = 5
    max_tasks: int = None           # 演示子集
    api_target: dict = None         # {provider, base_url, model, api_key_env, generation, headers}


class ConnectionTestRequest(BaseModel):
    provider: str = "openai_chat"   # openai_chat / anthropic / openai_responses
    base_url: str
    model: str
    api_key_env: str = ""           # key 只从环境变量读，不入请求日志


@app.post("/evaluations")
def create_evaluation(req: EvalRequest):
    agent = SafeLoopMainAgent()
    plan = agent.submit(req.question, target_model=req.target_model,
                        mode=req.mode, budget_per_task=req.budget_per_task,
                        max_tasks=req.max_tasks,
                        api_target=req.api_target)
    _runs[agent.run_id] = agent
    threading.Thread(target=_run_safe, args=(agent,), daemon=True).start()
    return {"run_id": agent.run_id, "state": agent.state, "plan": plan.to_dict()}


def _run_safe(agent: SafeLoopMainAgent):
    try:
        agent.run()
    except Exception as exc:  # noqa: BLE001
        agent._set_state("FAILED")
        agent._emit("error", message=str(exc)[:300])


@app.get("/evaluations/{run_id}")
def get_evaluation(run_id: str):
    agent = _runs.get(run_id) or _need(run_id)
    return agent.status()


@app.get("/evaluations/{run_id}/events")
def stream_events(run_id: str):
    """SSE：从当前事件位置起推送（含 replay 快进）。"""
    agent = _need(run_id)

    def gen():
        i = 0
        while True:
            while i < len(agent.events):
                yield "data: {}\n\n".format(json.dumps(
                    agent.events[i], ensure_ascii=False))
                i += 1
            if agent.state in ("COMPLETED", "FAILED", "CANCELLED"):
                yield "data: [DONE]\n\n"
                return
            import time
            time.sleep(1.0)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/evaluations/{run_id}/tasks")
def get_tasks(run_id: str):
    agent = _need(run_id)
    out = []
    for name, trajs in agent.trajectories.items():
        for t in trajs:
            out.append({"branch": name, "task_id": t.task.task_id,
                        "goal": t.task.goal,
                        "domain": (t.task.metadata or {}).get("feedback_observability"),
                        "n_rounds": len(t.steps)})
    return out


@app.get("/evaluations/{run_id}/trajectories")
def get_trajectories(run_id: str, task_id: str = None):
    agent = _need(run_id)
    out = []
    for name, trajs in agent.trajectories.items():
        for t in trajs:
            if task_id and t.task.task_id != task_id:
                continue
            out.append({"branch": name, "task_id": t.task.task_id,
                        "goal": t.task.goal,
                        "steps": [s.to_dict() for s in t.steps]})
    return out


@app.get("/evaluations/{run_id}/report")
def get_report(run_id: str):
    agent = _need(run_id)
    if agent.report is None:
        raise HTTPException(404, "report not ready (state={})".format(agent.state))
    return agent.report


@app.post("/evaluations/{run_id}/cancel")
def cancel(run_id: str):
    agent = _need(run_id)
    agent.cancel()
    return agent.status()


@app.post("/targets/test-connection")
def target_test_connection(req: ConnectionTestRequest):
    """发一条无害 ping 验证黑盒 API 连通（key 经环境变量）。"""
    from targets.api_target import test_connection
    return test_connection(req.model_dump())


@app.post("/replay")
def replay(run_id: str = "stage1b_r_4060"):
    """加载预跑数据（1B-R 等）构造回放 run。"""
    from safeloop.skills.replay_loader import load_prerun_as_agent
    agent = load_prerun_as_agent(run_id)
    _runs[agent.run_id] = agent
    return {"run_id": agent.run_id, "state": agent.state,
            "source": run_id}


def _need(run_id: str) -> SafeLoopMainAgent:
    agent = _runs.get(run_id)
    if agent is None:
        raise HTTPException(404, "unknown run_id: {}".format(run_id))
    return agent
