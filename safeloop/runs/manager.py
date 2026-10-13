# -*- coding: utf-8 -*-
"""RunManager：统一运行管理（roadmap P1）——单机版的持久化任务心脏。

职责（模块级统一：CLI 进程内直接嵌入，FastAPI 承载同一模块）：
  - SQLite 五表持久化：runs / run_tasks / run_events(递增序号) / artifacts /
    checkpoints；大文件（轨迹/报告/transcript）留文件系统，库只存索引与状态；
  - 串行任务队列：单 GPU → 单工作进程 → FIFO（QUEUED→RUNNING→…终态）；
  - 真取消：QUEUED 直接取消；活动 run 经 agent.cancel() 在轮边界优雅停止；
  - 恢复：CANCELLED/FAILED 且有检查点的 run 可重新入队（resume=True）；
  - 历史导入：首次启动扫描 outputs/reports/*.json 一次性入库（imported 标记）。

零 GPU 测试：agent_factory 可注入（默认 SafeLoopMainAgent）。
"""
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger("safeloop.runs")

TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")

# agent 状态机 → runs.status 域的映射（历史 bug：READY/PLANNING/REPORTING 等
# 中间态曾被直接写入 runs.status，竞态窗口内 API/前端会读到非法状态值）
_AGENT_TO_RUN_STATUS = {
    "IDLE": "RUNNING", "PLANNING": "RUNNING", "READY": "RUNNING",
    "RUNNING": "RUNNING", "CANCELLING": "CANCELLING",
    "EVALUATING": "RUNNING", "ANALYZING": "RUNNING", "REPORTING": "RUNNING",
    "COMPLETED": "COMPLETED", "FAILED": "FAILED", "CANCELLED": "CANCELLED",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  spec_json TEXT NOT NULL,
  question TEXT DEFAULT '',
  mode TEXT DEFAULT '', scope TEXT DEFAULT '', target TEXT DEFAULT '',
  n_tasks INTEGER DEFAULT 0, rounds INTEGER DEFAULT 0,
  total_steps INTEGER DEFAULT 0, steps_done INTEGER DEFAULT 0,
  error TEXT, resume INTEGER DEFAULT 0, imported INTEGER DEFAULT 0,
  created_at TEXT, started_at TEXT, finished_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS run_tasks(
  run_id TEXT, task_id TEXT, harm_category TEXT DEFAULT '',
  rounds_done INTEGER DEFAULT 0, rounds_total INTEGER DEFAULT 0,
  triggered INTEGER DEFAULT 0,
  PRIMARY KEY(run_id, task_id)
);
CREATE TABLE IF NOT EXISTS run_events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL, ts REAL DEFAULT 0, kind TEXT, payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id, seq);
CREATE TABLE IF NOT EXISTS artifacts(
  run_id TEXT, kind TEXT, path TEXT,
  PRIMARY KEY(run_id, kind, path)
);
CREATE TABLE IF NOT EXISTS checkpoints(
  run_id TEXT, branch TEXT, path TEXT, updated_at TEXT,
  PRIMARY KEY(run_id, branch)
);
"""


@dataclass
class RunSpec:
    """统一评估请求（roadmap P2 协议；三端共享）。凭据只含变量名，无密钥。"""
    mode: str = "standard"                    # standard / guided / compare
    scope: str = "sample"                     # sample / full / single
    scenario_ids: List[str] = field(default_factory=list)
    rounds: int = 3                           # 每场景查询轮数
    sample_size: int = 3                      # scope=sample 的场景数
    suite: str = "jbb100"
    seed: int = 42
    config_path: str = "configs/hardware/rtx4060_8g_1br.yaml"
    question: str = ""
    target_model: str = "phi-3.5-mini"
    api_target: Optional[Dict] = None         # {provider,base_url,model,api_key_env}
    save_transcript: bool = True
    generate_report: bool = True
    # ---- v1.1 实验能力（默认关闭）
    use_memory: bool = False                  # 长期攻击记忆
    adaptive_budget: Optional[int] = None     # 自适应评估模式的总查询预算


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def new_run_id() -> str:
    return "run_{}_{}".format(time.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:6])


class RunManager:
    """串行队列 + SQLite 持久化。一个进程一个实例即可（线程安全）。"""

    def __init__(self, db_path: str = "outputs/runs/safeloop.db",
                 agent_factory: Optional[Callable] = None,
                 start_worker: bool = True,
                 import_history: bool = True,
                 outputs_dir: str = "outputs") -> None:
        self.db_path = db_path
        self.outputs_dir = outputs_dir
        self._agents: Dict[str, object] = {}
        self._mirror_seq: Dict[str, int] = {}
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()
        self.agent_factory = agent_factory or self._default_agent_factory
        if import_history:
            self.import_history()
        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        if start_worker:
            self._worker = threading.Thread(target=self._worker_loop,
                                            daemon=True, name="safeloop-worker")
            self._worker.start()

    # ------------------------------------------------------------ agent 工厂
    @staticmethod
    def _default_agent_factory(config_path: str = "", seed: int = 42):
        from safeloop.agents.main_agent import SafeLoopMainAgent
        return SafeLoopMainAgent(
            config_path=config_path or
            "configs/hardware/rtx4060_8g_1br.yaml", seed=seed)

    # ------------------------------------------------------------ 对外 API
    def submit(self, spec: RunSpec) -> str:
        run_id = new_run_id()
        with self._lock:
            self._db.execute(
                "INSERT INTO runs(run_id,status,spec_json,question,mode,scope,"
                "target,n_tasks,rounds,total_steps,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, "QUEUED", json.dumps(asdict(spec),
                                              ensure_ascii=False),
                 spec.question, spec.mode, spec.scope, spec.target_model,
                 (1 if spec.scope == "single" else
                  (spec.sample_size if spec.scope == "sample" else 100)),
                 spec.rounds,
                 (1 if spec.scope == "single" else
                  (spec.sample_size if spec.scope == "sample" else 100))
                 * spec.rounds * (2 if spec.mode == "compare" else 1),
                 _now(), _now()))
            self._db.execute(
                "INSERT INTO run_events(run_id,ts,kind,payload) VALUES(?,?,?,?)",
                (run_id, time.time(), "queued", "{}"))
            self._db.commit()
        logger.info("run queued: %s (%s/%s)", run_id, spec.mode, spec.scope)
        return run_id

    def cancel(self, run_id: str) -> Dict:
        with self._lock:
            row = self._run_row(run_id)
            if row is None:
                raise KeyError("unknown run: {}".format(run_id))
            if row["status"] in TERMINAL:
                return {"run_id": run_id, "status": row["status"],
                        "note": "已结束，无需取消"}
            agent = self._agents.get(run_id)
            if agent is not None and row["status"] in ("RUNNING", "CANCELLING"):
                agent.cancel()   # 轮边界优雅停止；已完成结果保留
                status = "CANCELLING"
            else:                # QUEUED：从未启动，直接取消
                status = "CANCELLED"
                self._set_status(run_id, status, finished=True)
                self._add_event(run_id, "cancelled", '{"phase":"queued"}')
                return {"run_id": run_id, "status": status}
            self._db.execute(
                "UPDATE runs SET status=?,updated_at=? WHERE run_id=?",
                (status, _now(), run_id))
            self._db.commit()
            self._add_event(run_id, "cancel_requested", "{}")
            return {"run_id": run_id, "status": status,
                    "note": "当前调用结束或超时后生效，已完成结果保留"}

    def resume(self, run_id: str) -> str:
        """把 CANCELLED/FAILED 的 run 以同一 run_id 重新入队（从检查点续跑）。"""
        with self._lock:
            row = self._run_row(run_id)
            if row is None:
                raise KeyError("unknown run: {}".format(run_id))
            if row["status"] not in ("CANCELLED", "FAILED"):
                raise ValueError("只有已取消/失败的 run 可恢复（当前 {}）".format(
                    row["status"]))
            has_ckpt = any(os.path.exists(os.path.join(
                self.outputs_dir, "checkpoints",
                "{}_{}.json".format(run_id, br)))
                for br in ("STD", "GUI"))
            self._db.execute(
                "UPDATE runs SET status='QUEUED',resume=1,error=NULL,"
                "updated_at=? WHERE run_id=?", (_now(), run_id))
            self._db.execute(
                "INSERT INTO run_events(run_id,ts,kind,payload) VALUES(?,?,?,?)",
                (run_id, time.time(), "resume_requested",
                 json.dumps({"has_checkpoint": has_ckpt})))
            self._db.commit()
            return run_id

    def get_run(self, run_id: str) -> Dict:
        with self._lock:
            row = self._run_row(run_id)
            if row is None:
                raise KeyError("unknown run: {}".format(run_id))
            self._mirror(run_id)      # 顺手镜像最新事件与进度
            row = self._run_row(run_id)
            d = dict(row)
            d["spec"] = json.loads(d.pop("spec_json") or "{}")
            d["artifacts"] = [dict(r) for r in self._db.execute(
                "SELECT kind,path FROM artifacts WHERE run_id=?"
                " ORDER BY kind", (run_id,))]
            return d

    def list_runs(self, limit: int = 50) -> List[Dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT run_id,status,mode,scope,target,n_tasks,rounds,"
                "steps_done,total_steps,error,imported,created_at,finished_at"
                " FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_events(self, run_id: str, after_seq: int = 0) -> List[Dict]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq,ts,kind,payload FROM run_events"
                " WHERE run_id=? AND seq>? ORDER BY seq",
                (run_id, after_seq)).fetchall()
            out = []
            for r in rows:
                try:
                    payload = json.loads(r["payload"] or "{}")
                except ValueError:
                    payload = {}
                out.append({"seq": r["seq"], "ts": r["ts"],
                            "kind": r["kind"], **payload})
            return out

    def get_agent(self, run_id: str):
        """活动 run 的底层 agent（CLI live 渲染 / API 兼容层用）。"""
        return self._agents.get(run_id)

    def set_reviewed(self, run_id: str, reviewed: bool = True) -> None:
        """高风险案例人工复核标记（roadmap P3）：互斥写入 reviewed/unreviewed。"""
        with self._lock:
            self._db.execute(
                "DELETE FROM artifacts WHERE run_id=?"
                " AND kind IN ('reviewed','unreviewed')", (run_id,))
            self._db.execute(
                "INSERT OR REPLACE INTO artifacts(run_id,kind,path) VALUES(?,?,?)",
                (run_id, "reviewed" if reviewed else "unreviewed", "-"))
            self._db.commit()

    def prune_runs(self, days: int = 30) -> Dict:
        """清理 N 天前的排队/取消/失败 run 记录（长跑库维护）。

        只删 runs/run_tasks/run_events/artifacts/checkpoints 行；COMPLETED
        与 imported 记录、以及文件系统上的产物（报告/轨迹/transcript）全部保留。
        """
        cutoff = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.localtime(time.time() - max(0, days) * 86400))
        with self._lock:
            rows = self._db.execute(
                "SELECT run_id FROM runs WHERE status IN ('QUEUED','CANCELLED','FAILED')"
                " AND created_at < ? AND imported = 0", (cutoff,)).fetchall()
            ids = [r["run_id"] for r in rows]
            if ids:
                marks = ",".join("?" * len(ids))
                for table in ("run_tasks", "run_events", "artifacts", "checkpoints"):
                    self._db.execute(
                        "DELETE FROM {} WHERE run_id IN ({})".format(table, marks), ids)
                self._db.execute(
                    "DELETE FROM runs WHERE run_id IN ({})".format(marks), ids)
                self._db.commit()
        if ids:
            logger.info("pruned %d stale runs (>%dd)", len(ids), days)
        return {"pruned": len(ids), "days": days, "run_ids": ids[:10]}

    def register_artifact(self, run_id: str, kind: str, path: str) -> None:
        """登记产物（导出文件等；P3）。"""
        with self._lock:
            self._db.execute(
                "INSERT OR IGNORE INTO artifacts(run_id,kind,path) VALUES(?,?,?)",
                (run_id, kind, path))
            self._db.commit()

    def shutdown(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------ 工作进程
    def _worker_loop(self) -> None:
        while not self._stop.is_set():
            try:
                run_id = self._next_queued()
                if run_id is None:
                    time.sleep(0.5)
                    continue
                self._execute(run_id)
            except Exception:  # noqa: BLE001 工作进程永不退出
                logger.exception("worker iteration failed")
                time.sleep(1.0)

    def _next_queued(self) -> Optional[str]:
        with self._lock:
            row = self._db.execute(
                "SELECT run_id FROM runs WHERE status='QUEUED'"
                " ORDER BY created_at LIMIT 1").fetchone()
            if row is None:
                return None
            # 抢占式置 RUNNING；检查影响行数防多实例（同进程多 session）双取
            cur = self._db.execute(
                "UPDATE runs SET status='RUNNING',started_at=?,updated_at=?"
                " WHERE run_id=? AND status='QUEUED'", (_now(), _now(),
                                                        row["run_id"]))
            self._db.commit()
            return row["run_id"] if cur.rowcount else None

    def _execute(self, run_id: str) -> None:
        with self._lock:
            row = self._run_row(run_id)
            spec = RunSpec(**json.loads(row["spec_json"]))
            resume = bool(row["resume"])
        agent = self.agent_factory(config_path=spec.config_path, seed=spec.seed)
        with self._lock:
            self._agents[run_id] = agent
        try:
            overrides = {"mode": spec.mode, "budget_per_task": spec.rounds,
                         "max_tasks": (spec.sample_size
                                       if spec.scope == "sample" else None),
                         "target_model": spec.target_model}
            if spec.suite and spec.suite != "jbb100":
                overrides["suite"] = spec.suite
            if spec.use_memory:
                overrides["use_memory"] = True
            if spec.adaptive_budget:
                overrides["adaptive_budget"] = int(spec.adaptive_budget)
            if spec.scope == "single":
                overrides["scenario_ids"] = list(spec.scenario_ids)
                overrides["max_tasks"] = None
            if spec.api_target:
                overrides["api_target"] = spec.api_target
            agent.submit(spec.question or "评估 {} 的安全风险".format(
                spec.target_model), **overrides)
            agent.run_id = run_id          # 统一编号（报告/检查点/轨迹路径对齐）
            # 实际场景数（plan.n_tasks 是"请求值"，single/full 下不等于选中数）
            if spec.scope == "single":
                n = max(1, len(spec.scenario_ids))
            elif spec.scope == "sample":
                n = spec.sample_size
            else:
                tf = getattr(agent.plan, "tasks_file", "") or ""
                n = (sum(1 for _ in open(tf, encoding="utf-8"))
                     if tf and os.path.exists(tf)
                     else (getattr(agent.plan, "n_tasks", 0) or 0))
            total = n * spec.rounds * len(agent.plan.branches)
            with self._lock:
                self._db.execute(
                    "UPDATE runs SET n_tasks=?,total_steps=?,updated_at=?"
                    " WHERE run_id=?", (n, total, _now(), run_id))
                self._db.commit()
            agent.run(resume=resume)
            self._mirror(run_id)
        except Exception as exc:  # noqa: BLE001 与 API 服务 _run_safe 一致
            logger.exception("run %s failed", run_id)
            with self._lock:
                self._db.execute(
                    "UPDATE runs SET status='FAILED',error=?,finished_at=?,"
                    "updated_at=? WHERE run_id=?",
                    (str(exc)[:500], _now(), _now(), run_id))
                self._add_event(run_id, "error", json.dumps(
                    {"message": str(exc)[:300]}))
                self._db.commit()
            return
        finally:
            with self._lock:
                self._mirror(run_id)
                self._agents.pop(run_id, None)

    # ------------------------------------------------------------ 镜像/收尾
    def _mirror(self, run_id: str) -> None:
        """agent 内存态 → SQLite：事件增量、进度、状态、run_tasks、检查点。"""
        agent = self._agents.get(run_id)
        if agent is None:
            return
        last = self._mirror_seq.get(run_id, 0)
        events = agent.events
        with self._lock:
            for ev in events[last:]:
                payload = {k: v for k, v in ev.items() if k not in ("ts", "kind")}
                self._db.execute(
                    "INSERT INTO run_events(run_id,ts,kind,payload)"
                    " VALUES(?,?,?,?)",
                    (run_id, ev.get("ts", time.time()), ev.get("kind", ""),
                     json.dumps(payload, ensure_ascii=False, default=str)))
            if len(events) >= last:
                self._mirror_seq[run_id] = len(events)
            steps = len(getattr(agent, "live_events", []) or [])
            status = _AGENT_TO_RUN_STATUS.get(
                getattr(agent, "state", "RUNNING"), "RUNNING")
            self._db.execute(
                "UPDATE runs SET steps_done=?,status=?,updated_at=?"
                " WHERE run_id=? AND status NOT IN ('CANCELLED','FAILED')",
                (steps, status, _now(), run_id))
            # run_tasks：从 live_events 聚合每任务轮数
            rounds_total = 0
            try:
                spec = json.loads(self._run_row(run_id)["spec_json"])
                rounds_total = spec.get("rounds", 0)
            except Exception:  # noqa: BLE001
                pass
            agg: Dict[str, int] = {}
            for e in agent.live_events:
                agg[e.get("task_id", "?")] = max(
                    agg.get(e.get("task_id", "?"), 0),
                    int(e.get("round", 0) or 0))
            for tid, done in agg.items():
                self._db.execute(
                    "INSERT INTO run_tasks(run_id,task_id,rounds_done,"
                    "rounds_total) VALUES(?,?,?,?)"
                    " ON CONFLICT(run_id,task_id) DO UPDATE SET rounds_done=?",
                    (run_id, tid, done, rounds_total, done))
            if status in TERMINAL:
                self._finalize(run_id, status)
            self._db.commit()

    def _finalize(self, run_id: str, status: str) -> None:
        agent = self._agents.get(run_id)
        report = getattr(agent, "report", None) or {}
        self._db.execute(
            "UPDATE runs SET status=?,finished_at=?,updated_at=? WHERE run_id=?",
            (status, _now(), _now(), run_id))
        rp = os.path.join(self.outputs_dir, "reports",
                          "{}_report.json".format(run_id))
        if os.path.exists(rp):
            self._db.execute(
                "INSERT OR IGNORE INTO artifacts(run_id,kind,path)"
                " VALUES(?,?,?)", (run_id, "report", rp))
        tp = os.path.join(self.outputs_dir, "reports",
                          "{}_transcript.md".format(run_id))
        if not os.path.exists(tp):
            # transcript 统一落盘（所有入口一致，roadmap P2/P3）
            try:
                row = self._run_row(run_id)
                spec = RunSpec(**json.loads(row["spec_json"]))
                if (spec.save_transcript and agent is not None
                        and getattr(agent, "trajectories", None)):
                    from safeloop.skills.transcript import build_transcript
                    os.makedirs(os.path.dirname(tp), exist_ok=True)
                    with open(tp, "w", encoding="utf-8") as f:
                        f.write(build_transcript(
                            run_id, spec.mode,
                            sorted(agent.trajectories.items())))
            except Exception:  # noqa: BLE001 存档失败不影响主流程
                logger.debug("transcript write failed for %s", run_id,
                             exc_info=True)
        if os.path.exists(tp):
            self._db.execute(
                "INSERT OR IGNORE INTO artifacts(run_id,kind,path)"
                " VALUES(?,?,?)", (run_id, "transcript", tp))
        # 检查点登记（最近恢复位置）
        for br in ("STD", "GUI"):
            cp = os.path.join(self.outputs_dir, "checkpoints",
                              "{}_{}.json".format(run_id, br))
            if os.path.exists(cp):
                self._db.execute(
                    "INSERT OR REPLACE INTO checkpoints(run_id,branch,path,"
                    "updated_at) VALUES(?,?,?,?)",
                    (run_id, br, cp, _now()))
        # 风险摘要（历史列表一眼可见）
        ov = report.get("overview") or {}
        if ov:
            self._add_event(run_id, "summary", json.dumps({
                "risk_tasks": ov.get("risk_tasks"),
                "total_tasks": ov.get("total_tasks")}, ensure_ascii=False))

    def _add_event(self, run_id: str, kind: str, payload: str) -> None:
        self._db.execute(
            "INSERT INTO run_events(run_id,ts,kind,payload) VALUES(?,?,?,?)",
            (run_id, time.time(), kind, payload))
        self._db.commit()

    def _set_status(self, run_id: str, status: str, finished: bool = False) -> None:
        ts = _now()
        self._db.execute(
            "UPDATE runs SET status=?,finished_at=?,updated_at=? WHERE run_id=?",
            (status, ts if finished else None, ts, run_id))
        self._db.commit()

    def _run_row(self, run_id: str) -> Optional[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()

    # ------------------------------------------------------------ 历史导入
    def import_history(self) -> int:
        """一次性扫描 outputs/reports/*.json → runs/artifacts（幂等）。"""
        rdir = os.path.join(self.outputs_dir, "reports")
        if not os.path.isdir(rdir):
            return 0
        n = 0
        for fn in sorted(os.listdir(rdir)):
            if not fn.endswith("_report.json"):
                continue
            run_id = fn[:-len("_report.json")]
            if self._run_row(run_id) is not None:
                continue
            try:
                with open(os.path.join(rdir, fn), encoding="utf-8") as f:
                    rep = json.load(f)
            except (OSError, ValueError):
                continue
            ov = rep.get("overview") or {}
            cfg = rep.get("configuration") or {}
            mtime = time.strftime(
                "%Y-%m-%d %H:%M:%S",
                time.localtime(os.path.getmtime(os.path.join(rdir, fn))))
            spec = {"mode": ov.get("mode", ""), "scope": "imported",
                    "rounds": cfg.get("budget_per_task", 0),
                    "suite": cfg.get("suite", "")}
            with self._lock:
                self._db.execute(
                    "INSERT OR IGNORE INTO runs(run_id,status,spec_json,"
                    "question,mode,scope,target,n_tasks,rounds,total_steps,"
                    "steps_done,imported,created_at,finished_at,updated_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (run_id, "COMPLETED", json.dumps(spec, ensure_ascii=False),
                     "", ov.get("mode", ""), "imported", ov.get("target", ""),
                     ov.get("total_tasks", 0), cfg.get("budget_per_task", 0),
                     0, 0, 1, mtime, mtime, mtime))
                self._db.execute(
                    "INSERT OR IGNORE INTO artifacts(run_id,kind,path)"
                    " VALUES(?,?,?)", (run_id, "report",
                                       os.path.join(rdir, fn)))
                tp = os.path.join(rdir, "{}_transcript.md".format(run_id))
                if os.path.exists(tp):
                    self._db.execute(
                        "INSERT OR IGNORE INTO artifacts(run_id,kind,path)"
                        " VALUES(?,?,?)", (run_id, "transcript", tp))
                self._db.commit()
            n += 1
        if n:
            logger.info("imported %d historical runs", n)
        return n
