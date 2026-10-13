# -*- coding: utf-8 -*-
"""SafeLoop API（FastAPI + SSE）—— RunManager 承载（roadmap P1/P2）。

启动：uvicorn apps.api.server:app --host 127.0.0.1 --port 8712
      （默认仅本机；鉴权：export SAFELOOP_API_KEY=... 后要求 X-API-Key 头）
接口：POST /evaluations | GET /runs | /evaluations/{id} | /events(SSE,断线续传)
      /tasks | /trajectories | /report | POST .../cancel | .../resume |
      POST /targets/test-connection | POST /replay
"""
import json
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from safeloop.runs.manager import TERMINAL, RunManager, RunSpec

API_KEY = os.environ.get("SAFELOOP_API_KEY", "")

app = FastAPI(title="SafeLoop", version="1.1.0",
              description="多智能体闭环大语言模型安全评估系统")
mgr = RunManager()


@app.middleware("http")
async def _auth(request: Request, call_next):
    if API_KEY and request.headers.get("x-api-key") != API_KEY:
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    return await call_next(request)


class EvalRequest(BaseModel):
    """统一评估请求（新字段 + 兼容旧字段 budget_per_task/max_tasks）。"""
    mode: str = "standard"          # standard / guided / compare
    scope: str = "sample"           # sample / full / single
    scenario_ids: Optional[List[str]] = None
    rounds: int = 3
    sample_size: int = 3
    suite: str = "jbb100"
    seed: int = 42
    config_path: Optional[str] = None
    question: str = ""
    target_model: str = "phi-3.5-mini"
    api_target: Optional[Dict] = None   # {provider,base_url,model,api_key_env}
    save_transcript: bool = True
    generate_report: bool = True
    # ---- 兼容旧字段
    budget_per_task: Optional[int] = None
    max_tasks: Optional[int] = None


def _to_spec(req: EvalRequest) -> RunSpec:
    rounds = req.rounds if req.budget_per_task is None else req.budget_per_task
    size = req.sample_size if req.max_tasks is None else req.max_tasks
    scope = req.scope
    if req.scenario_ids:
        scope = "single"
    return RunSpec(mode=req.mode, scope=scope,
                   scenario_ids=req.scenario_ids or [], rounds=rounds,
                   sample_size=size, suite=req.suite, seed=req.seed,
                   config_path=req.config_path or
                   "configs/hardware/rtx4060_8g_1br.yaml",
                   question=req.question, target_model=req.target_model,
                   api_target=req.api_target,
                   save_transcript=req.save_transcript,
                   generate_report=req.generate_report)


@app.post("/evaluations")
def create_evaluation(req: EvalRequest):
    spec = _to_spec(req)
    run_id = mgr.submit(spec)
    return {"run_id": run_id, "status": "QUEUED", "spec": spec.__dict__}


@app.get("/runs")
def list_runs(limit: int = 50):
    return mgr.list_runs(limit)


@app.get("/evaluations/{run_id}")
def get_evaluation(run_id: str):
    try:
        return mgr.get_run(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run_id: {}".format(run_id))


@app.get("/evaluations/{run_id}/events")
def stream_events(run_id: str, request: Request, after: int = -1):
    """SSE 事件流。断线重连：响应带 id:<seq>，客户端重连带 Last-Event-ID 或
    ?after=<seq> 即可从断点续推（roadmap P1 验收项）。"""
    try:
        mgr.get_run(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run_id: {}".format(run_id))
    last = after if after >= 0 else int(request.headers.get("last-event-id", 0))

    def gen():
        nonlocal last
        while True:
            for ev in mgr.get_events(run_id, after_seq=last):
                last = ev["seq"]
                yield "id: {}\ndata: {}\n\n".format(
                    last, json.dumps(ev, ensure_ascii=False, default=str))
            row = mgr.get_run(run_id)
            if row["status"] in TERMINAL:
                yield "data: [DONE]\n\n"
                return
            import time
            time.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _agent_or_load(run_id: str):
    agent = mgr.get_agent(run_id)
    if agent is not None:
        return agent, False
    from safeloop.skills.replay_loader import load_prerun_as_agent
    try:
        return load_prerun_as_agent(run_id), True
    except Exception:
        raise HTTPException(404, "no trajectories for run: {}".format(run_id))


@app.get("/evaluations/{run_id}/tasks")
def get_tasks(run_id: str):
    agent, _ = _agent_or_load(run_id)
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
    agent, _ = _agent_or_load(run_id)
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
    agent, loaded = _agent_or_load(run_id)
    report = agent.report
    if report is None:
        raise HTTPException(404, "report not ready")
    return report


@app.post("/evaluations/{run_id}/cancel")
def cancel(run_id: str):
    try:
        return mgr.cancel(run_id)
    except KeyError:
        raise HTTPException(404, "unknown run_id: {}".format(run_id))


@app.post("/evaluations/{run_id}/resume")
def resume(run_id: str):
    try:
        return {"run_id": mgr.resume(run_id), "status": "QUEUED"}
    except KeyError:
        raise HTTPException(404, "unknown run_id: {}".format(run_id))
    except ValueError as exc:
        raise HTTPException(409, str(exc))


class ConnectionTestRequest(BaseModel):
    provider: str = "openai_chat"   # openai_chat / anthropic / openai_responses
    base_url: str
    model: str
    api_key_env: str = ""           # key 只从环境变量读，不入请求日志


@app.post("/targets/test-connection")
def target_test_connection(req: ConnectionTestRequest):
    """发一条无害 ping 验证黑盒 API 连通（key 经环境变量）。"""
    from targets.api_target import test_connection
    return test_connection(req.model_dump())


@app.post("/replay")
def replay(run_id: str = "stage1b_r_4060"):
    """装载历史 run（或演示数据）构造回放视图（零 GPU 秒级）。"""
    from safeloop.skills.replay_loader import load_prerun_as_agent
    agent = load_prerun_as_agent(run_id)
    return {"run_id": agent.run_id, "state": agent.state,
            "source": run_id, "is_demo": getattr(agent, "is_demo", False),
            "branches": {k: len(v) for k, v in agent.trajectories.items()}}
